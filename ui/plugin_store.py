#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为插件市场模块，包含：
- PluginStoreDialog：插件市场对话框
- PluginStoreClient：插件市场客户端（远程/本地）
- PluginInfo：插件信息数据类
- PluginDetailDialog：插件详情对话框
- PluginCard：插件卡片控件
- PluginInstaller：插件安装器（下载/解压/校验）
- 在线插件注册表拉取
- 本地插件扫描与管理
- 分类与标签过滤
- 搜索与排序
- 评分与下载量
- 权限展示
- 依赖检查与安装
- 插件更新检测
- 插件卸载
- 缓存管理
- 安装进度显示
"""

import os
import sys
import json
import time
import shutil
import zipfile
import tempfile
import hashlib
import datetime
from typing import Optional, List, Dict, Any, Tuple, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from urllib.parse import urlparse

from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QToolButton, QLabel, QListWidget, QListWidgetItem,
    QComboBox, QCheckBox, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QTextEdit, QTextBrowser, QProgressBar, QMessageBox,
    QDialogButtonBox, QFrame, QScrollArea, QGridLayout,
    QSizePolicy, QApplication, QStyle, QMenu, QSplitter,
    QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView
)
from PyQt5.QtGui import (
    QIcon,
    QPixmap,
    QColor,
    QFont,
    QPainter,
    QBrush,
    QPen,
    QDesktopServices,
    QTextCursor,
)
from PyQt5.QtWidgets import QAction
from PyQt5.QtCore import (
    Qt, pyqtSignal, QTimer, QSize, QSettings, QUrl, QThread,
    QByteArray, QBuffer, QIODevice
)

from app.event_bus import (
    bus, StatusMessageEvent, NotificationEvent,
    PluginLoadedEvent, PluginUnloadedEvent, PluginErrorEvent
)


# ============================================================
# 常量
# ============================================================
APP_VERSION = "2.0.0"

# 插件市场注册表地址（镜像优先，国内可访问）
# 优先级：jsDelivr CDN > 用户自定义 > FALLBACK 列表
# 用户可在"插件市场"的"注册表 URL"输入框中覆盖此默认值
DEFAULT_REGISTRY_URL = (
    "https://cdn.jsdelivr.net/gh/"
    "qingcao-editor/plugins-registry@main/registry.json"
)

# 备用注册表地址（多路兜底）
FALLBACK_REGISTRY_URLS = [
    # GitHub 原始地址（国外/代理环境）
    "https://raw.githubusercontent.com/"
    "qingcao-editor/plugins-registry/main/registry.json",
    # Gitee 镜像（国内）
    "https://gitee.com/qingcao-editor/plugins-registry/raw/main/registry.json",
    # Statically CDN（第三兜底）
    "https://cdn.statically.io/gh/"
    "qingcao-editor/plugins-registry/main/registry.json",
]

# 插件目录
PLUGINS_DIR = "plugins"
THEMES_DIR = "themes"

# 缓存目录
CACHE_DIR = "data/plugin_cache"

# 缓存有效期（秒）
CACHE_TTL = 3600  # 1 小时

# 下载超时（秒）
DOWNLOAD_TIMEOUT = 5

# 插件类型
PLUGIN_TYPE_PLUGIN = "plugin"
PLUGIN_TYPE_THEME = "theme"
PLUGIN_TYPE_LANGUAGE = "language"
PLUGIN_TYPE_TOOL = "tool"

# 插件分类
CATEGORIES = [
    ("all", "全部"),
    ("featured", "精选"),
    ("installed", "已安装"),
    ("updates", "可更新"),
    ("editor", "编辑器增强"),
    ("language", "语言支持"),
    ("theme", "主题"),
    ("tool", "工具"),
    ("integration", "集成"),
    ("other", "其他"),
]

# 排序方式
SORT_OPTIONS = [
    ("downloads", "按下载量"),
    ("rating", "按评分"),
    ("updated", "按更新时间"),
    ("name", "按名称"),
    ("trending", "热门趋势"),
]

# 权限说明
PERMISSION_DESCRIPTIONS = {
    "filesystem": ("读写本地文件", "允许访问文件系统读写文件"),
    "network": ("访问网络", "允许发送网络请求"),
    "process": ("执行系统命令", "允许执行系统命令和子进程"),
    "clipboard": ("读写剪贴板", "允许读写系统剪贴板"),
    "dialog": ("显示对话框", "允许显示对话框和通知"),
    "editor_write": ("修改编辑器", "允许修改编辑器内容"),
    "editor_read": ("读取编辑器", "允许读取编辑器内容"),
    "terminal": ("使用终端", "允许使用集成终端"),
    "lsp": ("LSP 服务", "允许注册和使用 LSP 服务"),
    "debugger": ("调试器", "允许使用调试功能"),
}


# ============================================================
# 插件状态枚举
# ============================================================
class PluginState(Enum):
    """插件状态"""
    NOT_INSTALLED = auto()   # 未安装
    INSTALLED = auto()       # 已安装
    UPDATE_AVAILABLE = auto()  # 可更新
    DISABLED = auto()        # 已禁用
    ERROR = auto()           # 错误


# ============================================================
# 插件信息
# ============================================================
@dataclass
class PluginInfo:
    """
    插件信息。

    描述一个插件的所有元数据。
    """

    # 基本信息
    name: str = ""                          # 内部名称
    display_name: str = ""                  # 显示名称
    version: str = "0.0.0"                  # 版本
    description: str = ""                   # 简介
    long_description: str = ""              # 详细描述
    author: str = ""                        # 作者
    author_email: str = ""                  # 作者邮箱
    homepage: str = ""                      # 主页
    repository: str = ""                    # 仓库地址

    # 分类
    type: str = PLUGIN_TYPE_PLUGIN          # 类型
    category: str = "other"                 # 分类
    tags: List[str] = field(default_factory=list)  # 标签

    # 版本信息
    min_app_version: str = ""               # 最低应用版本
    max_app_version: str = ""               # 最高应用版本
    updated_at: str = ""                    # 更新时间

    # 安装信息
    download_url: str = ""                  # 下载地址
    update_url: str = ""                    # 更新检测地址
    file_hash: str = ""                     # 文件哈希（SHA256）
    file_size: int = 0                      # 文件大小

    # 依赖
    dependencies: List[str] = field(default_factory=list)  # Python 依赖
    plugin_dependencies: List[str] = field(default_factory=list)  # 插件依赖

    # 权限
    permissions: List[str] = field(default_factory=list)

    # 统计
    downloads: int = 0                      # 下载量
    rating: float = 0.0                     # 评分
    rating_count: int = 0                   # 评分数

    # 状态
    verified: bool = False                  # 是否认证
    featured: bool = False                  # 是否精选
    installed: bool = False                 # 是否已安装
    installed_version: str = ""             # 已安装版本
    enabled: bool = True                    # 是否启用
    state: PluginState = PluginState.NOT_INSTALLED

    # 本地信息
    local_path: str = ""                    # 本地路径
    installed_at: str = ""                  # 安装时间

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        d = asdict(self)
        d['state'] = self.state.name
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'PluginInfo':
        """从字典反序列化"""
        info = cls()
        for key, value in d.items():
            if hasattr(info, key):
                if key == 'state' and isinstance(value, str):
                    try:
                        setattr(info, key, PluginState[value])
                    except KeyError:
                        pass
                else:
                    setattr(info, key, value)
        return info

    @property
    def display_title(self) -> str:
        """显示标题"""
        return self.display_name or self.name

    @property
    def is_installed(self) -> bool:
        """是否已安装"""
        return self.state in (
            PluginState.INSTALLED,
            PluginState.UPDATE_AVAILABLE,
            PluginState.DISABLED,
        )

    @property
    def has_update(self) -> bool:
        """是否有更新"""
        return self.state == PluginState.UPDATE_AVAILABLE

    def get_dependency_status(self) -> Tuple[bool, List[str]]:
        """
        检查 Python 依赖是否满足。

        返回:
            (是否全部满足, 缺失的依赖列表)
        """
        missing = []
        for dep in self.dependencies:
            # 简化处理：仅检查包名（不验证版本）
            dep_name = dep.split('==')[0].split('>=')[0].split('<')[0]
            dep_name = dep_name.split('[')[0].strip()

            try:
                __import__(dep_name.replace('-', '_'))
            except ImportError:
                missing.append(dep)

        return (len(missing) == 0, missing)

    def __repr__(self) -> str:
        return (f"<PluginInfo {self.name} v{self.version} "
                f"state={self.state.name}>")


# ============================================================
# 插件市场客户端
# ============================================================
class PluginStoreClient:
    """
    插件市场客户端。

    负责:
    - 拉取远程注册表
    - 扫描本地已安装插件
    - 安装/卸载插件
    - 检查更新
    - 缓存管理
    """

    def __init__(self, registry_url: str = DEFAULT_REGISTRY_URL):
        self.registry_url = registry_url
        self.plugins_dir = PLUGINS_DIR
        self.themes_dir = THEMES_DIR
        self.cache_dir = CACHE_DIR

        # 缓存
        self._registry_cache: Optional[Dict[str, Any]] = None
        self._registry_cache_time: float = 0.0
        self._local_cache: Dict[str, PluginInfo] = {}

        # 确保目录存在
        os.makedirs(self.plugins_dir, exist_ok=True)
        os.makedirs(self.themes_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)

    # --------------------------------------------------------
    # 远程注册表
    # --------------------------------------------------------
    def fetch_registry(self, force: bool = False,
                       cache_first: bool = False
                       ) -> Optional[Dict[str, Any]]:
        """
        拉取远程注册表。

        参数:
            force: 强制刷新（忽略内存缓存 TTL）
            cache_first:
                True  → 只读内存 + 磁盘缓存，不发起网络请求；
                        网络拉取由调用方在后台线程用 force=True 处理。
                False → 完整流程：内存缓存 → 网络 → 磁盘缓存。

        返回:
            注册表数据或 None
        """
        # 检查内存缓存
        if not force and self._registry_cache is not None:
            elapsed = time.time() - self._registry_cache_time
            if elapsed < CACHE_TTL:
                return self._registry_cache

        # v2.9: cache_first 模式，只读磁盘缓存（不管 TTL），立即返回
        if cache_first:
            cached = self._load_cache_no_ttl()
            if cached:
                self._registry_cache = cached
                self._registry_cache_time = time.time()
                return cached
            # v3.0: cache_first 模式下，退回本地兜底文件
            fallback = self._load_fallback_registry()
            if fallback:
                self._registry_cache = fallback
                self._registry_cache_time = time.time()
                return fallback
            return None

        # 从远程拉取
        urls = [self.registry_url] + FALLBACK_REGISTRY_URLS

        for url in urls:
            try:
                data = self._download_json(url)
                if data:
                    self._registry_cache = data
                    self._registry_cache_time = time.time()
                    self._save_cache(data)
                    return data
            except Exception as e:
                print(f"[PluginStore] 拉取注册表失败 ({url}): {e}")
                continue

        # v3.0: 远程全部失败，先读磁盘缓存
        cached = self._load_cache()
        if cached:
            return cached

        # v3.0: 磁盘缓存也没有，读本地兜底文件
        fallback = self._load_fallback_registry()
        if fallback:
            print("[PluginStore] 使用本地兜底注册表")
            return fallback

        return None

    def _download_json(self, url: str) -> Optional[Dict[str, Any]]:
        """下载 JSON"""
        try:
            import requests
            resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
        except ImportError:
            # 使用 urllib 回退
            import urllib.request
            with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as f:
                return json.loads(f.read().decode('utf-8'))
        except Exception as e:
            print(f"[PluginStore] 下载失败: {e}")

        return None

    def _save_cache(self, data: Dict[str, Any]):
        """保存到磁盘缓存"""
        try:
            cache_file = os.path.join(self.cache_dir, "registry.json")
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'data': data,
                    'timestamp': time.time(),
                }, f, ensure_ascii=False)
        except Exception:
            pass

    def _load_fallback_registry(self) -> Optional[Dict[str, Any]]:
        """
        从本地兜底文件加载注册表（v3.0）。

        说明：
            远程注册表仓库可能不存在（qingcao-editor/plugins-registry），
            导致插件市场永远空列表。本方法从本地
            resources/registry_fallback.json 读取内置的插件推荐列表，
            作为离线兜底。
        """
        try:
            # 定位 resources/registry_fallback.json
            # 当前文件在 ui/ 下，根目录是上一级
            root = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
            fallback_path = os.path.join(
                root, "resources", "registry_fallback.json"
            )

            if not os.path.exists(fallback_path):
                return None

            with open(fallback_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return None

            # 打标记，便于 UI 区分
            data['_from_fallback'] = True
            return data

        except Exception as e:
            print(f"[PluginStore] 读取本地兜底注册表失败: {e}")
            return None

    def _load_cache_no_ttl(self) -> Optional[Dict[str, Any]]:
        """
        从磁盘缓存加载，忽略 TTL。

        v2.9 新增：用于 cache_first 模式。
        即使缓存过期很久也返回，让 UI 立即有数据可显示；
        真正的刷新由后台线程负责。
        """
        try:
            cache_file = os.path.join(self.cache_dir, "registry.json")
            if not os.path.exists(cache_file):
                return None

            with open(cache_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)

            data = cached.get('data')
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return None

    def _load_cache(self) -> Optional[Dict[str, Any]]:
        """从磁盘缓存加载（受 TTL 限制）"""
        try:
            cache_file = os.path.join(self.cache_dir, "registry.json")
            if not os.path.exists(cache_file):
                return None

            with open(cache_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)

            # 检查缓存时间
            timestamp = cached.get('timestamp', 0)
            if time.time() - timestamp > CACHE_TTL * 24:  # 缓存最长 1 天
                return None

            self._registry_cache = cached.get('data')
            self._registry_cache_time = timestamp
            return self._registry_cache

        except Exception:
            return None

    # --------------------------------------------------------
    # 获取插件列表
    # --------------------------------------------------------
    def get_all_plugins(self, force: bool = False) -> List[PluginInfo]:
        """
        获取所有插件信息（远程 + 本地合并）。

        返回:
            PluginInfo 列表
        """
        plugins: Dict[str, PluginInfo] = {}

        # 1. 从远程注册表加载
        registry = self.fetch_registry(force=force)
        if registry:
            items = registry.get('plugins', [])
            items.extend(registry.get('themes', []))

            for item in items:
                try:
                    info = PluginInfo.from_dict(item)
                    if info.name:
                        plugins[info.name] = info
                except Exception as e:
                    print(f"[PluginStore] 解析插件失败: {e}")

        # 2. 扫描本地已安装插件
        local_plugins = self.scan_local_plugins()
        for name, local_info in local_plugins.items():
            if name in plugins:
                # 合并：使用远程的元数据，但补充本地状态
                remote_info = plugins[name]
                remote_info.installed = True
                remote_info.installed_version = local_info.version
                remote_info.local_path = local_info.local_path
                remote_info.installed_at = local_info.installed_at
                remote_info.enabled = local_info.enabled

                # 检查更新
                if self._is_newer_version(local_info.version, remote_info.version):
                    remote_info.state = PluginState.UPDATE_AVAILABLE
                elif not local_info.enabled:
                    remote_info.state = PluginState.DISABLED
                else:
                    remote_info.state = PluginState.INSTALLED
            else:
                # 仅本地存在
                local_info.state = (PluginState.INSTALLED
                                     if local_info.enabled
                                     else PluginState.DISABLED)
                plugins[name] = local_info

        return list(plugins.values())

    # --------------------------------------------------------
    # 本地插件扫描
    # --------------------------------------------------------
    def scan_local_plugins(self) -> Dict[str, PluginInfo]:
        """扫描本地已安装插件"""
        plugins = {}

        # 扫描 plugins 目录
        if os.path.isdir(self.plugins_dir):
            for name in os.listdir(self.plugins_dir):
                path = os.path.join(self.plugins_dir, name)
                if not os.path.isdir(path):
                    continue
                if name.startswith('.'):
                    continue

                info = self._read_local_plugin(path, name)
                if info:
                    plugins[name] = info

        # 扫描 themes 目录
        if os.path.isdir(self.themes_dir):
            for filename in os.listdir(self.themes_dir):
                if filename.endswith('.json'):
                    theme_name = os.path.splitext(filename)[0]
                    path = os.path.join(self.themes_dir, filename)

                    info = PluginInfo(
                        name=theme_name,
                        display_name=theme_name,
                        type=PLUGIN_TYPE_THEME,
                        category='theme',
                        local_path=path,
                        installed=True,
                        enabled=True,
                        state=PluginState.INSTALLED,
                    )

                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            theme_data = json.load(f)
                        info.display_name = theme_data.get('name', theme_name)
                        info.description = theme_data.get('description', '')
                        info.author = theme_data.get('author', '')
                        info.version = theme_data.get('version', '1.0.0')
                    except Exception:
                        pass

                    plugins[f"theme.{theme_name}"] = info

        return plugins

    def _read_local_plugin(self, path: str, name: str) -> Optional[PluginInfo]:
        """读取本地插件信息"""
        manifest_path = os.path.join(path, 'plugin.json')
        if not os.path.exists(manifest_path):
            return None

        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)

            info = PluginInfo(
                name=manifest.get('name', name),
                display_name=manifest.get('display_name',
                                            manifest.get('name', name)),
                version=manifest.get('version', '0.0.0'),
                description=manifest.get('description', ''),
                author=manifest.get('author', ''),
                author_email=manifest.get('author_email', ''),
                homepage=manifest.get('homepage', ''),
                repository=manifest.get('repository', ''),
                type=manifest.get('type', PLUGIN_TYPE_PLUGIN),
                category=manifest.get('category', 'other'),
                tags=manifest.get('tags', []),
                dependencies=manifest.get('dependencies', []),
                plugin_dependencies=manifest.get('plugin_dependencies', []),
                permissions=manifest.get('permissions', []),
                local_path=path,
                installed=True,
                enabled=not manifest.get('disabled', False),
            )

            # 安装时间
            try:
                info.installed_at = datetime.datetime.fromtimestamp(
                    os.path.getmtime(manifest_path)
                ).isoformat()
            except Exception:
                pass

            return info

        except Exception as e:
            print(f"[PluginStore] 读取插件 {name} 失败: {e}")
            return None

    # --------------------------------------------------------
    # 安装/卸载
    # --------------------------------------------------------
    def install_plugin(self, info: PluginInfo,
                        progress_callback: Optional[Callable[[int, str], None]] = None,
                        install_deps: bool = True) -> Tuple[bool, str]:
        """
        安装插件。

        参数:
            info: 插件信息
            progress_callback: 进度回调 (百分比, 状态描述)
            install_deps: 是否安装 Python 依赖

        返回:
            (是否成功, 消息)
        """
        if progress_callback:
            progress_callback(0, "准备安装...")

        try:
            # 检查下载地址
            if not info.download_url:
                return (False, "缺少下载地址")

            # 下载
            if progress_callback:
                progress_callback(10, "下载中...")

            data = self._download_bytes(info.download_url)
            if data is None:
                return (False, "下载失败")

            # 校验哈希
            if info.file_hash:
                if progress_callback:
                    progress_callback(40, "校验中...")

                actual_hash = hashlib.sha256(data).hexdigest()
                if actual_hash.lower() != info.file_hash.lower():
                    return (False, "文件哈希校验失败")

            # 安装依赖
            if install_deps and info.dependencies:
                if progress_callback:
                    progress_callback(50, "安装依赖...")

                success, msg = self._install_dependencies(info.dependencies)
                if not success:
                    return (False, f"依赖安装失败: {msg}")

            # 解压安装
            if progress_callback:
                progress_callback(70, "解压中...")

            target_dir = (self.themes_dir if info.type == PLUGIN_TYPE_THEME
                          else self.plugins_dir)

            success, msg = self._extract_plugin(
                data, target_dir, info.name, info.type
            )
            if not success:
                return (False, msg)

            # 更新状态
            info.installed = True
            info.installed_version = info.version
            info.state = PluginState.INSTALLED

            if progress_callback:
                progress_callback(100, "安装完成")

            return (True, f"插件 {info.display_title} 安装成功")

        except Exception as e:
            return (False, f"安装异常: {e}")

    def uninstall_plugin(self, info: PluginInfo) -> Tuple[bool, str]:
        """
        卸载插件。

        返回:
            (是否成功, 消息)
        """
        try:
            if not info.local_path:
                return (False, "无法确定插件路径")

            if not os.path.exists(info.local_path):
                return (False, "插件目录不存在")

            # 备份
            backup_dir = os.path.join(
                self.cache_dir, "uninstalled",
                f"{info.name}_{int(time.time())}"
            )
            os.makedirs(os.path.dirname(backup_dir), exist_ok=True)

            try:
                shutil.move(info.local_path, backup_dir)
            except Exception:
                # 若移动失败，尝试直接删除
                if os.path.isdir(info.local_path):
                    shutil.rmtree(info.local_path)
                else:
                    os.remove(info.local_path)

            info.installed = False
            info.state = PluginState.NOT_INSTALLED

            return (True, f"插件 {info.display_title} 已卸载")

        except Exception as e:
            return (False, f"卸载失败: {e}")

    def update_plugin(self, info: PluginInfo,
                       progress_callback: Optional[Callable[[int, str], None]] = None
                       ) -> Tuple[bool, str]:
        """
        更新插件。

        返回:
            (是否成功, 消息)
        """
        if not info.has_update:
            return (False, "无需更新")

        # 先卸载再安装
        if info.local_path and os.path.exists(info.local_path):
            # 移动到备份
            backup_dir = os.path.join(
                self.cache_dir, "backup",
                f"{info.name}_{int(time.time())}"
            )
            os.makedirs(os.path.dirname(backup_dir), exist_ok=True)

            try:
                shutil.move(info.local_path, backup_dir)
            except Exception:
                pass

        # 安装新版本
        success, msg = self.install_plugin(info, progress_callback)

        if not success:
            # 回滚
            if os.path.exists(backup_dir):
                try:
                    shutil.move(backup_dir, info.local_path)
                except Exception:
                    pass

        return (success, msg)

    def toggle_plugin(self, info: PluginInfo, enabled: bool) -> bool:
        """启用/禁用插件"""
        try:
            if not info.local_path:
                return False

            manifest_path = os.path.join(info.local_path, 'plugin.json')
            if not os.path.exists(manifest_path):
                return False

            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)

            manifest['disabled'] = not enabled

            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)

            info.enabled = enabled
            info.state = (PluginState.INSTALLED if enabled
                          else PluginState.DISABLED)

            return True

        except Exception as e:
            print(f"[PluginStore] 切换插件状态失败: {e}")
            return False

    # --------------------------------------------------------
    # 更新检测
    # --------------------------------------------------------
    def check_updates(self) -> List[PluginInfo]:
        """
        检查所有已安装插件的更新。

        返回:
            可更新的插件列表
        """
        updates = []

        try:
            local_plugins = self.scan_local_plugins()

            for name, local_info in local_plugins.items():
                # 从远程获取最新版本
                remote_info = self._get_remote_plugin_info(name)
                if not remote_info:
                    continue

                if self._is_newer_version(local_info.version,
                                            remote_info.version):
                    remote_info.installed = True
                    remote_info.installed_version = local_info.version
                    remote_info.local_path = local_info.local_path
                    remote_info.state = PluginState.UPDATE_AVAILABLE
                    updates.append(remote_info)

        except Exception as e:
            print(f"[PluginStore] 检查更新失败: {e}")

        return updates

    def _get_remote_plugin_info(self, name: str) -> Optional[PluginInfo]:
        """获取远程插件信息"""
        registry = self.fetch_registry()
        if not registry:
            return None

        for item in registry.get('plugins', []):
            if item.get('name') == name:
                return PluginInfo.from_dict(item)

        for item in registry.get('themes', []):
            if item.get('name') == name:
                return PluginInfo.from_dict(item)

        return None

    @staticmethod
    def _is_newer_version(old_version: str, new_version: str) -> bool:
        """比较版本号"""
        try:
            def parse(v):
                # 移除预发布标识
                v = v.split('-')[0].split('+')[0]
                return [int(x) for x in v.split('.')]

            return parse(new_version) > parse(old_version)

        except Exception:
            return new_version > old_version

    # --------------------------------------------------------
    # 依赖安装
    # --------------------------------------------------------
    def _install_dependencies(self, dependencies: List[str]
                                ) -> Tuple[bool, str]:
        """安装 Python 依赖"""
        if not dependencies:
            return (True, "")

        try:
            import subprocess

            cmd = [sys.executable, '-m', 'pip', 'install']
            cmd.extend(dependencies)

            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=120
            )

            if result.returncode == 0:
                return (True, "")
            else:
                return (False, result.stderr[:200])

        except Exception as e:
            return (False, str(e))

    # --------------------------------------------------------
    # 下载
    # --------------------------------------------------------
    def _download_bytes(self, url: str) -> Optional[bytes]:
        """下载字节数据"""
        try:
            import requests
            resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
            if resp.status_code != 200:
                return None

            # 流式下载
            chunks = []
            for chunk in resp.iter_content(chunk_size=8192):
                chunks.append(chunk)

            return b''.join(chunks)

        except ImportError:
            import urllib.request
            try:
                with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as f:
                    return f.read()
            except Exception:
                return None
        except Exception as e:
            print(f"[PluginStore] 下载失败: {e}")
            return None

    # --------------------------------------------------------
    # 解压
    # --------------------------------------------------------
    def _extract_plugin(self, data: bytes, target_dir: str,
                          plugin_name: str, plugin_type: str
                          ) -> Tuple[bool, str]:
        """解压插件包"""
        try:
            # 写入临时文件
            with tempfile.NamedTemporaryFile(
                delete=False, suffix='.zip'
            ) as tmp:
                tmp.write(data)
                tmp_path = tmp.name

            try:
                # 解压
                with zipfile.ZipFile(tmp_path, 'r') as zf:
                    # 检查压缩包结构
                    names = zf.namelist()

                    # 判断是否包含顶层目录
                    top_level = set()
                    for name in names:
                        parts = name.split('/')
                        if parts:
                            top_level.add(parts[0])

                    # 如果只有一个顶层目录且是插件名，则解压后移动
                    if len(top_level) == 1:
                        top_dir = list(top_level)[0]
                        if top_dir == plugin_name or top_dir.endswith('/'):
                            # 直接解压到 target_dir
                            extract_dir = target_dir
                        else:
                            # 解压到临时目录，然后移动
                            extract_dir = tempfile.mkdtemp()
                            zf.extractall(extract_dir)
                            final_dir = os.path.join(target_dir, plugin_name)

                            if os.path.exists(final_dir):
                                shutil.rmtree(final_dir)

                            shutil.move(
                                os.path.join(extract_dir, top_dir),
                                final_dir
                            )
                            shutil.rmtree(extract_dir, ignore_errors=True)

                            os.unlink(tmp_path)
                            return (True, "")

                    # 解压到目标目录
                    if plugin_type == PLUGIN_TYPE_THEME:
                        # 主题文件是单个 JSON，直接复制到 themes 目录
                        for name in names:
                            if name.endswith('.json'):
                                with zf.open(name) as src:
                                    content = src.read()
                                theme_file = os.path.join(
                                    target_dir, os.path.basename(name)
                                )
                                with open(theme_file, 'wb') as dst:
                                    dst.write(content)
                    else:
                        # 插件解压到子目录
                        extract_to = os.path.join(target_dir, plugin_name)
                        if os.path.exists(extract_to):
                            shutil.rmtree(extract_to)
                        os.makedirs(extract_to, exist_ok=True)

                        for name in names:
                            # 安全检查：防止路径穿越
                            if '..' in name or name.startswith('/'):
                                continue
                            zf.extract(name, extract_to)

            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

            return (True, "")

        except zipfile.BadZipFile:
            return (False, "压缩包格式错误")
        except Exception as e:
            return (False, f"解压失败: {e}")

    # --------------------------------------------------------
    # 缓存
    # --------------------------------------------------------
    def clear_cache(self):
        """清空缓存"""
        self._registry_cache = None
        self._registry_cache_time = 0

        try:
            cache_file = os.path.join(self.cache_dir, "registry.json")
            if os.path.exists(cache_file):
                os.remove(cache_file)
        except Exception:
            pass

    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存信息"""
        info = {
            'cache_dir': self.cache_dir,
            'has_cache': self._registry_cache is not None,
            'cache_age_seconds': 0,
        }

        if self._registry_cache_time > 0:
            info['cache_age_seconds'] = int(
                time.time() - self._registry_cache_time
            )

        return info


