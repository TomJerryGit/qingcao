#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为插件加载器模块，包含：
- PluginLoader：插件加载器（动态导入、生命周期管理）
- PluginMeta：插件元数据
- PluginSpec：插件规格（路径、manifest、模块）
- LoadResult：加载结果
- 目录扫描与发现
- manifest 解析与校验
- 依赖检查与拓扑排序
- 权限校验
- 插件实例化与激活
- 插件卸载与清理
- 异常隔离与错误恢复
- 加载顺序控制
- 热重载支持
- 版本兼容检查
- 插件目录监控

修复记录:
- _activate_plugin: 显式检查 api 是否为 None，避免 "NoneType object has no attribute"
- _load_plugin: DISABLED 状态不再进入加载流程
- _import_module: 改进 GBK 文件错误提示
- 全部插件激活/错误路径均有完整 traceback
- load_all: 在加载循环之前填充 self.specs（P1-6），
  修复 _check_plugin_dependencies 无法找到依赖插件的问题
- load_all: 移除末尾的 self.specs 填充（已提前），避免重复
"""

import importlib
import importlib.util
import json
import os
import sys
import threading
import time
import traceback
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import QFileSystemWatcher, QObject, QTimer, pyqtSignal


# ============================================================
# 常量
# ============================================================
# 插件目录（**相对/绝对均可**，见 resolve_plugin_dir）
DEFAULT_PLUGIN_DIR = "plugins"


def app_root_dir() -> str:
    """应用根目录（绝对路径）

    冻结运行时为 `_internal`（`ROOT_DIR`/`PLUGINS_DIR` 的基准），
    源码运行时为仓库根目录。
    """
    if getattr(sys, "frozen", False):
        # PyInstaller onedir：数据文件在 _MEIPASS（即 _internal）
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return base
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_plugin_dir(plugin_dir: Optional[str] = None) -> str:
    """把插件目录解析成**绝对路径**。

    为什么必须这样做（真实缺陷）：
        `plugin_dir` 原先写死相对路径 `"plugins"`，其含义取决于**当前工作
        目录**。从资源管理器双击 exe 时 cwd 恰好是 exe 目录，一切正常；
        但通过**快捷方式、任务栏固定项、或其他工作目录**启动时，
        `plugins` 会解析到别处 —— 插件发现数直接变成 0，界面上表现为
        "AI/Git 等菜单全部消失"，而 `插件目录存在` 却仍是 True
        （因为那是另一条用绝对路径的判断）。

    实测（同一 exe）:
        cwd = exe 目录   -> total=10 active=10
        cwd = C:\\        -> total=0  active=0     <-- 用户遇到的情形

    解析顺序：
        1. 已是绝对路径 -> 原样返回
        2. 相对路径 -> 依次尝试：应用根目录、exe/脚本所在目录、当前工作目录
           （取第一个真实存在的；都不存在时返回"应用根目录/相对路径"，
           以便错误信息可读）
    """
    if not plugin_dir:
        plugin_dir = DEFAULT_PLUGIN_DIR
    if os.path.isabs(plugin_dir):
        return plugin_dir

    candidates = []
    try:
        candidates.append(os.path.join(app_root_dir(), plugin_dir))
    except Exception:
        pass
    try:
        candidates.append(
            os.path.join(os.path.dirname(os.path.abspath(sys.executable)), plugin_dir)
        )
    except Exception:
        pass
    candidates.append(os.path.abspath(plugin_dir))
    candidates.append(os.path.join(os.getcwd(), plugin_dir))

    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[0]


# 插件清单文件名
PLUGIN_MANIFEST = "plugin.json"

# 插件入口文件名
PLUGIN_ENTRY = "__init__.py"

# 当前 API 版本（用于兼容性检查）
# P1-1: 插件 API 版本是独立契约，继续保持独立常量
CURRENT_API_VERSION = "2.0.0"

# 当前应用版本（P1-1: 唯一来源 version.py）
try:
    from version import __version__ as _APP_VERSION
except ImportError:  # pragma: no cover
    _APP_VERSION = "0.0.0"
CURRENT_APP_VERSION = _APP_VERSION

# 最小/最大支持版本（用于应用版本匹配）
MIN_SUPPORTED_APP_VERSION = "1.0.0"

# 加载超时（秒）
LOAD_TIMEOUT = 30

# P1-2: 插件目录变化后的防抖延迟（毫秒）
RELOAD_DEBOUNCE_MS = 800

# 允许的权限列表
ALLOWED_PERMISSIONS = {
    "filesystem",
    "network",
    "process",
    "clipboard",
    "dialog",
    "editor_write",
    "editor_read",
    "terminal",
    "lsp",
    "debugger",
    "settings",
    "themes",
    "plugins",
}

# 危险权限（加载时提示用户）
DANGEROUS_PERMISSIONS = {
    "network",
    "process",
    "terminal",
    "debugger",
}


# ============================================================
# 插件状态枚举
# ============================================================


class PluginState(Enum):
    """插件状态"""

    DISCOVERED = auto()  # 已发现
    LOADING = auto()  # 加载中
    LOADED = auto()  # 已加载
    ACTIVATED = auto()  # 已激活
    ERROR = auto()  # 错误
    DISABLED = auto()  # 已禁用
    UNLOADED = auto()  # 已卸载


# ============================================================
# 插件元数据
# ============================================================


@dataclass
class PluginMeta:
    """
    插件元数据。

    从 plugin.json 解析。
    """

    # 基本信息
    name: str = ""  # 内部名称（唯一）
    display_name: str = ""  # 显示名称
    version: str = "0.0.0"  # 版本
    description: str = ""  # 简短描述
    long_description: str = ""  # 详细描述
    author: str = ""  # 作者
    author_email: str = ""  # 作者邮箱
    homepage: str = ""  # 主页
    repository: str = ""  # 仓库地址
    license: str = "MIT"  # 许可证

    # 类型分类
    type: str = "plugin"  # plugin / theme / language / tool
    category: str = "other"  # 分类
    tags: List[str] = field(default_factory=list)

    # 版本兼容
    min_app_version: str = ""  # 最低应用版本
    max_app_version: str = ""  # 最高应用版本
    api_version: str = CURRENT_API_VERSION  # API 版本

    # 依赖
    dependencies: List[str] = field(default_factory=list)
    plugin_dependencies: List[str] = field(default_factory=list)

    # 权限
    permissions: List[str] = field(default_factory=list)

    # 入口
    entry_point: str = PLUGIN_ENTRY  # 入口文件名
    main_class: str = "Plugin"  # 主类名

    # 其他
    enabled: bool = True  # 是否启用
    auto_load: bool = True  # 是否自动加载
    load_order: int = 100  # 加载顺序（越小越先）

    # P1-2: 保留原始 plugin.json 内容，供 hot_reload 等扩展字段使用
    raw: Dict[str, Any] = field(default_factory=dict)

    # 校验字段
    valid: bool = True  # 是否通过校验
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PluginMeta":
        """从字典反序列化"""
        meta = cls()
        for key, value in d.items():
            if hasattr(meta, key):
                setattr(meta, key, value)

        # P1-2: 保留原始清单，供 hot_reload 等扩展字段读取
        try:
            meta.raw = dict(d)
        except Exception:
            meta.raw = {}

        # 补全显示名称
        if not meta.display_name:
            meta.display_name = meta.name

        return meta

    @property
    def has_dangerous_permissions(self) -> bool:
        """是否有危险权限"""
        return bool(set(self.permissions) & DANGEROUS_PERMISSIONS)

    def validate(self) -> bool:
        """
        校验元数据。

        返回:
            是否通过
        """
        self.errors = []
        self.valid = True

        # 必填字段
        if not self.name:
            self.errors.append("缺少 name 字段")
            self.valid = False
        else:
            # 名称格式校验
            import re

            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", self.name):
                self.errors.append("name 必须是合法的标识符（字母、数字、下划线）")
                self.valid = False

        # 版本格式
        if not self._is_valid_version(self.version):
            self.errors.append(f"无效的版本号: {self.version}")
            self.valid = False

        # 权限校验
        invalid_perms = set(self.permissions) - ALLOWED_PERMISSIONS
        if invalid_perms:
            self.errors.append(f"未知权限: {', '.join(invalid_perms)}")
            self.valid = False

        return self.valid

    def check_app_version(self) -> bool:
        """检查应用版本兼容性"""
        try:
            if self.min_app_version:
                if self._compare_version(CURRENT_APP_VERSION, self.min_app_version) < 0:
                    self.errors.append(f"需要应用版本 >= {self.min_app_version}")
                    return False

            if self.max_app_version:
                if self._compare_version(CURRENT_APP_VERSION, self.max_app_version) > 0:
                    self.errors.append(f"支持的最高应用版本为 {self.max_app_version}")
                    return False

            return True

        except Exception:
            return True

    @staticmethod
    def _is_valid_version(version: str) -> bool:
        """检查版本号格式"""
        import re

        return bool(re.match(r"^\d+\.\d+\.\d+(?:[-+][\w\.]+)?$", version))

    @staticmethod
    def _compare_version(v1: str, v2: str) -> int:
        """比较版本号"""
        try:

            def parse(v):
                v = v.split("-")[0].split("+")[0]
                return [int(x) for x in v.split(".")]

            p1 = parse(v1)
            p2 = parse(v2)

            for a, b in zip(p1, p2):
                if a < b:
                    return -1
                elif a > b:
                    return 1

            if len(p1) < len(p2):
                return -1
            elif len(p1) > len(p2):
                return 1

            return 0

        except Exception:
            return 0

    def __repr__(self) -> str:
        return f"<PluginMeta {self.name} v{self.version} valid={self.valid}>"


# ============================================================
# 插件规格
# ============================================================


@dataclass
class PluginSpec:
    """
    插件规格。

    描述一个插件的完整信息。
    """

    # 路径信息
    directory: str = ""  # 插件目录
    manifest_path: str = ""  # manifest 路径
    entry_path: str = ""  # 入口文件路径

    # 元数据
    meta: PluginMeta = field(default_factory=PluginMeta)

    # 模块与实例
    module: Any = None  # 加载的模块
    instance: Any = None  # 插件实例
    api: Any = None  # 插件 API

    # 状态
    state: PluginState = PluginState.DISCOVERED
    error: str = ""  # 错误信息
    load_time_ms: float = 0.0  # 加载耗时
    activated_at: float = 0.0  # 激活时间

    @property
    def name(self) -> str:
        """插件名称"""
        return self.meta.name

    @property
    def version(self) -> str:
        """插件版本"""
        return self.meta.version

    @property
    def is_loaded(self) -> bool:
        """是否已加载"""
        return self.state in (
            PluginState.LOADED,
            PluginState.ACTIVATED,
        )

    @property
    def is_active(self) -> bool:
        """是否已激活"""
        return self.state == PluginState.ACTIVATED

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "directory": self.directory,
            "manifest_path": self.manifest_path,
            "entry_path": self.entry_path,
            "meta": self.meta.to_dict(),
            "state": self.state.name,
            "error": self.error,
            "load_time_ms": self.load_time_ms,
            "activated_at": self.activated_at,
        }

    def __repr__(self) -> str:
        return f"<PluginSpec {self.name} v{self.version} state={self.state.name}>"


# ============================================================
# 加载结果
# ============================================================


@dataclass
class LoadResult:
    """插件加载结果"""

    total: int = 0  # 发现的插件总数
    loaded: int = 0  # 成功加载数
    activated: int = 0  # 成功激活数
    failed: int = 0  # 失败数
    skipped: int = 0  # 跳过数
    disabled: int = 0  # 禁用数

    specs: List[PluginSpec] = field(default_factory=list)
    # 被延后加载的插件（manifest 声明 defer_activation，等启动完成后
    # 再 import+activate，见 PluginLoader.load_deferred）
    deferred: List[PluginSpec] = field(default_factory=list)
    errors: List[Tuple[str, str]] = field(default_factory=list)
    warnings: List[Tuple[str, str]] = field(default_factory=list)

    elapsed_ms: float = 0.0  # 总耗时

    def get_summary(self) -> str:
        """获取摘要"""
        return (
            f"发现 {self.total} 个插件，"
            f"激活 {self.activated} 个，"
            f"失败 {self.failed} 个，"
            f"禁用 {self.disabled} 个 "
            f"({self.elapsed_ms:.0f} ms)"
        )

    def __repr__(self) -> str:
        return f"<LoadResult {self.get_summary()}>"


# ============================================================
# 插件加载器
# ============================================================

__all__ = [n for n in dir() if not n.startswith("__")]
