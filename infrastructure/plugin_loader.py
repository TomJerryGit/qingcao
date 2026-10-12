#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
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
# 插件目录
DEFAULT_PLUGIN_DIR = "plugins"

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
    DISCOVERED = auto()      # 已发现
    LOADING = auto()         # 加载中
    LOADED = auto()          # 已加载
    ACTIVATED = auto()       # 已激活
    ERROR = auto()           # 错误
    DISABLED = auto()        # 已禁用
    UNLOADED = auto()        # 已卸载


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
    name: str = ""                          # 内部名称（唯一）
    display_name: str = ""                  # 显示名称
    version: str = "0.0.0"                  # 版本
    description: str = ""                   # 简短描述
    long_description: str = ""              # 详细描述
    author: str = ""                        # 作者
    author_email: str = ""                  # 作者邮箱
    homepage: str = ""                      # 主页
    repository: str = ""                    # 仓库地址
    license: str = "MIT"                    # 许可证

    # 类型分类
    type: str = "plugin"                    # plugin / theme / language / tool
    category: str = "other"                 # 分类
    tags: List[str] = field(default_factory=list)

    # 版本兼容
    min_app_version: str = ""               # 最低应用版本
    max_app_version: str = ""               # 最高应用版本
    api_version: str = CURRENT_API_VERSION  # API 版本

    # 依赖
    dependencies: List[str] = field(default_factory=list)
    plugin_dependencies: List[str] = field(default_factory=list)

    # 权限
    permissions: List[str] = field(default_factory=list)

    # 入口
    entry_point: str = PLUGIN_ENTRY         # 入口文件名
    main_class: str = "Plugin"              # 主类名

    # 其他
    enabled: bool = True                    # 是否启用
    auto_load: bool = True                  # 是否自动加载
    load_order: int = 100                   # 加载顺序（越小越先）

    # P1-2: 保留原始 plugin.json 内容，供 hot_reload 等扩展字段使用
    raw: Dict[str, Any] = field(default_factory=dict)

    # 校验字段
    valid: bool = True                      # 是否通过校验
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'PluginMeta':
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
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', self.name):
                self.errors.append(
                    "name 必须是合法的标识符（字母、数字、下划线）"
                )
                self.valid = False

        # 版本格式
        if not self._is_valid_version(self.version):
            self.errors.append(f"无效的版本号: {self.version}")
            self.valid = False

        # 权限校验
        invalid_perms = set(self.permissions) - ALLOWED_PERMISSIONS
        if invalid_perms:
            self.errors.append(
                f"未知权限: {', '.join(invalid_perms)}"
            )
            self.valid = False

        return self.valid

    def check_app_version(self) -> bool:
        """检查应用版本兼容性"""
        try:
            if self.min_app_version:
                if self._compare_version(
                    CURRENT_APP_VERSION, self.min_app_version
                ) < 0:
                    self.errors.append(
                        f"需要应用版本 >= {self.min_app_version}"
                    )
                    return False

            if self.max_app_version:
                if self._compare_version(
                    CURRENT_APP_VERSION, self.max_app_version
                ) > 0:
                    self.errors.append(
                        f"支持的最高应用版本为 {self.max_app_version}"
                    )
                    return False

            return True

        except Exception:
            return True

    @staticmethod
    def _is_valid_version(version: str) -> bool:
        """检查版本号格式"""
        import re
        return bool(re.match(
            r'^\d+\.\d+\.\d+(?:[-+][\w\.]+)?$', version
        ))

    @staticmethod
    def _compare_version(v1: str, v2: str) -> int:
        """比较版本号"""
        try:
            def parse(v):
                v = v.split('-')[0].split('+')[0]
                return [int(x) for x in v.split('.')]

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
        return (f"<PluginMeta {self.name} v{self.version} "
                f"valid={self.valid}>")


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
    directory: str = ""             # 插件目录
    manifest_path: str = ""         # manifest 路径
    entry_path: str = ""            # 入口文件路径

    # 元数据
    meta: PluginMeta = field(default_factory=PluginMeta)

    # 模块与实例
    module: Any = None              # 加载的模块
    instance: Any = None            # 插件实例
    api: Any = None                 # 插件 API

    # 状态
    state: PluginState = PluginState.DISCOVERED
    error: str = ""                 # 错误信息
    load_time_ms: float = 0.0       # 加载耗时
    activated_at: float = 0.0       # 激活时间

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
            'directory': self.directory,
            'manifest_path': self.manifest_path,
            'entry_path': self.entry_path,
            'meta': self.meta.to_dict(),
            'state': self.state.name,
            'error': self.error,
            'load_time_ms': self.load_time_ms,
            'activated_at': self.activated_at,
        }

    def __repr__(self) -> str:
        return (f"<PluginSpec {self.name} v{self.version} "
                f"state={self.state.name}>")