# ============================================================
# 插件卡片
# ============================================================
class PluginCard(QFrame):
    """
    插件卡片控件。

    展示单个插件的信息，支持点击安装/卸载。
    """

    install_clicked = pyqtSignal(object)     # PluginInfo
    uninstall_clicked = pyqtSignal(object)
    update_clicked = pyqtSignal(object)
    detail_clicked = pyqtSignal(object)

    def __init__(self, info: PluginInfo, parent=None):
        super().__init__(parent)

        self.info = info
        self.setObjectName("PluginCard")
        self.setFrameShape(QFrame.StyledPanel)

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        """构建 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # 左侧：图标
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(40, 40)
        self.icon_label.setAlignment(Qt.AlignCenter)

        # 根据类型选择图标
        if self.info.type == PLUGIN_TYPE_THEME:
            self.icon_label.setText("🎨")
        elif self.info.type == PLUGIN_TYPE_LANGUAGE:
            self.icon_label.setText("🌐")
        elif self.info.type == PLUGIN_TYPE_TOOL:
            self.icon_label.setText("🔧")
        else:
            self.icon_label.setText("🧩")

        self.icon_label.setStyleSheet(
            "font-size: 24px; background-color: #2d2d2d; "
            "border-radius: 6px;"
        )
        layout.addWidget(self.icon_label)

        # 中间：信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        # 标题行
        title_layout = QHBoxLayout()
        title_layout.setSpacing(6)

        self.title_label = QLabel(self.info.display_title)
        self.title_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #d4d4d4;"
        )
        title_layout.addWidget(self.title_label)

        # 版本
        self.version_label = QLabel(f"v{self.info.version}")
        self.version_label.setStyleSheet(
            "font-size: 11px; color: #888;"
        )
        title_layout.addWidget(self.version_label)

        # 认证标记
        if self.info.verified:
            verified_label = QLabel("✅")
            verified_label.setToolTip("已验证插件")
            title_layout.addWidget(verified_label)

        # 精选标记
        if self.info.featured:
            featured_label = QLabel("⭐")
            featured_label.setToolTip("精选插件")
            title_layout.addWidget(featured_label)

        title_layout.addStretch()
        info_layout.addLayout(title_layout)

        # 描述
        self.desc_label = QLabel(self.info.description or "（无描述）")
        self.desc_label.setStyleSheet("font-size: 11px; color: #888;")
        self.desc_label.setWordWrap(True)
        info_layout.addWidget(self.desc_label)

        # 底部：作者、统计
        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(10)

        if self.info.author:
            author_label = QLabel(f"👤 {self.info.author}")
            author_label.setStyleSheet("font-size: 10px; color: #666;")
            meta_layout.addWidget(author_label)

        if self.info.downloads > 0:
            downloads_label = QLabel(f"⬇ {self._format_number(self.info.downloads)}")
            downloads_label.setStyleSheet("font-size: 10px; color: #666;")
            meta_layout.addWidget(downloads_label)

        if self.info.rating > 0:
            stars = "★" * int(self.info.rating) + "☆" * (5 - int(self.info.rating))
            rating_label = QLabel(f"{stars} {self.info.rating:.1f}")
            rating_label.setStyleSheet("font-size: 10px; color: #f0ad4e;")
            meta_layout.addWidget(rating_label)

        meta_layout.addStretch()
        info_layout.addLayout(meta_layout)

        layout.addLayout(info_layout, 1)

        # 右侧：操作按钮
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(4)
        btn_layout.setAlignment(Qt.AlignVCenter)

        self.action_btn = QPushButton()
        self.action_btn.setFixedWidth(80)
        self.action_btn.clicked.connect(self._on_action_clicked)
        btn_layout.addWidget(self.action_btn)

        self.detail_btn = QToolButton()
        self.detail_btn.setText("ℹ")
        self.detail_btn.setFixedSize(24, 24)
        self.detail_btn.setToolTip("查看详情")
        self.detail_btn.clicked.connect(
            lambda: self.detail_clicked.emit(self.info)
        )
        btn_layout.addWidget(self.detail_btn)

        layout.addLayout(btn_layout)

        # 更新按钮状态
        self._update_action_button()

    def _update_action_button(self):
        """更新操作按钮状态"""
        state = self.info.state

        if state == PluginState.NOT_INSTALLED:
            self.action_btn.setText("安装")
            self.action_btn.setStyleSheet(
                "background-color: #0e639c; color: white; "
                "border: none; border-radius: 3px; padding: 4px;"
            )
            self.action_btn.setEnabled(True)

        elif state == PluginState.INSTALLED:
            self.action_btn.setText("卸载")
            self.action_btn.setStyleSheet(
                "background-color: #5a5a5a; color: white; "
                "border: none; border-radius: 3px; padding: 4px;"
            )
            self.action_btn.setEnabled(True)

        elif state == PluginState.UPDATE_AVAILABLE:
            self.action_btn.setText("更新")
            self.action_btn.setStyleSheet(
                "background-color: #7ec850; color: white; "
                "border: none; border-radius: 3px; padding: 4px; "
                "font-weight: bold;"
            )
            self.action_btn.setEnabled(True)

        elif state == PluginState.DISABLED:
            self.action_btn.setText("启用")
            self.action_btn.setStyleSheet(
                "background-color: #f0ad4e; color: white; "
                "border: none; border-radius: 3px; padding: 4px;"
            )
            self.action_btn.setEnabled(True)

        else:
            self.action_btn.setText("不可用")
            self.action_btn.setEnabled(False)

    def _on_action_clicked(self):
        """按钮点击"""
        state = self.info.state

        if state == PluginState.NOT_INSTALLED:
            self.install_clicked.emit(self.info)
        elif state == PluginState.INSTALLED:
            self.uninstall_clicked.emit(self.info)
        elif state == PluginState.UPDATE_AVAILABLE:
            self.update_clicked.emit(self.info)
        elif state == PluginState.DISABLED:
            self.install_clicked.emit(self.info)  # 复用为启用

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QFrame#PluginCard {
                background-color: #2d2d2d;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
            }
            QFrame#PluginCard:hover {
                background-color: #333333;
                border-color: #4c4c4c;
            }
            QFrame#PluginCard QLabel {
                background-color: transparent;
            }
        """)

    @staticmethod
    def _format_number(n: int) -> str:
        """格式化数字"""
        if n < 1000:
            return str(n)
        elif n < 1000000:
            return f"{n / 1000:.1f}K"
        else:
            return f"{n / 1000000:.1f}M"

    def refresh(self):
        """刷新卡片"""
        self._update_action_button()


