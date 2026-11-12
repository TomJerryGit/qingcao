# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
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

import datetime
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from PyQt5.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QSettings,
    QSize,
    Qt,
    QThread,
    QTimer,
    QUrl,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
    QTextCursor,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.event_bus import (
    NotificationEvent,
    PluginErrorEvent,
    PluginLoadedEvent,
    PluginUnloadedEvent,
    StatusMessageEvent,
    bus,
)


# ============================================================
# 常量
# ============================================================
# P1-1: 版本号唯一来源 version.py
try:
    from version import __version__ as APP_VERSION
except ImportError:  # pragma: no cover
    APP_VERSION = "0.0.0"

# 插件市场注册表地址（镜像优先，国内可访问）
# 优先级：jsDelivr CDN > 用户自定义 > FALLBACK 列表
# 用户可在"插件市场"的"注册表 URL"输入框中覆盖此默认值
GITHUB_REGISTRY_URL = (
    "https://github.com/TomJerryGit/qingcao/releases/download/plugin-registry/registry.json"
)

DEFAULT_REGISTRY_URL = (
    "https://cdn.jsdelivr.net/gh/qingcao-editor/plugins-registry@main/registry.json"
)

# 备用注册表地址（多路兜底）
FALLBACK_REGISTRY_URLS = [
    # GitHub 原始地址（国外/代理环境）
    "https://raw.githubusercontent.com/qingcao-editor/plugins-registry/main/registry.json",
    # Gitee 镜像（国内）
    "https://gitee.com/qingcao-editor/plugins-registry/raw/main/registry.json",
    # Statically CDN（第三兜底）
    "https://cdn.statically.io/gh/qingcao-editor/plugins-registry/main/registry.json",
]

# 插件目录
PLUGINS_DIR = "plugins"  # 使用前请经 resolve_plugin_dir 解析
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
    ("local_rating", "按本地评分"),
    ("updated", "按更新时间"),
    ("name", "按名称"),
    ("trending", "热门趋势"),
    ("community_rating", "按社区评分"),
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


def plugin_bytes_sha256(data: bytes) -> str:
    """返回插件包 SHA256（小写十六进制）"""
    return hashlib.sha256(data).hexdigest()


def verify_plugin_signature(
    data: bytes,
    expected_hash: str = "",
    signature: str = "",
    signature_algo: str = "",
    key_env: str = "QINGCAO_PLUGIN_SIGNING_KEY",
) -> Tuple[bool, str]:
    """校验插件包完整性/签名（v2.16：SHA256 + HMAC/Ed25519，fail closed）"""
    actual = plugin_bytes_sha256(data)
    if expected_hash and actual.lower() != expected_hash.lower():
        return (False, "文件哈希校验失败")
    if signature:
        algo = (signature_algo or "").lower()
        if algo == "ed25519":
            from core.plugin_signature import verify_signature_envelope

            return verify_signature_envelope(data, signature)
        import hmac

        key = os.environ.get(key_env, "")
        if not key:
            return (False, "未配置签名密钥（%s），拒绝安装" % key_env)
        expected = hmac.new(key.encode("utf-8"), actual.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature.lower()):
            return (False, "签名校验失败")
    return (True, "ok")


def plugin_signature_status(info) -> str:
    """市场 UI 用：插件安全状态文本（v2.16）"""
    try:
        from core.plugin_signature import is_revoked

        if is_revoked(getattr(info, "name", "")):
            return "已吊销"
    except Exception:
        pass
    algo = (getattr(info, "signature_algo", "") or "").lower()
    if not getattr(info, "signature", ""):
        return "未签名（仅 SHA256 校验和）" if getattr(info, "file_hash", "") else "无签名"
    if algo == "ed25519":
        return "Ed25519 签名"
    return "HMAC 签名"