# ============================================================
# 加载结果
# ============================================================
@dataclass
class LoadResult:
    """插件加载结果"""

    total: int = 0                          # 发现的插件总数
    loaded: int = 0                         # 成功加载数
    activated: int = 0                      # 成功激活数
    failed: int = 0                         # 失败数
    skipped: int = 0                        # 跳过数
    disabled: int = 0                       # 禁用数

    specs: List[PluginSpec] = field(default_factory=list)
    errors: List[Tuple[str, str]] = field(default_factory=list)
    warnings: List[Tuple[str, str]] = field(default_factory=list)

    elapsed_ms: float = 0.0                 # 总耗时

    def get_summary(self) -> str:
        """获取摘要"""
        return (f"发现 {self.total} 个插件，"
                f"激活 {self.activated} 个，"
                f"失败 {self.failed} 个，"
                f"禁用 {self.disabled} 个 "
                f"({self.elapsed_ms:.0f} ms)")

    def __repr__(self) -> str:
        return f"<LoadResult {self.get_summary()}>"


# ============================================================
# 插件加载器
# ============================================================
class PluginLoader(QObject):
    """
    插件加载器。

    负责:
    - 发现插件目录
    - 解析 manifest
    - 校验依赖与版本
    - 动态导入模块
    - 实例化并激活插件
    - 卸载与清理
    - 异常隔离

    信号:
        plugin_discovered(str): 发现插件（名称）
        plugin_loaded(str): 加载成功（名称）
        plugin_activated(str): 激活成功（名称）
        plugin_unloaded(str): 卸载完成（名称）
        plugin_error(str, str): 加载错误（名称, 错误信息）
        load_finished(object): 加载完成（LoadResult）
    """

    plugin_discovered = pyqtSignal(str)
    plugin_loaded = pyqtSignal(str)
    plugin_activated = pyqtSignal(str)
    plugin_unloaded = pyqtSignal(str)
    plugin_error = pyqtSignal(str, str)
    load_finished = pyqtSignal(object)

    def __init__(self, parent: Optional[QObject] = None,
                 plugin_dir: str = DEFAULT_PLUGIN_DIR,
                 enable_watcher: bool = False,
                 hot_reload_enabled: bool = True):
        """
        参数:
            parent: 父 QObject
            plugin_dir: 插件目录
            enable_watcher: 是否启用目录监控
            hot_reload_enabled: P1-2 监控到变更时是否自动重载
                （enable_watcher 必须为 True 才有意义）
        """
        super().__init__(parent)

        self.plugin_dir = os.path.abspath(plugin_dir)
        self.enable_watcher = enable_watcher
        self.hot_reload_enabled = hot_reload_enabled

        # 已加载的插件规格
        self.specs: Dict[str, PluginSpec] = {}

        # 加载顺序（用于控制依赖）
        self._load_order: List[str] = []

        # 目录监控
        self._watcher: Optional[QFileSystemWatcher] = None
        self._watch_timer: Optional[QTimer] = None
        self._watch_paths: set = set()
        # P1-2: 每个插件目录的最新 mtime，用于判断哪些插件变了
        self._plugin_mtimes: Dict[str, float] = {}

        # 线程锁（保护 specs 操作）
        self._lock = threading.RLock()

        # 全局 API 工厂（由外部注入）
        self._api_factory: Optional[Callable] = None

    # ========================================================
    # 发现插件
    # ========================================================
    def discover(self, plugin_dir: Optional[str] = None) -> List[PluginSpec]:
        """
        扫描插件目录，发现所有插件。

        参数:
            plugin_dir: 插件目录（None 则使用默认）

        返回:
            PluginSpec 列表
        """
        if plugin_dir:
            self.plugin_dir = os.path.abspath(plugin_dir)

        specs = []

        if not os.path.isdir(self.plugin_dir):
            return specs

        try:
            for name in sorted(os.listdir(self.plugin_dir)):
                # 跳过隐藏目录
                if name.startswith('.'):
                    continue

                plugin_path = os.path.join(self.plugin_dir, name)

                # 只处理目录
                if not os.path.isdir(plugin_path):
                    continue

                # 跳过模板目录
                if name.startswith('_'):
                    continue

                # 解析插件
                spec = self._parse_plugin(plugin_path, name)
                if spec:
                    specs.append(spec)
                    self.plugin_discovered.emit(spec.name)

        except Exception as e:
            print(f"[PluginLoader] 扫描目录失败: {e}")
            traceback.print_exc()

        return specs

    def _parse_plugin(self, plugin_path: str,
                       dir_name: str) -> Optional[PluginSpec]:
        """
        解析单个插件。

        参数:
            plugin_path: 插件目录
            dir_name: 目录名

        返回:
            PluginSpec 或 None
        """
        spec = PluginSpec()
        spec.directory = plugin_path

        # 检查 manifest
        manifest_path = os.path.join(plugin_path, PLUGIN_MANIFEST)

        if not os.path.exists(manifest_path):
            # 无 manifest，使用目录名作为插件名
            meta = PluginMeta(name=dir_name)
            meta.display_name = dir_name
            meta.valid = False
            meta.errors.append("缺少 plugin.json")
            spec.meta = meta
            spec.state = PluginState.ERROR
            spec.error = "缺少 plugin.json"
            return spec

        spec.manifest_path = manifest_path

        # 解析 manifest
        try:
            with open(manifest_path, encoding='utf-8') as f:
                manifest = json.load(f)

            if not isinstance(manifest, dict):
                raise ValueError("manifest 必须是 JSON 对象")

            meta = PluginMeta.from_dict(manifest)

            # 名称校验：如果不匹配则使用目录名
            if not meta.name:
                meta.name = dir_name

            # 校验
            meta.validate()
            meta.check_app_version()

            spec.meta = meta

            # 检查入口
            entry_path = os.path.join(plugin_path, meta.entry_point)
            if not os.path.exists(entry_path):
                entry_path = os.path.join(plugin_path, PLUGIN_ENTRY)

            if not os.path.exists(entry_path):
                spec.state = PluginState.ERROR
                spec.error = "缺少入口文件"
                meta.valid = False
                meta.errors.append("缺少入口文件")
                return spec

            spec.entry_path = entry_path

            # 检查启用状态
            if not meta.enabled:
                spec.state = PluginState.DISABLED
            elif not meta.valid:
                spec.state = PluginState.ERROR
                spec.error = "; ".join(meta.errors)
            else:
                spec.state = PluginState.DISCOVERED

        except json.JSONDecodeError as e:
            spec.state = PluginState.ERROR
            spec.error = f"plugin.json 解析失败: {e}"
        except Exception as e:
            spec.state = PluginState.ERROR
            spec.error = str(e)

        return spec

    # ========================================================
    # 加载插件
    # ========================================================
    def load_all(self, plugin_dir: Optional[str] = None,
                 api_factory: Optional[Callable] = None,
                 auto_activate: bool = True) -> LoadResult:
        """
        加载所有插件。

        参数:
            plugin_dir: 插件目录
            api_factory: 创建插件 API 的工厂函数，接收 PluginSpec 返回 api 对象
            auto_activate: 是否自动激活

        返回:
            LoadResult

        修复说明（P1-6）:
            - 原实现在加载循环结束后才填充 self.specs，导致
              _load_plugin → _check_plugin_dependencies 在遍历
              self.specs 时找不到任何依赖项，任何声明了
              plugin_dependencies 的插件都会失败。
            - 修复：在加载循环之前先用 discover 的结果填充
              self.specs（同时 clear 旧的条目），确保依赖检查
              能正确找到依赖插件。
            - 移除了原末尾的填充逻辑，避免重复赋值。
        """
        start_time = time.time()

        result = LoadResult()

        # 保存 API 工厂
        if api_factory:
            self._api_factory = api_factory

        # 发现插件
        specs = self.discover(plugin_dir)
        result.total = len(specs)
        result.specs = specs

        # ====================================================
        # 关键修复（P1-6）：在加载循环之前填充 self.specs
        # ====================================================
        # 说明：
        #   _load_plugin 会调用 _check_plugin_dependencies，
        #   后者遍历 self.specs 检查依赖插件的激活状态。
        #   若此时 self.specs 为空，则所有带依赖的插件都会
        #   因"缺少插件依赖"而失败。
        with self._lock:
            self.specs.clear()
            for spec in specs:
                self.specs[spec.name] = spec

        # 过滤出可加载的插件
        # 修复：DISABLED 状态的插件不进入加载队列
        loadable = [s for s in specs if s.state == PluginState.DISCOVERED]

        # 按 load_order 和依赖排序
        sorted_specs = self._sort_by_dependencies(loadable)

        # 加载每个插件
        for spec in sorted_specs:
            try:
                success = self._load_plugin(spec)

                if success:
                    result.loaded += 1

                    if auto_activate and spec.meta.auto_load:
                        if self._activate_plugin(spec):
                            result.activated += 1
                        else:
                            result.failed += 1
                            result.errors.append(
                                (spec.name, spec.error or "激活失败")
                            )
                else:
                    result.failed += 1
                    result.errors.append(
                        (spec.name, spec.error or "加载失败")
                    )

            except Exception as e:
                spec.state = PluginState.ERROR
                spec.error = str(e)
                result.failed += 1
                result.errors.append((spec.name, str(e)))

                self.plugin_error.emit(spec.name, str(e))

                traceback.print_exc()

        # 统计（去重）
        for spec in specs:
            if spec.state == PluginState.DISABLED:
                result.disabled += 1
            elif spec.state == PluginState.ERROR:
                if (spec.name, spec.error) not in result.errors:
                    result.failed += 1
                    result.errors.append(
                        (spec.name, spec.error)
                    )

        result.elapsed_ms = (time.time() - start_time) * 1000

        # 更新加载顺序
        self._update_load_order()

        # 发射信号
        self.load_finished.emit(result)

        return result

    def _load_plugin(self, spec: PluginSpec) -> bool:
        """
        加载单个插件（导入模块）。

        参数:
            spec: 插件规格

        返回:
            是否成功
        """
        # 修复：只有 DISCOVERED 状态才能加载
        if spec.state != PluginState.DISCOVERED:
            return False

        if not spec.meta.valid:
            spec.state = PluginState.ERROR
            spec.error = "; ".join(spec.meta.errors)
            return False

        # 检查插件依赖
        if not self._check_plugin_dependencies(spec):
            spec.state = PluginState.ERROR
            spec.error = spec.error or "缺少插件依赖"
            return False

        start_time = time.time()

        try:
            spec.state = PluginState.LOADING

            # 动态导入模块
            module = self._import_module(spec)

            if module is None:
                spec.state = PluginState.ERROR
                spec.error = "模块导入失败"
                return False

            spec.module = module

            spec.state = PluginState.LOADED
            spec.load_time_ms = (time.time() - start_time) * 1000

            self.plugin_loaded.emit(spec.name)

            return True

        except Exception as e:
            spec.state = PluginState.ERROR
            spec.error = str(e)
            spec.load_time_ms = (time.time() - start_time) * 1000

            self.plugin_error.emit(spec.name, str(e))

            # 打印堆栈
            traceback.print_exc()

            return False

    def _import_module(self, spec: PluginSpec):
        """
        动态导入插件模块。

        参数:
            spec: 插件规格

        返回:
            模块对象或 None
        """
        try:
            # 生成唯一的模块名
            module_name = f"qingcao_plugin_{spec.name}"

            # 加载入口文件
            loader = importlib.util.spec_from_file_location(
                module_name, spec.entry_path
            )

            if loader is None:
                print(
                    f"[PluginLoader] 无法创建模块加载器: "
                    f"{spec.entry_path}"
                )
                return None

            module = importlib.util.module_from_spec(loader)

            # 将模块添加到 sys.modules（供内部 import 使用）
            sys.modules[module_name] = module

            # 执行模块
            try:
                loader.loader.exec_module(module)
            except SyntaxError as e:
                # 修复：为 GBK 编码错误提供更清晰的提示
                error_msg = str(e)
                if 'invalid character' in error_msg or \
                        'unicode error' in error_msg.lower():
                    error_msg += (
                        "\n提示：插件源文件可能不是 UTF-8 编码。"
                        "\n请运行 python fix_gbk.py 转换编码，"
                        "或用 VSCode 将文件另存为 UTF-8。"
                    )
                print(
                    f"[PluginLoader] 语法/编码错误 "
                    f"({spec.name}): {error_msg}"
                )
                # 清理 sys.modules 中的残留
                sys.modules.pop(module_name, None)
                spec.error = error_msg
                return None

            return module

        except Exception as e:
            print(f"[PluginLoader] 导入模块失败 ({spec.name}): {e}")
            traceback.print_exc()
            spec.error = str(e)
            return None

    # ========================================================
    # 激活插件
    # ========================================================
    def _activate_plugin(self, spec: PluginSpec) -> bool:
        """
        激活插件。

        参数:
            spec: 插件规格

        返回:
            是否成功

        修复说明:
            - 显式检查 api 是否为 None
            - 使用 try/except 包裹 activate() 调用
            - 失败时给出完整堆栈
        """
        # 修复：只允许 LOADED 状态进入
        if spec.state != PluginState.LOADED:
            return False

        if not spec.module:
            spec.state = PluginState.ERROR
            spec.error = "模块未加载"
            return False

        try:
            # 获取 Plugin 类
            plugin_class = getattr(
                spec.module, spec.meta.main_class, None
            )

            if plugin_class is None:
                spec.state = PluginState.ERROR
                spec.error = (
                    f"未找到 {spec.meta.main_class} 类"
                )
                self.plugin_error.emit(spec.name, spec.error)
                return False

            # 创建插件 API
            api = self._create_api(spec)

            # 修复：显式检查 api
            if api is None:
                spec.state = PluginState.ERROR
                spec.error = (
                    "无法创建插件 API（api_factory 返回 None）"
                )
                self.plugin_error.emit(spec.name, spec.error)
                return False

            spec.api = api

            # 实例化插件
            try:
                plugin_instance = plugin_class()
            except Exception as e:
                spec.state = PluginState.ERROR
                spec.error = f"实例化插件类失败: {e}"
                self.plugin_error.emit(spec.name, str(e))
                traceback.print_exc()
                return False

            spec.instance = plugin_instance

            # 调用 activate
            try:
                plugin_instance.activate(api)
            except Exception as e:
                spec.state = PluginState.ERROR
                spec.error = f"activate() 失败: {e}"
                self.plugin_error.emit(spec.name, str(e))
                traceback.print_exc()

                # 尝试回滚
                try:
                    if hasattr(plugin_instance, 'deactivate'):
                        plugin_instance.deactivate()
                except Exception:
                    pass

                return False

            # 成功
            spec.state = PluginState.ACTIVATED
            spec.activated_at = time.time()

            self.plugin_activated.emit(spec.name)

            # 发布事件
            try:
                from app.event_bus import PluginLoadedEvent, bus
                bus.emit_event(PluginLoadedEvent(
                    plugin_name=spec.name,
                    version=spec.version,
                    load_time_ms=spec.load_time_ms,
                ))
            except Exception:
                pass

            return True

        except Exception as e:
            spec.state = PluginState.ERROR
            spec.error = f"激活异常: {e}"

            self.plugin_error.emit(spec.name, str(e))

            # 打印堆栈
            traceback.print_exc()

            return False

    def _create_api(self, spec: PluginSpec):
        """
        创建插件 API。

        修复说明:
            - 检查工厂函数的返回值是否为 None
            - 捕获工厂函数内部的异常
        """
        if self._api_factory:
            try:
                api = self._api_factory(spec)
                if api is None:
                    print(
                        f"[PluginLoader] api_factory 返回 None "
                        f"({spec.name})"
                    )
                return api
            except Exception as e:
                print(
                    f"[PluginLoader] 创建 API 失败 "
                    f"({spec.name}): {e}"
                )
                traceback.print_exc()

        # 回退：返回 None
        return None

    # ========================================================
    # 依赖检查与排序
    # ========================================================
    def _check_plugin_dependencies(self, spec: PluginSpec) -> bool:
        """
        检查插件依赖是否已加载。

        修复说明（P1-6）:
            - 本方法依赖 self.specs 已被 load_all 提前填充。
              若 load_all 在循环结束才填充，则此处的查找会
              永远失败。
        """
        if not spec.meta.plugin_dependencies:
            return True

        with self._lock:
            for dep_name in spec.meta.plugin_dependencies:
                dep_spec = self.specs.get(dep_name)
                if dep_spec is None or not dep_spec.is_active:
                    # 依赖未激活
                    if dep_spec is None:
                        spec.error = f"缺少插件依赖: {dep_name}"
                    else:
                        spec.error = (
                            f"依赖插件 {dep_name} 未激活"
                        )
                    return False

        return True

    def _sort_by_dependencies(self,
                                specs: List[PluginSpec]) -> List[PluginSpec]:
        """
        按依赖关系拓扑排序。

        参数:
            specs: 插件规格列表

        返回:
            排序后的列表
        """
        # 构建依赖图
        name_to_spec = {s.name: s for s in specs}

        # 计算加载顺序
        visited: Set[str] = set()
        result: List[PluginSpec] = []
        visiting: Set[str] = set()

        def visit(spec: PluginSpec):
            if spec.name in visited:
                return

            if spec.name in visiting:
                # 检测到循环依赖
                print(f"[PluginLoader] 检测到循环依赖: {spec.name}")
                return

            visiting.add(spec.name)

            # 先访问依赖
            for dep_name in spec.meta.plugin_dependencies:
                dep_spec = name_to_spec.get(dep_name)
                if dep_spec:
                    visit(dep_spec)

            visiting.discard(spec.name)

            if spec.name not in visited:
                visited.add(spec.name)
                result.append(spec)

        # 按 load_order 排序
        sorted_specs = sorted(
            specs, key=lambda s: s.meta.load_order
        )

        for spec in sorted_specs:
            visit(spec)

        return result

    def _update_load_order(self):
        """更新加载顺序列表"""
        with self._lock:
            activated = [
                name for name, spec in self.specs.items()
                if spec.is_active
            ]
            self._load_order = activated

    # ========================================================
    # 卸载插件
    # ========================================================
    def unload_plugin(self, name: str) -> bool:
        """
        卸载单个插件。

        参数:
            name: 插件名

        返回:
            是否成功
        """
        with self._lock:
            spec = self.specs.get(name)

        if not spec:
            return False

        try:
            # 调用 deactivate
            if spec.instance and hasattr(spec.instance, 'deactivate'):
                try:
                    spec.instance.deactivate()
                except Exception as e:
                    print(
                        f"[PluginLoader] deactivate 失败 "
                        f"({name}): {e}"
                    )

            # 清理 API 资源
            if spec.api and hasattr(spec.api, 'cleanup'):
                try:
                    spec.api.cleanup()
                except Exception as e:
                    print(f"[PluginLoader] API cleanup 失败: {e}")

            # 从 sys.modules 中移除
            module_name = f"qingcao_plugin_{name}"
            if module_name in sys.modules:
                try:
                    del sys.modules[module_name]
                except Exception:
                    pass

            spec.state = PluginState.UNLOADED

            self.plugin_unloaded.emit(name)

            # 发布事件
            try:
                from app.event_bus import PluginUnloadedEvent, bus
                bus.emit_event(PluginUnloadedEvent(
                    plugin_name=name,
                    version=spec.version,
                ))
            except Exception:
                pass

            return True

        except Exception as e:
            spec.state = PluginState.ERROR
            spec.error = f"卸载失败: {e}"
            traceback.print_exc()
            return False

    def unload_all(self) -> int:
        """
        卸载所有插件。

        返回:
            卸载数量
        """
        count = 0

        # 逆序卸载（先加载的后卸载）
        names = list(reversed(self._load_order))

        for name in names:
            if self.unload_plugin(name):
                count += 1

        return count

    def reload_plugin(self, name: str) -> bool:
        """
        重新加载单个插件。

        参数:
            name: 插件名

        返回:
            是否成功
        """
        with self._lock:
            spec = self.specs.get(name)

        if not spec:
            return False

        # 保存路径
        directory = spec.directory

        # 卸载
        self.unload_plugin(name)

        # 重新解析
        dir_name = os.path.basename(directory)
        new_spec = self._parse_plugin(directory, dir_name)

        if not new_spec:
            return False

        # 加载
        if self._load_plugin(new_spec):
            if self._activate_plugin(new_spec):
                with self._lock:
                    self.specs[name] = new_spec
                return True

        return False

    # ========================================================
    # 查询
    # ========================================================
    def get_plugin(self, name: str) -> Optional[PluginSpec]:
        """获取插件规格"""
        with self._lock:
            return self.specs.get(name)

    def get_all_plugins(self) -> List[PluginSpec]:
        """获取所有插件"""
        with self._lock:
            return list(self.specs.values())

    def get_activated_plugins(self) -> List[PluginSpec]:
        """获取所有已激活的插件"""
        with self._lock:
            return [
                s for s in self.specs.values()
                if s.is_active
            ]

    def get_plugin_names(self) -> List[str]:
        """获取所有插件名称"""
        with self._lock:
            return list(self.specs.keys())

    def is_loaded(self, name: str) -> bool:
        """检查插件是否已加载"""
        with self._lock:
            spec = self.specs.get(name)
            return spec is not None and spec.is_loaded

    def is_active(self, name: str) -> bool:
        """检查插件是否已激活"""
        with self._lock:
            spec = self.specs.get(name)
            return spec is not None and spec.is_active

    def get_plugin_count(self) -> int:
        """获取插件总数"""
        with self._lock:
            return len(self.specs)

    def get_load_order(self) -> List[str]:
        """获取加载顺序"""
        return list(self._load_order)

    # ========================================================
    # 目录监控（热重载）
    # ========================================================
    def start_watching(self):
        """启动目录监控（P1-2: 支持真正的热重载）"""
        if not self.enable_watcher:
            return

        if self._watcher is not None:
            return

        try:
            self._watcher = QFileSystemWatcher(self)
            # 监控插件根目录，以及每个已发现插件目录内的文件
            self._watch_paths = set()
            self._add_watch_path(self.plugin_dir)
            # P1-2: 递归登记插件子目录与源文件，
            # 否则 QFileSystemWatcher 只会报告根目录变化，
            # 修改某个插件的 __init__.py 不会触发重载。
            self._refresh_watch_paths()

            # 延迟重载定时器（防抖）
            self._watch_timer = QTimer(self)
            self._watch_timer.setSingleShot(True)
            self._watch_timer.setInterval(RELOAD_DEBOUNCE_MS)
            self._watch_timer.timeout.connect(
                self._on_directory_changed
            )

            self._watcher.directoryChanged.connect(
                lambda p: self._watch_timer.start()
            )
            self._watcher.fileChanged.connect(
                lambda p: self._watch_timer.start()
            )

        except Exception as e:
            print(f"[PluginLoader] 启动监控失败: {e}")

    def _add_watch_path(self, path: str):
        """把路径加入 QFileSystemWatcher（去重，统一绝对路径）"""
        if not self._watcher or not path:
            return
        path = os.path.abspath(path)
        if not os.path.exists(path):
            return
        if not hasattr(self, '_watch_paths'):
            self._watch_paths = set()
        if path in self._watch_paths:
            return
        try:
            if self._watcher.addPath(path):
                self._watch_paths.add(path)
        except Exception:
            pass

    def _refresh_watch_paths(self):
        """重新扫描插件目录，把变更的文件纳入监控"""
        if not self._watcher:
            return
        self._add_watch_path(self.plugin_dir)
        try:
            for name in os.listdir(self.plugin_dir):
                d = os.path.join(self.plugin_dir, name)
                if not os.path.isdir(d):
                    continue
                self._add_watch_path(d)
                for fname in os.listdir(d):
                    # 只监控源码与清单，避免 __pycache__ 噪声
                    if fname.endswith(('.py', '.json')):
                        self._add_watch_path(os.path.join(d, fname))
        except Exception as e:
            print(f"[PluginLoader] 刷新监控路径失败: {e}")

    def stop_watching(self):
        """停止目录监控"""
        if self._watcher:
            try:
                self._watcher.deleteLater()
            except Exception:
                pass
            self._watcher = None

        if self._watch_timer:
            self._watch_timer.stop()

    def _on_directory_changed(self):
        """目录/文件变化回调（P1-2: 真正的热重载）

        P1-2 修复：原实现只有一句
            print("[PluginLoader] 插件目录已变化，可能需要重启编辑器")
        即 README 宣称的"修改插件代码后无需重启"实际不成立。

        现在：默认对变化的插件执行 unload + load + activate；
        可在 plugin.json 中设置 "hot_reload": false 让单个插件
        退出热重载（例如需要保持长连接的插件）。
        """
        changed = self._detect_changed_plugins()
        self._refresh_watch_paths()

        if not changed:
            return

        if not self.hot_reload_enabled:
            print(
                "[PluginLoader] 检测到插件变更: %s"
                "（热重载已关闭，请手动重载）" % ", ".join(sorted(changed))
            )
            return

        for name in sorted(changed):
            spec = self.specs.get(name)
            if spec is None:
                # 新出现的插件目录：重新发现一次
                print(f"[PluginLoader] 发现新插件目录: {name}")
                self.discover()
                self._refresh_watch_paths()
                continue

            if not self._is_hot_reload_allowed(spec):
                print(f"[PluginLoader] {name} 声明 hot_reload=false，跳过")
                continue

            print(f"[PluginLoader] 热重载插件: {name}")
            try:
                self.reload_plugin(name)
            except Exception as e:
                print(f"[PluginLoader] 热重载 {name} 失败: {e}")
                self.plugin_error.emit(name, str(e))

    def _detect_changed_plugins(self) -> set:
        """通过 mtime 判断哪些插件目录内容发生了变化"""
        changed = set()
        try:
            for name in os.listdir(self.plugin_dir):
                d = os.path.join(self.plugin_dir, name)
                if not os.path.isdir(d):
                    continue
                latest = 0.0
                for fname in os.listdir(d):
                    if not fname.endswith(('.py', '.json')):
                        continue
                    try:
                        latest = max(
                            latest,
                            os.path.getmtime(os.path.join(d, fname))
                        )
                    except OSError:
                        continue
                prev = self._plugin_mtimes.get(name)
                if prev is None:
                    self._plugin_mtimes[name] = latest
                elif latest > prev:
                    self._plugin_mtimes[name] = latest
                    changed.add(name)
        except Exception as e:
            print(f"[PluginLoader] 检测插件变更失败: {e}")
        return changed

    def _is_hot_reload_allowed(self, spec) -> bool:
        """插件是否允许热重载（plugin.json 的 hot_reload 字段）"""
        try:
            raw = getattr(spec.meta, 'raw', None) or {}
            return bool(raw.get('hot_reload', True))
        except Exception:
            return True

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出加载器信息"""
        lines = ["PluginLoader", "=" * 60]
        lines.append(f"插件目录: {self.plugin_dir}")
        lines.append(f"插件数量: {len(self.specs)}")
        lines.append(
            f"激活数量: {len(self.get_activated_plugins())}"
        )
        lines.append(f"加载顺序: {self._load_order}")
        lines.append("")

        if self.specs:
            lines.append("插件列表:")
            for name, spec in sorted(self.specs.items()):
                state_marker = {
                    PluginState.ACTIVATED: "✓",
                    PluginState.LOADED: "◐",
                    PluginState.DISABLED: "⊘",
                    PluginState.ERROR: "✗",
                    PluginState.UNLOADED: "−",
                }.get(spec.state, "?")

                lines.append(
                    f"  {state_marker} {name:25s} "
                    f"v{spec.version:10s} "
                    f"{spec.state.name}"
                )

                if spec.error:
                    lines.append(f"      错误: {spec.error}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<PluginLoader plugins={len(self.specs)} "
                f"activated={len(self.get_activated_plugins())}>")


# ============================================================
# 便捷函数
# ============================================================
def create_loader(plugin_dir: str = DEFAULT_PLUGIN_DIR) -> PluginLoader:
    """创建插件加载器"""
    return PluginLoader(plugin_dir=plugin_dir)


def discover_plugins(plugin_dir: str = DEFAULT_PLUGIN_DIR) -> List[PluginSpec]:
    """
    快速发现插件（无需加载）。

    参数:
        plugin_dir: 插件目录

    返回:
        PluginSpec 列表
    """
    loader = PluginLoader(plugin_dir=plugin_dir)
    return loader.discover()


def load_plugins(plugin_dir: str = DEFAULT_PLUGIN_DIR,
                  api_factory: Optional[Callable] = None) -> LoadResult:
    """
    快速加载所有插件。

    参数:
        plugin_dir: 插件目录
        api_factory: API 工厂函数

    返回:
        LoadResult
    """
    loader = PluginLoader(plugin_dir=plugin_dir)
    return loader.load_all(plugin_dir, api_factory=api_factory)


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import shutil
    import tempfile

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # 创建测试插件目录
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_plugin_loader_test_")

    try:
        # 创建插件 1
        plugin1_dir = os.path.join(tmp_dir, "demo_plugin")
        os.makedirs(plugin1_dir)

        with open(os.path.join(plugin1_dir, "plugin.json"),
                   'w', encoding='utf-8') as f:
            json.dump({
                "name": "demo_plugin",
                "display_name": "示例插件",
                "version": "1.0.0",
                "description": "这是一个示例插件",
                "author": "hedongwei",
                "permissions": ["filesystem"],
                "dependencies": [],
            }, f, indent=2, ensure_ascii=False)

        with open(os.path.join(plugin1_dir, "__init__.py"),
                   'w', encoding='utf-8') as f:
            f.write('''
class Plugin:
    def __init__(self):
        self.name = "demo_plugin"

    def activate(self, api):
        print(f"[{self.name}] 插件已激活")
        self.api = api

    def deactivate(self):
        print(f"[{self.name}] 插件已停用")
''')

        # 创建插件 2（无 manifest，测试错误处理）
        plugin2_dir = os.path.join(tmp_dir, "broken_plugin")
        os.makedirs(plugin2_dir)

        # 创建插件 3（禁用）
        plugin3_dir = os.path.join(tmp_dir, "disabled_plugin")
        os.makedirs(plugin3_dir)

        with open(os.path.join(plugin3_dir, "plugin.json"),
                   'w', encoding='utf-8') as f:
            json.dump({
                "name": "disabled_plugin",
                "version": "1.0.0",
                "enabled": False,
            }, f, indent=2)

        with open(os.path.join(plugin3_dir, "__init__.py"),
                   'w', encoding='utf-8') as f:
            f.write(
                'class Plugin:\n'
                '    def activate(self, api): pass\n'
            )

        # 创建加载器
        print("=== 测试 PluginLoader ===")
        loader = PluginLoader(plugin_dir=tmp_dir)

        # 连接信号
        loader.plugin_discovered.connect(
            lambda name: print(f"[信号] 发现: {name}")
        )
        loader.plugin_loaded.connect(
            lambda name: print(f"[信号] 加载: {name}")
        )
        loader.plugin_activated.connect(
            lambda name: print(f"[信号] 激活: {name}")
        )
        loader.plugin_error.connect(
            lambda name, err: print(
                f"[信号] 错误: {name} - {err}"
            )
        )

        print()
        print("=== 发现插件 ===")
        specs = loader.discover()
        for spec in specs:
            print(f"  {spec.name} v{spec.version} "
                  f"状态={spec.state.name} "
                  f"有效={spec.meta.valid}")
        print()

        print("=== 加载所有插件 ===")

        def api_factory(spec):
            """测试用的 API 工厂"""
            class TestAPI:
                def __init__(self, spec_obj):
                    self.spec = spec_obj

                def log(self, msg, level="info"):
                    # F821 修复：原实现引用了外层工厂参数 s（未定义），
                    # 调用 log() 时会 NameError
                    print(f"  [API/{self.spec.name}] {msg}")

                def cleanup(self):
                    pass

            return TestAPI(spec)

        result = loader.load_all(api_factory=api_factory)

        print()
        print(f"结果: {result.get_summary()}")
        print(f"  发现: {result.total}")
        print(f"  加载: {result.loaded}")
        print(f"  激活: {result.activated}")
        print(f"  失败: {result.failed}")
        print(f"  禁用: {result.disabled}")
        print()

        if result.errors:
            print("错误列表:")
            for name, err in result.errors:
                print(f"  • {name}: {err}")
            print()

        # 打印完整信息
        print("=== PluginLoader 详情 ===")
        print(loader.dump())
        print()

        # 测试卸载
        print("=== 测试卸载 ===")
        loader.unload_plugin("demo_plugin")
        print(
            f"卸载后已激活: "
            f"{len(loader.get_activated_plugins())}"
        )
        print()

        # 测试重新加载
        print("=== 测试重新加载 ===")
        success = loader.reload_plugin("demo_plugin")
        print(f"重新加载结果: {success}")
        print()

        print(f"最终统计: {loader}")

    finally:
        # 清理
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print()
    print("测试完成。")
    sys.exit(0)