# ============================================================
# 远程注册表异步拉取 Worker
# ============================================================
class RegistryFetchWorker(QThread):
    """
    后台拉取远程注册表。

    修复说明（异步加载）:
        避免在 QTimer.singleShot 回调中同步执行网络请求，
        导致 Qt 事件循环阻塞、窗口"未响应"。

    信号：
        finished(dict): 成功拉取到注册表
        failed(str):    拉取失败（已 fallback 到磁盘缓存）
    """

    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, client, force: bool = False, parent=None):
        super().__init__(parent)
        self.client = client
        self.force = force

    def run(self):
        try:
            registry = self.client.fetch_registry(force=self.force)
            if registry:
                self.finished.emit(registry)
            else:
                self.failed.emit("无法获取注册表（网络与缓存均失败）")
        except Exception as e:
            self.failed.emit(str(e))


# ============================================================
# 插件详情对话框
# ============================================================
class PluginDetailDialog(QDialog):
    """
    插件详情对话框。

    显示插件的完整信息。
    """

    install_clicked = pyqtSignal(object)
    uninstall_clicked = pyqtSignal(object)
    update_clicked = pyqtSignal(object)

    def __init__(self, info: PluginInfo, parent=None):
        super().__init__(parent)

        self.info = info
        self.setWindowTitle(f"插件详情 - {info.display_title}")
        self.resize(600, 500)

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 头部
        header = self._build_header()
        layout.addWidget(header)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #3c3c3c;")
        layout.addWidget(line)

        # 详细内容
        content = QTextBrowser()
        content.setOpenExternalLinks(True)
        content.setStyleSheet("""
            QTextBrowser {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
            }
        """)

        html = self._build_html()
        content.setHtml(html)
        layout.addWidget(content, 1)

        # 底部按钮
        btn_layout = QHBoxLayout()

        # 操作按钮
        self.action_btn = QPushButton()
        self.action_btn.setFixedWidth(100)
        self.action_btn.clicked.connect(self._on_action_clicked)
        btn_layout.addWidget(self.action_btn)

        btn_layout.addStretch()

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        self._update_action_button()

    def _build_header(self) -> QWidget:
        """构建头部"""
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)

        # 图标
        icon_label = QLabel()
        icon_label.setFixedSize(64, 64)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setText("🧩")
        icon_label.setStyleSheet(
            "font-size: 40px; background-color: #2d2d2d; "
            "border-radius: 8px;"
        )
        layout.addWidget(icon_label)

        # 信息
        info_layout = QVBoxLayout()

        name_label = QLabel(self.info.display_title)
        name_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #d4d4d4;"
        )
        info_layout.addWidget(name_label)

        meta_parts = [f"v{self.info.version}"]

        if self.info.author:
            meta_parts.append(f"by {self.info.author}")

        if self.info.updated_at:
            try:
                date = self.info.updated_at[:10]
                meta_parts.append(f"更新于 {date}")
            except Exception:
                pass

        meta_label = QLabel(" · ".join(meta_parts))
        meta_label.setStyleSheet("color: #888; font-size: 12px;")
        info_layout.addWidget(meta_label)

        # 统计
        stats_layout = QHBoxLayout()

        if self.info.downloads > 0:
            downloads = QLabel(f"⬇ {self.info.downloads:,} 次下载")
            downloads.setStyleSheet("color: #666; font-size: 11px;")
            stats_layout.addWidget(downloads)

        if self.info.rating > 0:
            stars = "★" * int(self.info.rating) + "☆" * (5 - int(self.info.rating))
            rating = QLabel(f"{stars} ({self.info.rating_count})")
            rating.setStyleSheet("color: #f0ad4e; font-size: 11px;")
            stats_layout.addWidget(rating)

        stats_layout.addStretch()
        info_layout.addLayout(stats_layout)

        layout.addLayout(info_layout, 1)

        return header

    def _build_html(self) -> str:
        """构建详情 HTML"""
        html_parts = []

        html_parts.append("<style>")
        html_parts.append("""
            h3 { color: #7ec850; font-size: 14px;
                 border-bottom: 1px solid #3c3c3c;
                 padding-bottom: 4px; margin-top: 16px; }
            p { margin: 4px 0; }
            ul { margin: 4px 0; padding-left: 20px; }
            code { background-color: #2d2d2d; padding: 1px 4px;
                   border-radius: 3px; font-family: Consolas, monospace;
                   color: #ce9178; }
            .permission { color: #f0ad4e; }
            .dep { color: #9cdcfe; }
            .missing { color: #f14c4c; }
        """)
        html_parts.append("</style>")

        # 描述
        if self.info.description:
            html_parts.append(f"<p>{self.info.description}</p>")

        # 详细描述
        if self.info.long_description:
            html_parts.append("<h3>详细说明</h3>")
            html_parts.append(f"<p>{self.info.long_description}</p>")

        # 权限
        if self.info.permissions:
            html_parts.append("<h3>权限要求</h3>")
            html_parts.append("<ul>")
            for perm in self.info.permissions:
                desc = PERMISSION_DESCRIPTIONS.get(perm)
                if desc:
                    html_parts.append(
                        f'<li class="permission">🔑 {desc[0]} - {desc[1]}</li>'
                    )
                else:
                    html_parts.append(f'<li class="permission">🔑 {perm}</li>')
            html_parts.append("</ul>")

        # 依赖
        if self.info.dependencies:
            html_parts.append("<h3>Python 依赖</h3>")
            satisfied, missing = self.info.get_dependency_status()

            html_parts.append("<ul>")
            for dep in self.info.dependencies:
                if dep in missing:
                    html_parts.append(
                        f'<li class="missing">✗ {dep} (未安装)</li>'
                    )
                else:
                    html_parts.append(f'<li class="dep">✓ {dep}</li>')
            html_parts.append("</ul>")

        # 插件依赖
        if self.info.plugin_dependencies:
            html_parts.append("<h3>插件依赖</h3>")
            html_parts.append("<ul>")
            for dep in self.info.plugin_dependencies:
                html_parts.append(f"<li>🧩 {dep}</li>")
            html_parts.append("</ul>")

        # 链接
        links = []
        if self.info.homepage:
            links.append(f'<a href="{self.info.homepage}">🏠 主页</a>')
        if self.info.repository:
            links.append(f'<a href="{self.info.repository}">📦 仓库</a>')

        if links:
            html_parts.append("<h3>相关链接</h3>")
            html_parts.append("<p>" + " · ".join(links) + "</p>")

        # 技术信息
        html_parts.append("<h3>技术信息</h3>")
        html_parts.append("<ul>")
        html_parts.append(f"<li>类型: {self.info.type}</li>")
        html_parts.append(f"<li>分类: {self.info.category}</li>")
        html_parts.append(f"<li>版本: {self.info.version}</li>")

        if self.info.file_size > 0:
            size_str = self._format_size(self.info.file_size)
            html_parts.append(f"<li>大小: {size_str}</li>")

        if self.info.min_app_version:
            html_parts.append(f"<li>最低版本: {self.info.min_app_version}</li>")

        if self.info.verified:
            html_parts.append("<li>✅ 已验证</li>")

        if self.info.tags:
            tags_str = ", ".join(self.info.tags)
            html_parts.append(f"<li>标签: {tags_str}</li>")

        html_parts.append("</ul>")

        return "".join(html_parts)

    def _update_action_button(self):
        """更新操作按钮"""
        state = self.info.state

        if state == PluginState.NOT_INSTALLED:
            self.action_btn.setText("安装")
            self.action_btn.setStyleSheet(
                "background-color: #0e639c; color: white; "
                "border: none; border-radius: 4px; padding: 6px 12px;"
            )
            self.action_btn.setEnabled(True)

        elif state == PluginState.INSTALLED:
            self.action_btn.setText("卸载")
            self.action_btn.setEnabled(True)

        elif state == PluginState.UPDATE_AVAILABLE:
            self.action_btn.setText("更新")
            self.action_btn.setStyleSheet(
                "background-color: #7ec850; color: white; "
                "border: none; border-radius: 4px; padding: 6px 12px;"
            )
            self.action_btn.setEnabled(True)

        elif state == PluginState.DISABLED:
            self.action_btn.setText("启用")
            self.action_btn.setEnabled(True)

        else:
            self.action_btn.setText("不可用")
            self.action_btn.setEnabled(False)

    def _on_action_clicked(self):
        """操作按钮点击"""
        state = self.info.state

        if state == PluginState.NOT_INSTALLED:
            self.install_clicked.emit(self.info)
        elif state == PluginState.INSTALLED:
            self.uninstall_clicked.emit(self.info)
        elif state == PluginState.UPDATE_AVAILABLE:
            self.update_clicked.emit(self.info)
        elif state == PluginState.DISABLED:
            self.install_clicked.emit(self.info)

    @staticmethod
    def _format_size(size: int) -> str:
        """格式化文件大小"""
        if size < 1024:
            return f"{size} 字节"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / 1024 / 1024:.1f} MB"