SECURITY_FILTERS = [
    ("all", "全部安全状态"),
    ("ed25519", "仅 Ed25519 签名"),
    ("hmac", "仅 HMAC 签名"),
    ("sha256", "仅 SHA256 校验和"),
    ("unsigned", "未签名"),
    ("revoked", "已吊销"),
]


def plugin_security_bucket(info) -> str:
    """安全状态分类（v2.17 市场筛选）"""
    try:
        from core.plugin_signature import is_revoked

        if is_revoked(getattr(info, "name", "")):
            return "revoked"
    except Exception:
        pass
    algo = (getattr(info, "signature_algo", "") or "").lower()
    if not getattr(info, "signature", ""):
        return "sha256" if getattr(info, "file_hash", "") else "unsigned"
    return "ed25519" if algo == "ed25519" else "hmac"


def plugin_source_badge(info) -> str:
    """来源徽章：官方 / 本地 / 第三方（v2.17）"""
    if getattr(info, "installed", False):
        return "本地"
    if getattr(info, "verified", False) or getattr(info, "featured", False):
        return "官方"
    return "第三方"


def filter_plugins_by_security(plugins, mode):
    """按安全状态筛选插件列表（v2.17）"""
    if not mode or mode == "all":
        return list(plugins)
    return [p for p in plugins if plugin_security_bucket(p) == mode]


def build_market_catalog(plugin_root: str) -> Dict[str, Any]:
    """从本地插件 manifest 构建市场目录（v2.15 离线 MVP）"""
    plugins = []
    try:
        names = sorted(os.listdir(plugin_root))
    except OSError:
        names = []
    for name in names:
        mf = os.path.join(plugin_root, name, "plugin.json")
        if not os.path.isfile(mf):
            continue
        try:
            with open(mf, encoding="utf-8") as f:
                m = json.load(f)
        except Exception:
            continue
        plugins.append(
            {
                "name": m.get("name") or name,
                "display_name": m.get("display_name") or m.get("name") or name,
                "version": m.get("version", "0.0.0"),
                "description": m.get("description", ""),
                "author": m.get("author", ""),
                "category": m.get("category", "other"),
                "license": m.get("license", ""),
                "homepage": m.get("homepage", ""),
                "keywords": m.get("keywords") or [],
                "permissions": m.get("permissions") or [],
                "sandbox": bool(m.get("sandbox")),
                "enabled": bool(m.get("enabled", True)),
            }
        )
    return {"version": 1, "plugins": plugins, "themes": [], "_from_local_catalog": True}


class PluginState(Enum):
    """插件状态"""

    NOT_INSTALLED = auto()  # 未安装
    INSTALLED = auto()  # 已安装
    UPDATE_AVAILABLE = auto()  # 可更新
    DISABLED = auto()  # 已禁用
    ERROR = auto()  # 错误


def check_plugin_compatibility(info, app_version: str = ""):
    """插件与应用版本是否兼容（复用更新器判定，唯一实现）"""
    try:
        from infrastructure.plugin_updater import get_app_version, is_app_version_compatible

        return is_app_version_compatible(
            getattr(info, "min_app_version", "") or "",
            getattr(info, "max_app_version", "") or "",
            app_version or get_app_version(),
        )
    except Exception as e:
        return False, "兼容性检查失败: %s" % e


