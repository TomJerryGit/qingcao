#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为插件更新器模块，包含：
- PluginUpdater：插件更新器（检查/下载/安装/回滚）
- UpdateInfo：更新信息数据类
- UpdateResult：更新结果数据类
- UpdateHistoryEntry：更新历史记录
- 版本比较与语义化版本
- 远程注册表拉取
- 更新检查（单个/批量）
- 更新下载（带进度）
- 增量安装与原子替换
- 备份与回滚机制
- 依赖检查与安装
- 文件哈希校验
- 自动更新调度
- 更新历史管理
- 网络异常重试
"""

import os
import sys
import json
import time
import shutil
import hashlib
import zipfile
import tempfile
import threading
import datetime
from typing import Optional, List, Dict, Any, Tuple, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from urllib.parse import urlparse

from PyQt5.QtCore import QObject, pyqtSignal, QTimer


# ============================================================
# 常量
# ============================================================
# 默认注册表地址
DEFAULT_REGISTRY_URL = (
    "https://raw.githubusercontent.com/"
    "qingcao-editor/plugins-registry/main/registry.json"
)

# 备用注册表地址
FALLBACK_REGISTRY_URLS = [
    "https://gitee.com/qingcao-editor/plugins-registry/raw/main/registry.json",
]

# 插件目录
PLUGINS_DIR = "plugins"
THEMES_DIR = "themes"

# 更新缓存目录
UPDATE_CACHE_DIR = "data/update_cache"

# 备份目录
BACKUP_DIR = "data/plugin_backups"

# 更新历史文件
UPDATE_HISTORY_FILE = "data/update_history.json"

# 缓存有效期（秒）
CACHE_TTL = 3600  # 1 小时

# 下载超时（秒）
DOWNLOAD_TIMEOUT = 60

# 最大重试次数
MAX_RETRIES = 3
RETRY_DELAY = 3  # 秒

# 自动更新检查间隔（小时）
DEFAULT_AUTO_CHECK_INTERVAL = 24

# 保留的备份数量
MAX_BACKUPS = 10

# 更新通道
UPDATE_CHANNELS = {
    "stable": "稳定版",
    "beta": "测试版",
    "dev": "开发版",
}


# ============================================================
# 更新状态枚举
# ============================================================
class UpdateState(Enum):
    """更新状态"""
    IDLE = auto()              # 空闲
    CHECKING = auto()          # 检查中
    DOWNLOADING = auto()       # 下载中
    EXTRACTING = auto()        # 解压中
    INSTALLING = auto()        # 安装中
    COMPLETED = auto()         # 完成
    FAILED = auto()            # 失败
    CANCELLED = auto()         # 已取消
    ROLLING_BACK = auto()      # 回滚中


# ============================================================
# 更新信息
# ============================================================
@dataclass
class UpdateInfo:
    """
    单个插件的更新信息。
    """

    # 基本信息
    name: str = ""                          # 插件名
    display_name: str = ""                  # 显示名
    current_version: str = ""               # 当前版本
    latest_version: str = ""                # 最新版本

    # 更新内容
    description: str = ""                   # 更新说明
    changelog: str = ""                     # 变更日志
    release_date: str = ""                  # 发布日期

    # 下载信息
    download_url: str = ""                  # 下载地址
    file_hash: str = ""                     # 文件哈希
    file_size: int = 0                      # 文件大小

    # 依赖
    dependencies: List[str] = field(default_factory=list)
    plugin_dependencies: List[str] = field(default_factory=list)

    # 兼容性
    min_app_version: str = ""               # 最低应用版本

    # 状态
    has_update: bool = False                # 是否有更新
    is_major: bool = False                  # 是否主版本更新
    is_security: bool = False               # 是否安全更新
    forced: bool = False                    # 是否强制更新

    # 通道
    channel: str = "stable"                 # 更新通道

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def version_display(self) -> str:
        """版本显示"""
        if not self.has_update:
            return f"v{self.current_version}"
        return f"{self.current_version} → {self.latest_version}"

    def get_summary(self) -> str:
        """获取摘要"""
        if not self.has_update:
            return f"{self.display_name or self.name} 已是最新版本"
        return (f"{self.display_name or self.name}: "
                f"{self.current_version} → {self.latest_version}")

    def __repr__(self) -> str:
        return (f"<UpdateInfo {self.name} "
                f"{self.current_version}->{self.latest_version} "
                f"has_update={self.has_update}>")


# ============================================================
# 更新结果
# ============================================================
@dataclass
class UpdateResult:
    """
    更新操作的结果。
    """

    success: bool = False                   # 是否成功
    name: str = ""                          # 插件名
    old_version: str = ""                   # 旧版本
    new_version: str = ""                   # 新版本
    message: str = ""                       # 结果消息
    error: str = ""                         # 错误信息

    # 时间统计
    download_ms: float = 0.0                # 下载耗时
    install_ms: float = 0.0                 # 安装耗时
    total_ms: float = 0.0                   # 总耗时

    # 备份路径（用于回滚）
    backup_path: str = ""

    # 状态
    state: UpdateState = UpdateState.IDLE

    def get_summary(self) -> str:
        """获取摘要"""
        if self.success:
            return (f"{self.name}: {self.old_version} → "
                    f"{self.new_version} ({self.total_ms:.0f} ms)")
        return f"{self.name} 更新失败: {self.error or self.message}"

    def __repr__(self) -> str:
        return f"<UpdateResult {self.get_summary()}>"


# ============================================================
# 更新历史记录
# ============================================================
@dataclass
class UpdateHistoryEntry:
    """更新历史记录"""

    name: str = ""
    old_version: str = ""
    new_version: str = ""
    success: bool = False
    timestamp: str = ""
    message: str = ""
    channel: str = "stable"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'UpdateHistoryEntry':
        entry = cls()
        for key, value in d.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        return entry

    def __repr__(self) -> str:
        status = "✓" if self.success else "✗"
        return (f"<UpdateHistory {status} {self.name} "
                f"{self.old_version}->{self.new_version} "
                f"@ {self.timestamp[:19]}>")


# ============================================================
# 语义化版本
# ============================================================
class SemVer:
    """语义化版本号"""

    def __init__(self, version: str = "0.0.0"):
        self.raw = version
        self.major = 0
        self.minor = 0
        self.patch = 0
        self.prerelease = ""
        self.build = ""

        self._parse(version)

    def _parse(self, version: str):
        """解析版本号"""
        try:
            # 分离 build metadata
            if '+' in version:
                version, self.build = version.split('+', 1)

            # 分离 prerelease
            if '-' in version:
                version, self.prerelease = version.split('-', 1)

            parts = version.split('.')

            if len(parts) >= 1:
                self.major = int(parts[0]) if parts[0].isdigit() else 0
            if len(parts) >= 2:
                self.minor = int(parts[1]) if parts[1].isdigit() else 0
            if len(parts) >= 3:
                self.patch = int(parts[2]) if parts[2].isdigit() else 0

        except Exception:
            pass

    def __eq__(self, other: 'SemVer') -> bool:
        return (self.major == other.major and
                self.minor == other.minor and
                self.patch == other.patch)

    def __lt__(self, other: 'SemVer') -> bool:
        return self._compare(other) < 0

    def __gt__(self, other: 'SemVer') -> bool:
        return self._compare(other) > 0

    def __le__(self, other: 'SemVer') -> bool:
        return self._compare(other) <= 0

    def __ge__(self, other: 'SemVer') -> bool:
        return self._compare(other) >= 0

    def _compare(self, other: 'SemVer') -> int:
        """比较版本号"""
        # 比较主版本
        if self.major != other.major:
            return 1 if self.major > other.major else -1
        if self.minor != other.minor:
            return 1 if self.minor > other.minor else -1
        if self.patch != other.patch:
            return 1 if self.patch > other.patch else -1

        # prerelease：无 prerelease 的版本更大
        if not self.prerelease and other.prerelease:
            return 1
        if self.prerelease and not other.prerelease:
            return -1

        # 比较 prerelease
        if self.prerelease != other.prerelease:
            return 1 if self.prerelease > other.prerelease else -1

        return 0

    def is_major_update(self, other: 'SemVer') -> bool:
        """检查是否主版本更新"""
        return other.major > self.major

    def __str__(self) -> str:
        return self.raw

    def __repr__(self) -> str:
        return f"<SemVer {self.raw}>"


# ============================================================
# 插件更新器
# ============================================================
class PluginUpdater(QObject):
    """
    插件更新器。

    负责:
    - 检查插件更新（远程注册表）
    - 下载更新包
    - 安装更新（原子替换）
    - 失败回滚
    - 依赖管理
    - 自动更新调度
    - 更新历史记录

    信号:
        check_started(): 检查开始
        check_finished(list): 检查完成（UpdateInfo 列表）
        update_started(str): 更新开始（插件名）
        update_progress(str, int, str): 更新进度（插件名, 百分比, 状态）
        update_finished(object): 更新完成（UpdateResult）
        update_failed(str, str): 更新失败（插件名, 错误）
        rollback_finished(str, bool): 回滚完成（插件名, 是否成功）
        auto_check_triggered(): 自动检查触发
    """

    check_started = pyqtSignal()
    check_finished = pyqtSignal(list)
    update_started = pyqtSignal(str)
    update_progress = pyqtSignal(str, int, str)
    update_finished = pyqtSignal(object)
    update_failed = pyqtSignal(str, str)
    rollback_finished = pyqtSignal(str, bool)
    auto_check_triggered = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None,
                 registry_url: str = DEFAULT_REGISTRY_URL,
                 plugin_dir: str = PLUGINS_DIR,
                 theme_dir: str = THEMES_DIR):
        """
        参数:
            parent: 父 QObject
            registry_url: 远程注册表地址
            plugin_dir: 插件目录
            theme_dir: 主题目录
        """
        super().__init__(parent)

        self.registry_url = registry_url
        self.plugin_dir = plugin_dir
        self.theme_dir = theme_dir

        # 状态
        self._state = UpdateState.IDLE
        self._cancelled = False
        self._lock = threading.RLock()

        # 缓存
        self._registry_cache: Optional[Dict[str, Any]] = None
        self._registry_cache_time: float = 0.0

        # 更新历史
        self._history: List[UpdateHistoryEntry] = []

        # 自动更新配置
        self._auto_check_enabled = True
        self._auto_check_interval = DEFAULT_AUTO_CHECK_INTERVAL
        self._last_check_time: float = 0.0
        self._update_channel = "stable"

        # 自动检查定时器
        self._auto_check_timer = QTimer(self)
        self._auto_check_timer.setInterval(
            self._auto_check_interval * 3600 * 1000
        )
        self._auto_check_timer.timeout.connect(self._on_auto_check)

        # 确保目录存在
        os.makedirs(UPDATE_CACHE_DIR, exist_ok=True)
        os.makedirs(BACKUP_DIR, exist_ok=True)

        # 加载配置和历史
        self._load_config()
        self._load_history()

    # ========================================================
    # 状态
    # ========================================================
    @property
    def state(self) -> UpdateState:
        return self._state

    @property
    def is_busy(self) -> bool:
        """是否正在操作中"""
        return self._state not in (
            UpdateState.IDLE,
            UpdateState.COMPLETED,
            UpdateState.FAILED,
            UpdateState.CANCELLED,
        )

    def cancel(self):
        """取消当前操作"""
        self._cancelled = True

    # ========================================================
    # 检查更新
    # ========================================================
    def check_updates(self, force: bool = False,
                       progress_callback: Optional[Callable] = None
                       ) -> List[UpdateInfo]:
        """
        检查所有已安装插件的更新。

        参数:
            force: 强制刷新（忽略缓存）
            progress_callback: 进度回调（可选）

        返回:
            UpdateInfo 列表（仅包含有更新的）
        """
        if self.is_busy:
            print("[PluginUpdater] 已有更新操作进行中")
            return []

        self._state = UpdateState.CHECKING
        self._cancelled = False

        self.check_started.emit()

        start_time = time.time()
        updates: List[UpdateInfo] = []

        try:
            # 拉取远程注册表
            if progress_callback:
                progress_callback(0, "拉取注册表...")

            registry = self._fetch_registry(force=force)

            if not registry:
                print("[PluginUpdater] 无法获取注册表")
                return []

            # 扫描本地插件
            if progress_callback:
                progress_callback(30, "扫描本地插件...")

            local_plugins = self._scan_local_plugins()

            # 构建远程插件映射
            remote_map = {}
            for item in registry.get('plugins', []):
                if item.get('name'):
                    remote_map[item['name']] = item
            for item in registry.get('themes', []):
                if item.get('name'):
                    remote_map[item['name']] = item

            # 对每个本地插件检查更新
            total = len(local_plugins)
            for i, (name, local_info) in enumerate(local_plugins.items()):
                if self._cancelled:
                    break

                if progress_callback:
                    progress_callback(
                        30 + int((i / max(1, total)) * 60),
                        f"检查 {name}..."
                    )

                remote_info = remote_map.get(name)
                if not remote_info:
                    continue

                update = self._compare_versions(
                    name, local_info, remote_info
                )

                if update and update.has_update:
                    updates.append(update)

            # 完成
            self._last_check_time = time.time()
            self._save_config()

            self._state = UpdateState.COMPLETED

            if progress_callback:
                progress_callback(100, f"发现 {len(updates)} 个更新")

            elapsed = (time.time() - start_time) * 1000
            print(f"[PluginUpdater] 检查完成，耗时 {elapsed:.0f} ms，"
                  f"发现 {len(updates)} 个更新")

            self.check_finished.emit(updates)

            return updates

        except Exception as e:
            self._state = UpdateState.FAILED
            print(f"[PluginUpdater] 检查失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _compare_versions(self, name: str, local_info: Dict[str, Any],
                           remote_info: Dict[str, Any]) -> Optional[UpdateInfo]:
        """
        比较本地和远程版本。

        返回:
            UpdateInfo 或 None
        """
        try:
            local_version = local_info.get('version', '0.0.0')
            remote_version = remote_info.get('version', '0.0.0')

            # 检查更新通道
            remote_channel = remote_info.get('channel', 'stable')
            if not self._is_channel_allowed(remote_channel):
                return None

            # 版本比较
            local_ver = SemVer(local_version)
            remote_ver = SemVer(remote_version)

            has_update = remote_ver > local_ver

            # 构建 UpdateInfo
            update = UpdateInfo(
                name=name,
                display_name=remote_info.get('display_name',
                                              remote_info.get('name', name)),
                current_version=local_version,
                latest_version=remote_version,
                description=remote_info.get('description', ''),
                changelog=remote_info.get('changelog', ''),
                release_date=remote_info.get('updated_at', ''),
                download_url=remote_info.get('download_url', ''),
                file_hash=remote_info.get('file_hash', ''),
                file_size=remote_info.get('file_size', 0),
                dependencies=remote_info.get('dependencies', []),
                plugin_dependencies=remote_info.get(
                    'plugin_dependencies', []
                ),
                min_app_version=remote_info.get('min_app_version', ''),
                has_update=has_update,
                is_major=has_update and remote_ver.is_major_update(local_ver),
                is_security=remote_info.get('security', False),
                forced=remote_info.get('forced', False),
                channel=remote_channel,
            )

            return update

        except Exception as e:
            print(f"[PluginUpdater] 比较版本失败 ({name}): {e}")
            return None

    def _is_channel_allowed(self, channel: str) -> bool:
        """检查更新通道是否允许"""
        if self._update_channel == "dev":
            return True
        elif self._update_channel == "beta":
            return channel in ("stable", "beta")
        else:  # stable
            return channel == "stable"

    # ========================================================
    # 拉取注册表
    # ========================================================
    def _fetch_registry(self, force: bool = False
                          ) -> Optional[Dict[str, Any]]:
        """拉取远程注册表"""
        # 检查缓存
        if not force and self._registry_cache is not None:
            elapsed = time.time() - self._registry_cache_time
            if elapsed < CACHE_TTL:
                return self._registry_cache

        # 尝试所有 URL
        urls = [self.registry_url] + FALLBACK_REGISTRY_URLS

        for url in urls:
            try:
                data = self._download_json(url)
                if data:
                    self._registry_cache = data
                    self._registry_cache_time = time.time()
                    return data
            except Exception as e:
                print(f"[PluginUpdater] 拉取失败 ({url}): {e}")
                continue

        # 尝试磁盘缓存
        cached = self._load_disk_cache()
        if cached:
            return cached

        return None

    def _download_json(self, url: str) -> Optional[Dict[str, Any]]:
        """下载 JSON"""
        for attempt in range(MAX_RETRIES):
            if self._cancelled:
                return None

            try:
                import requests
                resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
                if resp.status_code == 200:
                    return resp.json()
                else:
                    print(f"[PluginUpdater] HTTP {resp.status_code}")
            except ImportError:
                # urllib 回退
                try:
                    import urllib.request
                    with urllib.request.urlopen(
                        url, timeout=DOWNLOAD_TIMEOUT
                    ) as f:
                        return json.loads(f.read().decode('utf-8'))
                except Exception as e:
                    print(f"[PluginUpdater] urllib 失败: {e}")
            except Exception as e:
                print(f"[PluginUpdater] 下载失败: {e}")

            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))

        return None

    def _load_disk_cache(self) -> Optional[Dict[str, Any]]:
        """从磁盘缓存加载注册表"""
        try:
            cache_file = os.path.join(UPDATE_CACHE_DIR, "registry.json")
            if not os.path.exists(cache_file):
                return None

            with open(cache_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)

            timestamp = cached.get('timestamp', 0)
            # 缓存有效期 24 小时
            if time.time() - timestamp > CACHE_TTL * 24:
                return None

            self._registry_cache = cached.get('data')
            self._registry_cache_time = timestamp
            return self._registry_cache

        except Exception:
            return None

    def _save_disk_cache(self, data: Dict[str, Any]):
        """保存到磁盘缓存"""
        try:
            cache_file = os.path.join(UPDATE_CACHE_DIR, "registry.json")
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'data': data,
                    'timestamp': time.time(),
                }, f, ensure_ascii=False)
        except Exception:
            pass

    # ========================================================
    # 扫描本地插件
    # ========================================================
    def _scan_local_plugins(self) -> Dict[str, Dict[str, Any]]:
        """扫描本地已安装插件"""
        plugins = {}

        # 扫描 plugins 目录
        if os.path.isdir(self.plugin_dir):
            for name in os.listdir(self.plugin_dir):
                path = os.path.join(self.plugin_dir, name)
                if not os.path.isdir(path):
                    continue
                if name.startswith('.'):
                    continue

                info = self._read_plugin_manifest(path)
                if info:
                    plugins[name] = info

        # 扫描 themes 目录
        if os.path.isdir(self.theme_dir):
            for filename in os.listdir(self.theme_dir):
                if filename.endswith('.json'):
                    theme_name = os.path.splitext(filename)[0]
                    path = os.path.join(self.theme_dir, filename)

                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            data = json.load(f)

                        plugins[f"theme.{theme_name}"] = {
                            'name': theme_name,
                            'version': data.get('version', '1.0.0'),
                            'path': path,
                            'type': 'theme',
                        }
                    except Exception:
                        pass

        return plugins

    def _read_plugin_manifest(self, path: str
                                ) -> Optional[Dict[str, Any]]:
        """读取插件 manifest"""
        manifest_path = os.path.join(path, 'plugin.json')
        if not os.path.exists(manifest_path):
            return None

        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)

            manifest['path'] = path
            manifest['manifest_path'] = manifest_path
            return manifest

        except Exception as e:
            print(f"[PluginUpdater] 读取 manifest 失败: {e}")
            return None

    # ========================================================
    # 执行更新
    # ========================================================
    def update_plugin(self, info: UpdateInfo,
                       progress_callback: Optional[Callable] = None
                       ) -> UpdateResult:
        """
        更新单个插件。

        参数:
            info: 更新信息
            progress_callback: 进度回调（百分比, 状态描述）

        返回:
            UpdateResult
        """
        if not info.has_update:
            return UpdateResult(
                success=False,
                name=info.name,
                message="已是最新版本",
            )

        if self.is_busy:
            return UpdateResult(
                success=False,
                name=info.name,
                message="已有更新操作进行中",
            )

        self._state = UpdateState.DOWNLOADING
        self._cancelled = False

        self.update_started.emit(info.name)

        result = UpdateResult(
            name=info.name,
            old_version=info.current_version,
            new_version=info.latest_version,
        )

        start_time = time.time()

        try:
            # 1. 检查插件依赖
            if progress_callback:
                progress_callback(0, "检查依赖...")

            if not self._check_dependencies(info):
                result.success = False
                result.error = "依赖检查失败"
                self._state = UpdateState.FAILED
                return result

            # 2. 下载
            if progress_callback:
                progress_callback(5, "下载中...")

            download_start = time.time()

            data = self._download_update(
                info.download_url, info.name,
                progress_callback=progress_callback
            )

            if data is None:
                result.success = False
                result.error = "下载失败"
                self._state = UpdateState.FAILED
                return result

            result.download_ms = (time.time() - download_start) * 1000

            if self._cancelled:
                result.success = False
                result.error = "已取消"
                self._state = UpdateState.CANCELLED
                return result

            # 3. 校验哈希
            if info.file_hash:
                if progress_callback:
                    progress_callback(60, "校验哈希...")

                actual_hash = hashlib.sha256(data).hexdigest()
                if actual_hash.lower() != info.file_hash.lower():
                    result.success = False
                    result.error = "文件哈希不匹配"
                    self._state = UpdateState.FAILED
                    return result

            # 4. 备份现有插件
            if progress_callback:
                progress_callback(65, "备份现有插件...")

            backup_path = self._backup_plugin(info.name)

            if not backup_path:
                result.success = False
                result.error = "备份失败"
                self._state = UpdateState.FAILED
                return result

            result.backup_path = backup_path

            # 5. 解压安装
            if progress_callback:
                progress_callback(75, "安装中...")

            install_start = time.time()

            success, error = self._install_update(
                data, info.name, info.latest_version
            )

            if not success:
                # 回滚
                if progress_callback:
                    progress_callback(85, "安装失败，回滚中...")

                self._rollback(info.name, backup_path)

                result.success = False
                result.error = error or "安装失败"
                self._state = UpdateState.FAILED
                return result

            result.install_ms = (time.time() - install_start) * 1000

            # 6. 安装 Python 依赖
            if info.dependencies:
                if progress_callback:
                    progress_callback(90, "安装 Python 依赖...")

                self._install_python_dependencies(info.dependencies)

            # 完成
            result.success = True
            result.message = f"成功更新到 v{info.latest_version}"

            self._state = UpdateState.COMPLETED

            if progress_callback:
                progress_callback(100, "更新完成")

            # 记录历史
            self._add_history(UpdateHistoryEntry(
                name=info.name,
                old_version=info.current_version,
                new_version=info.latest_version,
                success=True,
                timestamp=datetime.datetime.now().isoformat(),
                message=result.message,
                channel=info.channel,
            ))

            result.total_ms = (time.time() - start_time) * 1000

            self.update_finished.emit(result)

            return result

        except Exception as e:
            result.success = False
            result.error = str(e)
            result.total_ms = (time.time() - start_time) * 1000

            self._state = UpdateState.FAILED

            # 尝试回滚
            if result.backup_path:
                self._rollback(info.name, result.backup_path)

            # 记录失败
            self._add_history(UpdateHistoryEntry(
                name=info.name,
                old_version=info.current_version,
                new_version=info.latest_version,
                success=False,
                timestamp=datetime.datetime.now().isoformat(),
                message=str(e),
                channel=info.channel,
            ))

            self.update_failed.emit(info.name, str(e))

            return result

    def update_all(self, updates: List[UpdateInfo],
                    progress_callback: Optional[Callable] = None
                    ) -> List[UpdateResult]:
        """
        批量更新。

        参数:
            updates: UpdateInfo 列表
            progress_callback: 进度回调

        返回:
            UpdateResult 列表
        """
        results = []
        total = len(updates)

        for i, info in enumerate(updates):
            if self._cancelled:
                break

            if progress_callback:
                progress_callback(
                    int((i / max(1, total)) * 100),
                    f"更新 {info.name} ({i+1}/{total})"
                )

            result = self.update_plugin(info)
            results.append(result)

        return results

    # ========================================================
    # 下载
    # ========================================================
    def _download_update(self, url: str, name: str,
                          progress_callback: Optional[Callable] = None
                          ) -> Optional[bytes]:
        """
        下载更新包。

        返回:
            字节数据或 None
        """
        if not url:
            return None

        for attempt in range(MAX_RETRIES):
            if self._cancelled:
                return None

            resp = None
            try:
                import requests
                resp = requests.get(
                    url, timeout=DOWNLOAD_TIMEOUT, stream=True
                )

                if resp.status_code != 200:
                    print(f"[PluginUpdater] 下载失败: HTTP {resp.status_code}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)
                        continue
                    return None

                # 获取总大小
                total_size = int(resp.headers.get('content-length', 0))

                # 流式下载
                chunks = []
                downloaded = 0

                for chunk in resp.iter_content(chunk_size=8192):
                    if self._cancelled:
                        return None

                    chunks.append(chunk)
                    downloaded += len(chunk)

                    if total_size > 0 and progress_callback:
                        pct = 5 + int((downloaded / total_size) * 50)
                        progress_callback(
                            pct,
                            f"下载中 {downloaded // 1024}/{total_size // 1024} KB"
                        )

                return b''.join(chunks)

            except ImportError:
                # urllib 回退
                try:
                    import urllib.request
                    with urllib.request.urlopen(
                        url, timeout=DOWNLOAD_TIMEOUT
                    ) as f:
                        return f.read()
                except Exception as e:
                    print(f"[PluginUpdater] urllib 下载失败: {e}")
            except Exception as e:
                print(f"[PluginUpdater] 下载异常: {e}")
            finally:
                # F1 修复：finally 保证 resp 关闭
                if resp is not None:
                    try:
                        resp.close()
                    except Exception:
                        pass

            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))

        return None

    # ========================================================
    # 备份与回滚
    # ========================================================
    def _backup_plugin(self, name: str) -> Optional[str]:
        """
        备份插件目录。

        参数:
            name: 插件名

        返回:
            备份路径或 None
        """
        try:
            source_dir = os.path.join(self.plugin_dir, name)

            # 主题特殊处理
            if name.startswith("theme."):
                theme_name = name[6:]
                source_file = os.path.join(
                    self.theme_dir, f"{theme_name}.json"
                )

                if not os.path.exists(source_file):
                    return None

                timestamp = datetime.datetime.now().strftime(
                    "%Y%m%d_%H%M%S"
                )
                backup_name = f"{name}_{timestamp}.json"
                backup_path = os.path.join(BACKUP_DIR, backup_name)

                shutil.copy2(source_file, backup_path)

                return backup_path

            # 插件目录
            if not os.path.isdir(source_dir):
                return None

            timestamp = datetime.datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )
            backup_name = f"{name}_{timestamp}"
            backup_path = os.path.join(BACKUP_DIR, backup_name)

            shutil.copytree(source_dir, backup_path)

            # 清理旧备份
            self._cleanup_old_backups(name)

            return backup_path

        except Exception as e:
            print(f"[PluginUpdater] 备份失败: {e}")
            return None

    def _cleanup_old_backups(self, name: str):
        """清理旧备份，只保留最近 N 个"""
        try:
            backups = []
            for item in os.listdir(BACKUP_DIR):
                if item.startswith(f"{name}_"):
                    path = os.path.join(BACKUP_DIR, item)
                    backups.append((path, os.path.getmtime(path)))

            # 按时间排序
            backups.sort(key=lambda x: x[1], reverse=True)

            # 删除超出数量的
            for path, _ in backups[MAX_BACKUPS:]:
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                except Exception:
                    pass

        except Exception:
            pass

    def _rollback(self, name: str, backup_path: str) -> bool:
        """
        回滚插件到备份状态。

        参数:
            name: 插件名
            backup_path: 备份路径

        返回:
            是否成功
        """
        if not backup_path or not os.path.exists(backup_path):
            print(f"[PluginUpdater] 备份不存在: {backup_path}")
            return False

        self._state = UpdateState.ROLLING_BACK

        try:
            # 主题回滚
            if name.startswith("theme."):
                theme_name = name[6:]
                target_file = os.path.join(
                    self.theme_dir, f"{theme_name}.json"
                )

                shutil.copy2(backup_path, target_file)
            else:
                target_dir = os.path.join(self.plugin_dir, name)

                # 删除当前
                if os.path.exists(target_dir):
                    shutil.rmtree(target_dir)

                # 恢复备份
                shutil.copytree(backup_path, target_dir)

            print(f"[PluginUpdater] 已回滚: {name}")

            self.rollback_finished.emit(name, True)

            return True

        except Exception as e:
            print(f"[PluginUpdater] 回滚失败 ({name}): {e}")
            self.rollback_finished.emit(name, False)
            return False

    # ========================================================
    # 安装
    # ========================================================
    def _install_update(self, data: bytes, name: str,
                         version: str) -> Tuple[bool, str]:
        """
        安装更新包。

        参数:
            data: 下载的数据
            name: 插件名
            version: 版本

        返回:
            (是否成功, 错误信息)
        """
        self._state = UpdateState.EXTRACTING

        tmp_path = None
        extract_dir = None

        try:
            # 写入临时文件
            with tempfile.NamedTemporaryFile(
                delete=False, suffix='.zip'
            ) as tmp:
                tmp.write(data)
                tmp_path = tmp.name

            # 主题特殊处理
            if name.startswith("theme."):
                theme_name = name[6:]
                return self._install_theme(
                    tmp_path, theme_name, version
                )

            # 解压到临时目录
            extract_dir = tempfile.mkdtemp(prefix="plugin_extract_")

            with zipfile.ZipFile(tmp_path, 'r') as zf:
                # 检查压缩包结构
                names = zf.namelist()
                if not names:
                    return (False, "压缩包为空")

                # 检查是否有顶层目录
                top_level = set()
                for n in names:
                    parts = n.split('/')
                    if parts:
                        top_level.add(parts[0])

                # 解压
                zf.extractall(extract_dir)

            # 确定插件源目录
            if len(top_level) == 1:
                top_dir = list(top_level)[0]
                if top_dir != name:
                    # 压缩包内是其他目录名，使用它
                    source_dir = os.path.join(extract_dir, top_dir)
                else:
                    source_dir = os.path.join(extract_dir, name)
            else:
                # 多顶层目录，使用解压根目录
                source_dir = extract_dir

            if not os.path.isdir(source_dir):
                return (False, "无效的插件结构")

            # 原子替换
            self._state = UpdateState.INSTALLING

            target_dir = os.path.join(self.plugin_dir, name)

            # 删除旧版本
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)

            # 移动新版本
            shutil.move(source_dir, target_dir)

            return (True, "")

        except zipfile.BadZipFile:
            return (False, "压缩包格式错误")
        except Exception as e:
            return (False, str(e))
        finally:
            # 清理临时文件
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

            if extract_dir:
                try:
                    shutil.rmtree(extract_dir, ignore_errors=True)
                except Exception:
                    pass

    def _install_theme(self, tmp_path: str, theme_name: str,
                        version: str) -> Tuple[bool, str]:
        """安装主题"""
        try:
            with zipfile.ZipFile(tmp_path, 'r') as zf:
                # 找 JSON 文件
                json_files = [
                    n for n in zf.namelist()
                    if n.endswith('.json')
                ]

                if not json_files:
                    return (False, "压缩包中无 JSON 文件")

                target_file = os.path.join(
                    self.theme_dir, f"{theme_name}.json"
                )

                # 提取 JSON
                with zf.open(json_files[0]) as src:
                    content = src.read()

                # 写入
                with open(target_file, 'wb') as dst:
                    dst.write(content)

                return (True, "")

        except Exception as e:
            return (False, str(e))

    # ========================================================
    # 依赖管理
    # ========================================================
    def _check_dependencies(self, info: UpdateInfo) -> bool:
        """检查依赖"""
        # 检查插件依赖
        for dep_name in info.plugin_dependencies:
            dep_dir = os.path.join(self.plugin_dir, dep_name)
            if not os.path.isdir(dep_dir):
                print(f"[PluginUpdater] 缺少插件依赖: {dep_name}")
                return False

        return True

    def _install_python_dependencies(self, dependencies: List[str]):
        """安装 Python 依赖"""
        if not dependencies:
            return

        try:
            import subprocess

            cmd = [sys.executable, '-m', 'pip', 'install']
            cmd.extend(dependencies)

            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=120
            )

            if result.returncode != 0:
                print(f"[PluginUpdater] 依赖安装失败: {result.stderr}")

        except Exception as e:
            print(f"[PluginUpdater] 依赖安装异常: {e}")

    # ========================================================
    # 历史记录
    # ========================================================
    def _load_history(self):
        """加载更新历史"""
        try:
            if os.path.exists(UPDATE_HISTORY_FILE):
                with open(UPDATE_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                self._history = [
                    UpdateHistoryEntry.from_dict(item)
                    for item in data
                ]

        except Exception as e:
            print(f"[PluginUpdater] 加载历史失败: {e}")
            self._history = []

    def _save_history(self):
        """保存更新历史"""
        try:
            os.makedirs(os.path.dirname(UPDATE_HISTORY_FILE), exist_ok=True)

            # 只保留最近 100 条
            self._history = self._history[-100:]

            with open(UPDATE_HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(
                    [entry.to_dict() for entry in self._history],
                    f, indent=2, ensure_ascii=False
                )

        except Exception as e:
            print(f"[PluginUpdater] 保存历史失败: {e}")

    def _add_history(self, entry: UpdateHistoryEntry):
        """添加历史记录"""
        self._history.append(entry)
        self._save_history()

    def get_history(self, limit: int = 50) -> List[UpdateHistoryEntry]:
        """获取更新历史"""
        return self._history[-limit:]

    def clear_history(self):
        """清空更新历史"""
        self._history = []
        self._save_history()

    # ========================================================
    # 配置管理
    # ========================================================
    def _load_config(self):
        """加载配置"""
        try:
            from PyQt5.QtCore import QSettings
            settings = QSettings("QingCao", "PluginUpdater")

            self._auto_check_enabled = settings.value(
                "auto_check_enabled", True, type=bool
            )
            self._auto_check_interval = settings.value(
                "auto_check_interval", DEFAULT_AUTO_CHECK_INTERVAL, type=int
            )
            self._update_channel = settings.value(
                "update_channel", "stable", type=str
            )
            self._last_check_time = settings.value(
                "last_check_time", 0.0, type=float
            )

        except Exception:
            pass

    def _save_config(self):
        """保存配置"""
        try:
            from PyQt5.QtCore import QSettings
            settings = QSettings("QingCao", "PluginUpdater")

            settings.setValue(
                "auto_check_enabled", self._auto_check_enabled
            )
            settings.setValue(
                "auto_check_interval", self._auto_check_interval
            )
            settings.setValue("update_channel", self._update_channel)
            settings.setValue("last_check_time", self._last_check_time)

        except Exception:
            pass

    def set_auto_check(self, enabled: bool):
        """启用/禁用自动检查"""
        self._auto_check_enabled = enabled

        if enabled:
            self.start_auto_check()
        else:
            self.stop_auto_check()

        self._save_config()

    def set_auto_check_interval(self, hours: int):
        """设置自动检查间隔"""
        self._auto_check_interval = max(1, hours)
        self._auto_check_timer.setInterval(hours * 3600 * 1000)

        if self._auto_check_timer.isActive():
            self._auto_check_timer.start()

        self._save_config()

    def set_update_channel(self, channel: str):
        """设置更新通道"""
        if channel in UPDATE_CHANNELS:
            self._update_channel = channel
            self._save_config()

    def start_auto_check(self):
        """启动自动检查"""
        if self._auto_check_enabled:
            # 检查是否需要立即检查
            elapsed = time.time() - self._last_check_time
            if elapsed > self._auto_check_interval * 3600:
                QTimer.singleShot(5000, self._on_auto_check)

            self._auto_check_timer.start()

    def stop_auto_check(self):
        """停止自动检查"""
        self._auto_check_timer.stop()

    def _on_auto_check(self):
        """自动检查触发"""
        if not self._auto_check_enabled:
            return

        self.auto_check_triggered.emit()

        # 后台执行检查
        def do_check():
            try:
                updates = self.check_updates(force=False)
                if updates:
                    print(f"[PluginUpdater] 自动检查发现 "
                          f"{len(updates)} 个更新")
            except Exception as e:
                print(f"[PluginUpdater] 自动检查失败: {e}")

        thread = threading.Thread(target=do_check, daemon=True)
        thread.start()

    # ========================================================
    # 工具方法
    # ========================================================
    def compare_versions(self, v1: str, v2: str) -> int:
        """
        比较两个版本号。

        返回:
            -1 表示 v1 < v2
             0 表示相等
             1 表示 v1 > v2
        """
        return SemVer(v1)._compare(SemVer(v2))

    def is_newer(self, current: str, latest: str) -> bool:
        """检查 latest 是否比 current 更新"""
        return SemVer(latest) > SemVer(current)

    def get_cached_update_info(self, name: str
                                ) -> Optional[UpdateInfo]:
        """从缓存获取更新信息"""
        # 简单实现：不缓存单项更新信息
        return None

    def get_config(self) -> Dict[str, Any]:
        """获取当前配置"""
        return {
            'auto_check_enabled': self._auto_check_enabled,
            'auto_check_interval': self._auto_check_interval,
            'update_channel': self._update_channel,
            'last_check_time': self._last_check_time,
            'channel_display': UPDATE_CHANNELS.get(
                self._update_channel, self._update_channel
            ),
        }

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出更新器信息"""
        lines = ["PluginUpdater", "=" * 60]
        lines.append(f"状态: {self._state.name}")
        lines.append(f"插件目录: {self.plugin_dir}")
        lines.append(f"注册表: {self.registry_url}")
        lines.append(f"更新通道: {self._update_channel}")
        lines.append(f"自动检查: {self._auto_check_enabled}")
        lines.append(f"检查间隔: {self._auto_check_interval} 小时")

        if self._last_check_time > 0:
            last_time = datetime.datetime.fromtimestamp(
                self._last_check_time
            )
            lines.append(
                f"上次检查: {last_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )

        lines.append(f"历史记录: {len(self._history)} 条")

        if self._history:
            lines.append("")
            lines.append("最近更新:")
            for entry in self._history[-5:]:
                status = "✓" if entry.success else "✗"
                lines.append(
                    f"  {status} {entry.name} "
                    f"{entry.old_version}→{entry.new_version}"
                )

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<PluginUpdater state={self._state.name} "
                f"channel={self._update_channel} "
                f"history={len(self._history)}>")