# ============================================================
# 安装进度对话框
# ============================================================
class InstallProgressDialog(QDialog):
    """插件安装进度对话框"""

    def __init__(self, plugin_name: str, parent=None):
        super().__init__(parent)

        self.setWindowTitle("安装插件")
        self.setFixedSize(400, 150)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowContextHelpButtonHint
        )

        self._cancelled = False

        layout = QVBoxLayout(self)

        # 插件名
        name_label = QLabel(f"正在安装: {plugin_name}")
        name_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(name_label)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        # 状态
        self.status_label = QLabel("准备中...")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.status_label)

        # 取消按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    def _on_cancel(self):
        """取消"""
        self._cancelled = True
        self.reject()

    def update_progress(self, value: int, status: str):
        """更新进度"""
        self.progress_bar.setValue(value)
        self.status_label.setText(status)

    def is_cancelled(self) -> bool:
        """是否已取消"""
        return self._cancelled


# ============================================================
# 插件市场对话框
# ============================================================
class PluginStoreDialog(QDialog):
    """
    插件市场对话框。

    主界面，包含:
    - 搜索栏
    - 分类筛选
    - 排序选项
    - 插件卡片列表
    - 详情对话框
    - 安装/卸载/更新操作

    信号:
        plugin_installed(str): 插件安装完成（插件名）
        plugin_uninstalled(str): 插件卸载完成（插件名）
        plugin_updated(str): 插件更新完成（插件名）
    """

    plugin_installed = pyqtSignal(str)
    plugin_uninstalled = pyqtSignal(str)
    plugin_updated = pyqtSignal(str)

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent or main_window)

        self.main_window = main_window
        self.setWindowTitle("青草插件市场")
        self.resize(800, 600)

        # 客户端
        self.client = PluginStoreClient()

        # v2.9: 从 QSettings 加载自定义注册表 URL
        # 允许用户覆盖默认注册表地址（适配网络环境）
        self._settings = QSettings("QingCao", "PluginStore")
        custom_url = self._settings.value(
            "registry_url", "", type=str
        )
        if custom_url:
            self.client.registry_url = custom_url

        # 插件列表
        self._all_plugins: List[PluginInfo] = []
        self._filtered_plugins: List[PluginInfo] = []

        # 设置
        self._settings = QSettings("QingCao", "PluginStore")
        self._current_category = "all"
        self._current_sort = "downloads"
        self._search_text = ""

        # 构建 UI
        self._build_ui()

        # 加载插件
        QTimer.singleShot(100, self._load_plugins)

    # --------------------------------------------------------
    # UI 构建
    # --------------------------------------------------------
    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 顶部工具栏
        toolbar = self._build_toolbar()
        layout.addWidget(toolbar)

        # 中间：插件列表
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #1e1e1e;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
            }
            QScrollBar:vertical {
                background-color: #2d2d2d;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #555;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #777;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

        # 插件容器
        self.plugins_container = QWidget()
        self.plugins_layout = QVBoxLayout(self.plugins_container)
        self.plugins_layout.setContentsMargins(8, 8, 8, 8)
        self.plugins_layout.setSpacing(6)
        self.plugins_layout.addStretch()

        self.scroll_area.setWidget(self.plugins_container)
        layout.addWidget(self.scroll_area, 1)

        # 状态栏
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            "color: #888; font-size: 11px; padding: 4px;"
        )
        layout.addWidget(self.status_label)

        # 底部按钮
        bottom = QHBoxLayout()

        self.check_updates_btn = QPushButton("🔍 检查更新")
        self.check_updates_btn.clicked.connect(self._check_updates)
        bottom.addWidget(self.check_updates_btn)

        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.clicked.connect(self._refresh_plugins)
        bottom.addWidget(self.refresh_btn)

        bottom.addStretch()

        self.install_local_btn = QPushButton("📦 安装本地插件")
        self.install_local_btn.clicked.connect(self._install_local)
        bottom.addWidget(self.install_local_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)

        layout.addLayout(bottom)

        # 应用样式
        self._apply_style()

    def _build_toolbar(self) -> QWidget:
        """构建工具栏（v2.9：两行布局）"""
        toolbar = QWidget()
        outer = QVBoxLayout(toolbar)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # ====================================================
        # v2.9: 注册表 URL 配置行
        # ====================================================
        url_row = QHBoxLayout()
        url_row.setContentsMargins(0, 0, 0, 0)
        url_row.setSpacing(6)

        url_label = QLabel("注册表 URL:")
        url_label.setStyleSheet("color: #888; font-size: 11px;")
        url_row.addWidget(url_label)

        self.registry_url_edit = QLineEdit()
        self.registry_url_edit.setPlaceholderText(
            "留空使用默认（jsDelivr CDN）"
        )
        self.registry_url_edit.setText(
            self._settings.value("registry_url", "", type=str)
        )
        self.registry_url_edit.setClearButtonEnabled(True)
        self.registry_url_edit.returnPressed.connect(
            self._on_registry_url_changed
        )
        url_row.addWidget(self.registry_url_edit, 1)

        self.apply_url_btn = QPushButton("应用并刷新")
        self.apply_url_btn.clicked.connect(
            self._on_registry_url_changed
        )
        url_row.addWidget(self.apply_url_btn)

        reset_url_btn = QPushButton("重置")
        reset_url_btn.setToolTip("恢复默认注册表地址")
        reset_url_btn.clicked.connect(self._on_reset_registry_url)
        url_row.addWidget(reset_url_btn)

        outer.addLayout(url_row)

        # ====================================================
        # 原有的搜索/分类/排序行
        # ====================================================
        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(8)

        # 临时把 layout 指向 filter_row，后面的 addWidget 会加到这一行
        layout = filter_row

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索插件...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_edit, 1)

        # 分类下拉
        self.category_combo = QComboBox()
        for key, name in CATEGORIES:
            self.category_combo.addItem(name, key)
        self.category_combo.currentIndexChanged.connect(
            self._on_category_changed
        )
        layout.addWidget(self.category_combo)

        # 排序下拉
        self.sort_combo = QComboBox()
        for key, name in SORT_OPTIONS:
            self.sort_combo.addItem(name, key)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        layout.addWidget(self.sort_combo)

        # 把 filter_row 加到 toolbar 的 outer 布局
        outer.addLayout(filter_row)

        return toolbar

    # ========================================================
    # v2.9: 注册表 URL 处理
    # ========================================================
    def _on_registry_url_changed(self):
        """用户点击"应用并刷新"或按回车"""
        url = self.registry_url_edit.text().strip()

        # 简单校验
        if url and not (url.startswith("http://")
                        or url.startswith("https://")):
            QMessageBox.warning(
                self, "URL 格式错误",
                "注册表 URL 必须以 http:// 或 https:// 开头"
            )
            return

        # 保存到 QSettings
        if url:
            self._settings.setValue("registry_url", url)
        else:
            self._settings.remove("registry_url")

        # 应用到 client
        if url:
            self.client.registry_url = url
        else:
            # 恢复默认
            self.client.registry_url = DEFAULT_REGISTRY_URL

        # 清缓存并刷新
        self.client.clear_cache()
        self._load_plugins(force=True)

        QMessageBox.information(
            self, "已应用",
            f"注册表地址已更新：\n{url or '(默认)'}\n\n"
            f"正在重新拉取插件列表..."
        )

    def _on_reset_registry_url(self):
        """重置为默认 URL"""
        self.registry_url_edit.clear()
        self._settings.remove("registry_url")
        self.client.registry_url = DEFAULT_REGISTRY_URL
        self.client.clear_cache()
        self._load_plugins(force=True)

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #007acc;
            }
            QComboBox {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
                min-width: 120px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: #d4d4d4;
                selection-background-color: #094771;
                border: 1px solid #3c3c3c;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0a4d7a;
            }
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #666;
            }
        """)

    # --------------------------------------------------------
    # 加载插件
    # --------------------------------------------------------
    def _load_plugins(self, force: bool = False):
        """加载插件列表（异步）。

        修复说明（异步加载）:
            原实现同步调用 get_all_plugins()，内部 fetch_registry()
            会顺序请求主 URL + fallback URL，每次 requests.get()
            超时 30 秒 → 主线程被阻塞 30~60 秒，窗口"未响应"。

            新实现分两步：
              1. 立即同步加载本地插件（毫秒级）并显示
              2. 后台线程拉远程注册表，完成后通过信号回传刷新
        """
        # ---- 第 1 步：立即显示本地插件 ----
        self.status_label.setText("正在扫描本地插件...")
        self.refresh_btn.setEnabled(False)

        try:
            # v2.9: 先用 cache_first 快速合并（本地 + 磁盘缓存）
            # 不发起网络请求，确保 UI 立即有内容
            try:
                fast_registry = self.client.fetch_registry(
                    force=False, cache_first=True
                )
            except Exception:
                fast_registry = None

            if fast_registry:
                # 有磁盘缓存：一次性合并远程 + 本地
                self._all_plugins = self.client.get_all_plugins(
                    force=False
                )
                self.status_label.setText(
                    f"已从缓存加载 {len(self._all_plugins)} 个插件，"
                    f"后台刷新中..."
                )
            else:
                # 无缓存：只显示本地
                local_plugins = self.client.scan_local_plugins()
                self._all_plugins = list(local_plugins.values())
                for p in self._all_plugins:
                    p.state = PluginState.INSTALLED
                self.status_label.setText(
                    f"已加载 {len(self._all_plugins)} 个本地插件，"
                    f"正在拉取远程列表..."
                )
            self._apply_filters()

        except Exception as e:
            print(f"[PluginStore] 加载插件失败: {e}")
            self._all_plugins = []
            self._apply_filters()

        # ---- 第 2 步：后台拉远程 ----
        # 用 QThread 避免阻塞主线程。
        self._registry_worker = RegistryFetchWorker(
            self.client, force=force, parent=self
        )
        self._registry_worker.finished.connect(
            self._on_registry_loaded
        )
        self._registry_worker.failed.connect(
            self._on_registry_failed
        )
        self._registry_worker.start()

    def _on_registry_loaded(self, registry: dict):
        """后台拉取远程注册表成功"""
        try:
            # 重新合并远程 + 本地
            self._all_plugins = self.client.get_all_plugins(force=False)
            self._apply_filters()
            self.status_label.setText(
                f"共 {len(self._all_plugins)} 个插件"
            )
        except Exception as e:
            print(f"[PluginStore] 合并远程插件失败: {e}")
        finally:
            self.refresh_btn.setEnabled(True)

    def _on_registry_failed(self, error: str):
        """后台拉取远程注册表失败（已 fallback 到本地）"""
        print(f"[PluginStore] 远程注册表不可用: {error}")
        self.status_label.setText(
            f"共 {len(self._all_plugins)} 个插件（离线模式）"
        )
        self.refresh_btn.setEnabled(True)

    def _refresh_plugins(self):
        """刷新插件列表"""
        self.client.clear_cache()
        self._load_plugins(force=True)

    # --------------------------------------------------------
    # 过滤与排序
    # --------------------------------------------------------
    def _on_search_changed(self, text: str):
        """搜索变化"""
        self._search_text = text.strip().lower()
        self._apply_filters()

    def _on_category_changed(self, index: int):
        """分类变化"""
        self._current_category = self.category_combo.currentData()
        self._apply_filters()

    def _on_sort_changed(self, index: int):
        """排序变化"""
        self._current_sort = self.sort_combo.currentData()
        self._apply_filters()

    def _apply_filters(self):
        """应用过滤和排序"""
        plugins = list(self._all_plugins)

        # 分类过滤
        if self._current_category == "installed":
            plugins = [p for p in plugins if p.is_installed]
        elif self._current_category == "updates":
            plugins = [p for p in plugins if p.has_update]
        elif self._current_category == "featured":
            plugins = [p for p in plugins if p.featured]
        elif self._current_category != "all":
            plugins = [p for p in plugins
                       if p.category == self._current_category]

        # 搜索过滤
        if self._search_text:
            text = self._search_text
            plugins = [
                p for p in plugins
                if (text in p.name.lower()
                    or text in p.display_name.lower()
                    or text in p.description.lower()
                    or any(text in tag.lower() for tag in p.tags))
            ]

        # 排序
        if self._current_sort == "downloads":
            plugins.sort(key=lambda p: p.downloads, reverse=True)
        elif self._current_sort == "rating":
            plugins.sort(key=lambda p: p.rating, reverse=True)
        elif self._current_sort == "updated":
            plugins.sort(key=lambda p: p.updated_at or "", reverse=True)
        elif self._current_sort == "name":
            plugins.sort(key=lambda p: p.display_title.lower())
        elif self._current_sort == "trending":
            # 按下载量 + 评分综合
            plugins.sort(
                key=lambda p: p.downloads * 0.7 + p.rating * 100 * 0.3,
                reverse=True
            )

        self._filtered_plugins = plugins
        self._render_plugins()

    def _render_plugins(self):
        """渲染插件列表"""
        # 清空现有卡片
        while self.plugins_layout.count() > 1:
            item = self.plugins_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 无结果
        if not self._filtered_plugins:
            empty_label = QLabel("没有找到匹配的插件")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(
                "color: #888; font-size: 14px; padding: 40px;"
            )
            self.plugins_layout.insertWidget(0, empty_label)
            self.status_label.setText("无结果")
            return

        # 添加卡片
        for plugin in self._filtered_plugins:
            card = PluginCard(plugin)
            card.install_clicked.connect(self._on_install)
            card.uninstall_clicked.connect(self._on_uninstall)
            card.update_clicked.connect(self._on_update)
            card.detail_clicked.connect(self._on_show_detail)

            self.plugins_layout.insertWidget(
                self.plugins_layout.count() - 1, card
            )

        self.status_label.setText(
            f"显示 {len(self._filtered_plugins)} / {len(self._all_plugins)} 个插件"
        )

    # --------------------------------------------------------
    # 操作处理
    # --------------------------------------------------------
    def _on_install(self, info: PluginInfo):
        """安装插件"""
        # 检查依赖
        satisfied, missing = info.get_dependency_status()
        if not satisfied:
            msg = (f"以下 Python 依赖未安装：\n\n"
                   + "\n".join(f"• {d}" for d in missing)
                   + "\n\n是否尝试自动安装？")

            reply = QMessageBox.question(
                self, "缺少依赖", msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply != QMessageBox.Yes:
                return

        # 显示进度
        progress_dlg = InstallProgressDialog(info.display_title, self)
        progress_dlg.show()

        def on_progress(value: int, status: str):
            progress_dlg.update_progress(value, status)
            QApplication.processEvents()

            if progress_dlg.is_cancelled():
                return

        # 执行安装
        success, msg = self.client.install_plugin(
            info, progress_callback=on_progress
        )

        progress_dlg.close()

        if success:
            QMessageBox.information(self, "安装成功", msg)
            self.plugin_installed.emit(info.name)

            # 刷新列表
            self._load_plugins()

            # 通知用户重启
            QMessageBox.information(
                self, "提示",
                "插件已安装，重启编辑器后生效。"
            )
        else:
            QMessageBox.critical(self, "安装失败", msg)

    def _on_uninstall(self, info: PluginInfo):
        """卸载插件"""
        reply = QMessageBox.question(
            self, "确认卸载",
            f"确定要卸载插件 {info.display_title} 吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        success, msg = self.client.uninstall_plugin(info)

        if success:
            QMessageBox.information(self, "卸载成功", msg)
            self.plugin_uninstalled.emit(info.name)
            self._load_plugins()
        else:
            QMessageBox.critical(self, "卸载失败", msg)

    def _on_update(self, info: PluginInfo):
        """更新插件"""
        progress_dlg = InstallProgressDialog(info.display_title, self)
        progress_dlg.show()

        def on_progress(value: int, status: str):
            progress_dlg.update_progress(value, status)
            QApplication.processEvents()

        success, msg = self.client.update_plugin(
            info, progress_callback=on_progress
        )

        progress_dlg.close()

        if success:
            QMessageBox.information(self, "更新成功", msg)
            self.plugin_updated.emit(info.name)
            self._load_plugins()
        else:
            QMessageBox.critical(self, "更新失败", msg)

    def _on_show_detail(self, info: PluginInfo):
        """显示详情"""
        dlg = PluginDetailDialog(info, self)
        dlg.install_clicked.connect(self._on_install)
        dlg.uninstall_clicked.connect(self._on_uninstall)
        dlg.update_clicked.connect(self._on_update)
        dlg.exec()

    # --------------------------------------------------------
    # 检查更新
    # --------------------------------------------------------
    def _check_updates(self):
        """检查所有插件的更新"""
        self.status_label.setText("正在检查更新...")
        self.check_updates_btn.setEnabled(False)

        try:
            updates = self.client.check_updates()

            if updates:
                msg = f"发现 {len(updates)} 个插件可更新：\n\n"
                msg += "\n".join(
                    f"• {p.display_title} "
                    f"({p.installed_version} → {p.version})"
                    for p in updates[:10]
                )
                if len(updates) > 10:
                    msg += f"\n... 及其他 {len(updates) - 10} 个"

                reply = QMessageBox.question(
                    self, "检查更新", msg + "\n\n是否全部更新？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )

                if reply == QMessageBox.Yes:
                    self._update_all(updates)
            else:
                QMessageBox.information(self, "检查更新", "所有插件都是最新的")

        except Exception as e:
            QMessageBox.warning(self, "检查更新失败", str(e))

        finally:
            self.check_updates_btn.setEnabled(True)
            self.status_label.setText("")

    def _update_all(self, updates: List[PluginInfo]):
        """批量更新"""
        success_count = 0
        failed_count = 0

        progress_dlg = InstallProgressDialog(
            f"{len(updates)} 个插件", self
        )
        progress_dlg.show()

        for i, info in enumerate(updates):
            if progress_dlg.is_cancelled():
                break

            progress_dlg.update_progress(
                int((i / len(updates)) * 100),
                f"更新 {info.display_title}..."
            )
            QApplication.processEvents()

            success, msg = self.client.update_plugin(info)

            if success:
                success_count += 1
            else:
                failed_count += 1

        progress_dlg.close()

        QMessageBox.information(
            self, "批量更新完成",
            f"成功: {success_count} 个\n失败: {failed_count} 个"
        )

        self._load_plugins()

    # --------------------------------------------------------
    # 安装本地插件
    # --------------------------------------------------------
    def _install_local(self):
        """安装本地插件（ZIP 文件）"""
        from PyQt5.QtWidgets import QFileDialog

        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择插件包", "",
            "插件包 (*.zip);;所有文件 (*.*)"
        )

        if not filepath:
            return

        try:
            # 读取文件
            with open(filepath, 'rb') as f:
                data = f.read()

            # 获取插件名
            name = os.path.splitext(os.path.basename(filepath))[0]

            # 解压
            success, msg = self.client._extract_plugin(
                data, self.client.plugins_dir, name, PLUGIN_TYPE_PLUGIN
            )

            if success:
                QMessageBox.information(
                    self, "安装成功",
                    f"插件已从 {os.path.basename(filepath)} 安装。\n"
                    f"重启编辑器后生效。"
                )
                self._load_plugins()
            else:
                QMessageBox.critical(self, "安装失败", msg)

        except Exception as e:
            QMessageBox.critical(self, "安装失败", str(e))

    # --------------------------------------------------------
    # 调试
    # --------------------------------------------------------
    def dump(self) -> str:
        """导出插件市场信息"""
        lines = ["PluginStoreDialog", "=" * 60]
        lines.append(f"插件总数: {len(self._all_plugins)}")
        lines.append(f"筛选后: {len(self._filtered_plugins)}")
        lines.append(f"当前分类: {self._current_category}")
        lines.append(f"当前排序: {self._current_sort}")
        lines.append(f"搜索: {self._search_text}")

        cache_info = self.client.get_cache_info()
        lines.append(f"缓存: {cache_info}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<PluginStoreDialog plugins={len(self._all_plugins)} "
                f"filtered={len(self._filtered_plugins)}>")


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # 测试客户端
    print("=== 测试 PluginStoreClient ===")
    client = PluginStoreClient()

    # 扫描本地插件
    local = client.scan_local_plugins()
    print(f"本地插件数: {len(local)}")
    for name, info in local.items():
        print(f"  - {name} v{info.version} ({info.type})")
    print()

    # 测试插件信息
    print("=== 测试 PluginInfo ===")
    info = PluginInfo(
        name="test_plugin",
        display_name="测试插件",
        version="1.0.0",
        description="这是一个测试插件",
        author="hedongwei",
        dependencies=["requests", "chardet"],
        permissions=["filesystem", "network"],
    )
    print(f"插件: {info}")
    print(f"显示标题: {info.display_title}")
    print(f"依赖状态: {info.get_dependency_status()}")
    print()

    # 测试版本比较
    print("=== 测试版本比较 ===")
    test_cases = [
        ("1.0.0", "1.0.1", True),
        ("1.0.1", "1.0.0", False),
        ("1.0.0", "2.0.0", True),
        ("2.0.0", "1.9.9", False),
        ("1.0.0", "1.0.0", False),
    ]
    for old, new, expected in test_cases:
        result = PluginStoreClient._is_newer_version(old, new)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {old} -> {new}: {result}")
    print()

    # 显示插件市场对话框
    print("=== 显示插件市场 ===")
    dlg = PluginStoreDialog()
    dlg.show()

    # 5 秒后退出
    from PyQt5.QtCore import QTimer
    QTimer.singleShot(5000, app.quit)

    sys.exit(app.exec())