@dataclass
class PluginInfo:
    """
    插件信息。

    描述一个插件的所有元数据。
    """

    # 基本信息
    name: str = ""  # 内部名称
    display_name: str = ""  # 显示名称
    version: str = "0.0.0"  # 版本
    description: str = ""  # 简介
    long_description: str = ""  # 详细描述
    author: str = ""  # 作者
    author_email: str = ""  # 作者邮箱
    homepage: str = ""  # 主页
    repository: str = ""  # 仓库地址

    # 分类
    type: str = PLUGIN_TYPE_PLUGIN  # 类型
    category: str = "other"  # 分类
    tags: List[str] = field(default_factory=list)  # 标签

    # 版本信息
    min_app_version: str = ""  # 最低应用版本
    max_app_version: str = ""  # 最高应用版本
    updated_at: str = ""  # 更新时间
    changelog: str = ""  # 更新日志（可选）

    # 安装信息
    download_url: str = ""  # 下载地址
    update_url: str = ""  # 更新检测地址
    file_hash: str = ""  # 文件哈希（SHA256）
    signature: str = ""  # 签名（HMAC/Ed25519）
    signature_algo: str = ""  # 签名算法（hmac/ed25519）
    file_size: int = 0  # 文件大小

    # 依赖
    dependencies: List[str] = field(default_factory=list)  # Python 依赖
    plugin_dependencies: List[str] = field(default_factory=list)  # 插件依赖

    # 权限
    permissions: List[str] = field(default_factory=list)

    # 统计
    downloads: int = 0  # 下载量
    rating: float = 0.0  # 评分
    rating_count: int = 0  # 评分数

    # 状态
    verified: bool = False  # 是否认证
    featured: bool = False  # 是否精选
    installed: bool = False  # 是否已安装
    installed_version: str = ""  # 已安装版本
    enabled: bool = True  # 是否启用
    state: PluginState = PluginState.NOT_INSTALLED

    # 本地信息
    local_path: str = ""  # 本地路径
    installed_at: str = ""  # 安装时间

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        d = asdict(self)
        d["state"] = self.state.name
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PluginInfo":
        """从字典反序列化"""
        info = cls()
        for key, value in d.items():
            if hasattr(info, key):
                if key == "state" and isinstance(value, str):
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
            dep_name = dep.split("==")[0].split(">=")[0].split("<")[0]
            dep_name = dep_name.split("[")[0].strip()

            try:
                __import__(dep_name.replace("-", "_"))
            except ImportError:
                missing.append(dep)

        return (len(missing) == 0, missing)

    def __repr__(self) -> str:
        return f"<PluginInfo {self.name} v{self.version} state={self.state.name}>"


COMMUNITY_RATINGS: Dict[str, Dict[str, Any]] = {}


def set_community_ratings(plugins) -> None:
    COMMUNITY_RATINGS.clear()
    if isinstance(plugins, dict):
        COMMUNITY_RATINGS.update(plugins)