# ============================================================
# 便捷函数
# ============================================================
def check_for_updates(plugin_dir: str = PLUGINS_DIR,
                       registry_url: str = DEFAULT_REGISTRY_URL
                       ) -> List[UpdateInfo]:
    """
    快速检查更新。

    参数:
        plugin_dir: 插件目录
        registry_url: 注册表地址

    返回:
        UpdateInfo 列表
    """
    updater = PluginUpdater(
        plugin_dir=plugin_dir,
        registry_url=registry_url,
    )
    return updater.check_updates()


def update_plugin_by_name(name: str,
                           plugin_dir: str = PLUGINS_DIR,
                           registry_url: str = DEFAULT_REGISTRY_URL
                           ) -> Optional[UpdateResult]:
    """
    快速更新指定插件。

    参数:
        name: 插件名
        plugin_dir: 插件目录
        registry_url: 注册表地址

    返回:
        UpdateResult 或 None
    """
    updater = PluginUpdater(
        plugin_dir=plugin_dir,
        registry_url=registry_url,
    )

    updates = updater.check_updates()

    for info in updates:
        if info.name == name:
            return updater.update_plugin(info)

    return None


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    print("=== 测试 SemVer ===")
    test_cases = [
        ("1.0.0", "1.0.1", -1),
        ("1.0.1", "1.0.0", 1),
        ("1.0.0", "1.0.0", 0),
        ("2.0.0", "1.9.9", 1),
        ("1.0.0-alpha", "1.0.0", -1),
        ("1.0.0", "1.0.0-beta", 1),
        ("1.0.0-alpha", "1.0.0-beta", -1),
    ]

    for v1, v2, expected in test_cases:
        result = SemVer(v1)._compare(SemVer(v2))
        status = "✓" if result == expected else "✗"
        print(f"  {status} {v1} vs {v2}: {result} (期望 {expected})")

    print()

    # 测试更新器
    print("=== 测试 PluginUpdater ===")
    updater = PluginUpdater()

    print(updater.dump())
    print()

    # 连接信号
    updater.check_started.connect(
        lambda: print("[信号] 检查开始")
    )
    updater.check_finished.connect(
        lambda updates: print(f"[信号] 检查完成: {len(updates)} 个更新")
    )
    updater.update_started.connect(
        lambda name: print(f"[信号] 更新开始: {name}")
    )
    updater.update_progress.connect(
        lambda name, pct, status: print(f"[信号] {name}: {pct}% - {status}")
    )
    updater.update_finished.connect(
        lambda result: print(f"[信号] 更新完成: {result.get_summary()}")
    )

    # 测试版本比较
    print()
    print("=== 测试版本比较 ===")
    print(f"1.0.0 < 1.1.0: {updater.is_newer('1.0.0', '1.1.0')}")
    print(f"2.0.0 > 1.9.9: {updater.is_newer('2.0.0', '1.9.9')}")
    print()

    # 测试更新历史
    print("=== 测试更新历史 ===")
    updater._add_history(UpdateHistoryEntry(
        name="test_plugin",
        old_version="1.0.0",
        new_version="1.1.0",
        success=True,
        timestamp=datetime.datetime.now().isoformat(),
        message="测试更新",
    ))

    history = updater.get_history()
    print(f"历史记录数: {len(history)}")
    for entry in history:
        print(f"  {entry}")
    print()

    # 测试配置
    print("=== 当前配置 ===")
    config = updater.get_config()
    for k, v in config.items():
        print(f"  {k}: {v}")
    print()

    print("测试完成。")
    sys.exit(0)