def get_community_rating(name):
    rec = COMMUNITY_RATINGS.get(name)
    if not isinstance(rec, dict):
        return None
    try:
        return (float(rec.get("average", 0)), int(rec.get("count", 0)))
    except Exception:
        return None


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

        # 鉴权/TLS（v2.18.x P3）
        self.registry_token = os.environ.get("QINGCAO_REGISTRY_TOKEN", "")
        _env_tls = os.environ.get("QINGCAO_REGISTRY_VERIFY_TLS")
        if _env_tls is not None:
            self.verify_tls = _env_tls != "0"
        else:
            try:
                from PyQt5.QtCore import QSettings

                self.verify_tls = QSettings("QingCao", "Editor").value(
                    "registry_verify_tls", True, type=bool
                )
            except Exception:
                self.verify_tls = True

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
    def fetch_ratings(self, timeout=5):
        """拉取并验签静态 ratings.json；失败/无效返回 None（fail-closed）。"""
        if os.environ.get("QINGCAO_NO_COMMUNITY_RATINGS") == "1":
            return None
        base = self.registry_url.rsplit("/", 1)[0]
        url = base + "/ratings.json"

        def _get(target):
            try:
                import requests

                resp = requests.get(target, timeout=timeout, headers=self._registry_headers())
                if resp.status_code == 200:
                    return resp.content
            except Exception:
                pass
            try:
                import urllib.request

                req = urllib.request.Request(target, headers=self._registry_headers())
                with urllib.request.urlopen(req, timeout=timeout) as f:
                    return f.read()
            except Exception:
                return None

        raw = _get(url)
        if not raw:
            return None
        sig = _get(url + ".sig")
        if not sig:
            return None
        try:
            from core.plugin_signature import verify_signature_envelope

            ok, _msg = verify_signature_envelope(raw, sig.decode("ascii", "ignore").strip())
            if not ok:
                return None
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def fetch_registry(
        self, force: bool = False, cache_first: bool = False
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

    def _registry_headers(self) -> Dict[str, str]:
        """注册表请求头（Token 鉴权，v2.18.x P3）"""
        token = self.registry_token or os.environ.get("QINGCAO_REGISTRY_TOKEN", "")
        if not token:
            try:
                from PyQt5.QtCore import QSettings

                token = QSettings("QingCao", "Editor").value("registry_token", "", type=str) or ""
            except Exception:
                token = ""
        return {"Authorization": "Bearer %s" % token} if token else {}

    def _download_json(self, url: str) -> Optional[Dict[str, Any]]:
        """下载 JSON"""
        try:
            import requests

            resp = requests.get(
                url,
                timeout=DOWNLOAD_TIMEOUT,
                headers=self._registry_headers(),
                verify=self.verify_tls,
            )
            if resp.status_code == 200:
                return resp.json()
        except ImportError:
            # 使用 urllib 回退
            import urllib.request

            _req = urllib.request.Request(url, headers=self._registry_headers())
            with urllib.request.urlopen(_req, timeout=DOWNLOAD_TIMEOUT) as f:
                return json.loads(f.read().decode("utf-8"))
        except Exception as e:
            print(f"[PluginStore] 下载失败: {e}")

        return None

    def _save_cache(self, data: Dict[str, Any]):
        """保存到磁盘缓存"""
        try:
            cache_file = os.path.join(self.cache_dir, "registry.json")
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "data": data,
                        "timestamp": time.time(),
                    },
                    f,
                    ensure_ascii=False,
                )
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
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            fallback_path = os.path.join(root, "resources", "registry_fallback.json")

            if not os.path.exists(fallback_path):
                catalog = build_market_catalog(os.path.join(root, "plugins"))
                if catalog.get("plugins"):
                    return catalog
                return None

            with open(fallback_path, encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                return None
            if not data.get("plugins"):
                catalog = build_market_catalog(os.path.join(root, "plugins"))
                if catalog.get("plugins"):
                    return catalog

            # 打标记，便于 UI 区分
            data["_from_fallback"] = True
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

            with open(cache_file, encoding="utf-8") as f:
                cached = json.load(f)

            data = cached.get("data")
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

            with open(cache_file, encoding="utf-8") as f:
                cached = json.load(f)

            # 检查缓存时间
            timestamp = cached.get("timestamp", 0)
            if time.time() - timestamp > CACHE_TTL * 24:  # 缓存最长 1 天
                return None

            self._registry_cache = cached.get("data")
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
            items = registry.get("plugins", [])
            items.extend(registry.get("themes", []))

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
                local_info.state = (
                    PluginState.INSTALLED if local_info.enabled else PluginState.DISABLED
                )
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
                if name.startswith("."):
                    continue

                info = self._read_local_plugin(path, name)
                if info:
                    plugins[name] = info

        # 扫描 themes 目录
        if os.path.isdir(self.themes_dir):
            for filename in os.listdir(self.themes_dir):
                if filename.endswith(".json"):
                    theme_name = os.path.splitext(filename)[0]
                    path = os.path.join(self.themes_dir, filename)

                    info = PluginInfo(
                        name=theme_name,
                        display_name=theme_name,
                        type=PLUGIN_TYPE_THEME,
                        category="theme",
                        local_path=path,
                        installed=True,
                        enabled=True,
                        state=PluginState.INSTALLED,
                    )

                    try:
                        with open(path, encoding="utf-8") as f:
                            theme_data = json.load(f)
                        info.display_name = theme_data.get("name", theme_name)
                        info.description = theme_data.get("description", "")
                        info.author = theme_data.get("author", "")
                        info.version = theme_data.get("version", "1.0.0")
                    except Exception:
                        pass

                    plugins[f"theme.{theme_name}"] = info

        return plugins

    def _read_local_plugin(self, path: str, name: str) -> Optional[PluginInfo]:
        """读取本地插件信息"""
        manifest_path = os.path.join(path, "plugin.json")
        if not os.path.exists(manifest_path):
            return None

        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            info = PluginInfo(
                name=manifest.get("name", name),
                display_name=manifest.get("display_name", manifest.get("name", name)),
                version=manifest.get("version", "0.0.0"),
                description=manifest.get("description", ""),
                author=manifest.get("author", ""),
                author_email=manifest.get("author_email", ""),
                homepage=manifest.get("homepage", ""),
                repository=manifest.get("repository", ""),
                type=manifest.get("type", PLUGIN_TYPE_PLUGIN),
                category=manifest.get("category", "other"),
                tags=manifest.get("tags", []),
                dependencies=manifest.get("dependencies", []),
                plugin_dependencies=manifest.get("plugin_dependencies", []),
                permissions=manifest.get("permissions", []),
                local_path=path,
                installed=True,
                enabled=not manifest.get("disabled", False),
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
    def install_plugin(
        self,
        info: PluginInfo,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        install_deps: bool = True,
    ) -> Tuple[bool, str]:
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

            # 校验哈希/签名（v2.15.x P3）
            if info.file_hash or getattr(info, "signature", ""):
                if progress_callback:
                    progress_callback(40, "校验中...")

                ok, msg = verify_plugin_signature(
                    data,
                    info.file_hash,
                    getattr(info, "signature", ""),
                    getattr(info, "signature_algo", ""),
                )
                if not ok:
                    return (False, msg)

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

            target_dir = self.themes_dir if info.type == PLUGIN_TYPE_THEME else self.plugins_dir

            _target_path = os.path.join(target_dir, info.name)
            _existed_before = os.path.exists(_target_path)
            success, msg = self._extract_plugin(data, target_dir, info.name, info.type)
            if not success:
                # 回滚：清理本次新建的半成品目录（v2.17）
                try:
                    if not _existed_before and os.path.isdir(_target_path):
                        import shutil

                        shutil.rmtree(_target_path, ignore_errors=True)
                except Exception:
                    pass
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
                self.cache_dir, "uninstalled", f"{info.name}_{int(time.time())}"
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

    def update_plugin(
        self, info: PluginInfo, progress_callback: Optional[Callable[[int, str], None]] = None
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
            backup_dir = os.path.join(self.cache_dir, "backup", f"{info.name}_{int(time.time())}")
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

            manifest_path = os.path.join(info.local_path, "plugin.json")
            if not os.path.exists(manifest_path):
                return False

            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            manifest["disabled"] = not enabled

            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)

            info.enabled = enabled
            info.state = PluginState.INSTALLED if enabled else PluginState.DISABLED

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

                if self._is_newer_version(local_info.version, remote_info.version):
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

        for item in registry.get("plugins", []):
            if item.get("name") == name:
                return PluginInfo.from_dict(item)

        for item in registry.get("themes", []):
            if item.get("name") == name:
                return PluginInfo.from_dict(item)

        return None

    @staticmethod
    def _is_newer_version(old_version: str, new_version: str) -> bool:
        """比较版本号"""
        try:

            def parse(v):
                # 移除预发布标识
                v = v.split("-")[0].split("+")[0]
                return [int(x) for x in v.split(".")]

            return parse(new_version) > parse(old_version)

        except Exception:
            return new_version > old_version

    # --------------------------------------------------------
    # 依赖安装
    # --------------------------------------------------------
    def _install_dependencies(self, dependencies: List[str]) -> Tuple[bool, str]:
        """安装 Python 依赖"""
        if not dependencies:
            return (True, "")

        try:
            import subprocess

            cmd = [sys.executable, "-m", "pip", "install"]
            cmd.extend(dependencies)

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

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

            resp = requests.get(
                url,
                timeout=DOWNLOAD_TIMEOUT,
                headers=self._registry_headers(),
                verify=self.verify_tls,
                stream=True,
            )
            if resp.status_code != 200:
                return None

            # 流式下载
            chunks = []
            for chunk in resp.iter_content(chunk_size=8192):
                chunks.append(chunk)

            return b"".join(chunks)

        except ImportError:
            import urllib.request

            try:
                _req = urllib.request.Request(url, headers=self._registry_headers())
                with urllib.request.urlopen(_req, timeout=DOWNLOAD_TIMEOUT) as f:
                    return f.read()
            except Exception:
                return None
        except Exception as e:
            print(f"[PluginStore] 下载失败: {e}")
            return None

    # --------------------------------------------------------
    # 解压
    # --------------------------------------------------------
    def _extract_plugin(
        self, data: bytes, target_dir: str, plugin_name: str, plugin_type: str
    ) -> Tuple[bool, str]:
        """解压插件包"""
        try:
            # 写入临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                tmp.write(data)
                tmp_path = tmp.name

            try:
                # 解压
                with zipfile.ZipFile(tmp_path, "r") as zf:
                    # 检查压缩包结构
                    names = zf.namelist()

                    # 判断是否包含顶层目录
                    top_level = set()
                    for name in names:
                        parts = name.split("/")
                        if parts:
                            top_level.add(parts[0])

                    # 如果只有一个顶层目录且是插件名，则解压后移动
                    if len(top_level) == 1:
                        top_dir = list(top_level)[0]
                        if top_dir == plugin_name or top_dir.endswith("/"):
                            # 直接解压到 target_dir
                            extract_dir = target_dir
                        else:
                            # 解压到临时目录，然后移动
                            extract_dir = tempfile.mkdtemp()
                            zf.extractall(extract_dir)
                            final_dir = os.path.join(target_dir, plugin_name)

                            if os.path.exists(final_dir):
                                shutil.rmtree(final_dir)

                            shutil.move(os.path.join(extract_dir, top_dir), final_dir)
                            shutil.rmtree(extract_dir, ignore_errors=True)

                            os.unlink(tmp_path)
                            return (True, "")

                    # 解压到目标目录
                    if plugin_type == PLUGIN_TYPE_THEME:
                        # 主题文件是单个 JSON，直接复制到 themes 目录
                        for name in names:
                            if name.endswith(".json"):
                                with zf.open(name) as src:
                                    content = src.read()
                                theme_file = os.path.join(target_dir, os.path.basename(name))
                                with open(theme_file, "wb") as dst:
                                    dst.write(content)
                    else:
                        # 插件解压到子目录
                        extract_to = os.path.join(target_dir, plugin_name)
                        if os.path.exists(extract_to):
                            shutil.rmtree(extract_to)
                        os.makedirs(extract_to, exist_ok=True)

                        for name in names:
                            # 安全检查：防止路径穿越
                            if ".." in name or name.startswith("/"):
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
            "cache_dir": self.cache_dir,
            "has_cache": self._registry_cache is not None,
            "cache_age_seconds": 0,
        }

        if self._registry_cache_time > 0:
            info["cache_age_seconds"] = int(time.time() - self._registry_cache_time)

        return info


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

    # 修复 B1：原名为 finished，会覆盖 QThread.finished（无参）
    # 信号导致线程 run() 结束时 Qt 内部 emit 参数不匹配。
    registry_ready = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, client, force: bool = False, parent=None):
        super().__init__(parent)
        self.client = client
        self.force = force

    def run(self):
        try:
            registry = self.client.fetch_registry(force=self.force)
            if registry:
                self.registry_ready.emit(registry)
            else:
                self.failed.emit("无法获取注册表（网络与缓存均失败）")
        except Exception as e:
            self.failed.emit(str(e))
