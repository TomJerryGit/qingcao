#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
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

import datetime
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import zipfile
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


# ============================================================
# 常量
# ============================================================
# 默认注册表地址
DEFAULT_REGISTRY_URL = (
    "https://raw.githubusercontent.com/qingcao-editor/plugins-registry/main/registry.json"
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

    IDLE = auto()  # 空闲
    CHECKING = auto()  # 检查中
    DOWNLOADING = auto()  # 下载中
    EXTRACTING = auto()  # 解压中
    INSTALLING = auto()  # 安装中
    COMPLETED = auto()  # 完成
    FAILED = auto()  # 失败
    CANCELLED = auto()  # 已取消
    ROLLING_BACK = auto()  # 回滚中


# ============================================================
# 更新信息
# ============================================================


@dataclass
class UpdateInfo:
    """
    单个插件的更新信息。
    """

    # 基本信息
    name: str = ""  # 插件名
    display_name: str = ""  # 显示名
    current_version: str = ""  # 当前版本
    latest_version: str = ""  # 最新版本

    # 更新内容
    description: str = ""  # 更新说明
    changelog: str = ""  # 变更日志
    release_date: str = ""  # 发布日期

    # 下载信息
    download_url: str = ""  # 下载地址
    file_hash: str = ""  # 文件哈希
    file_size: int = 0  # 文件大小

    # 依赖
    dependencies: List[str] = field(default_factory=list)
    plugin_dependencies: List[str] = field(default_factory=list)

    # 兼容性
    min_app_version: str = ""  # 最低应用版本
    max_app_version: str = ""  # 最高应用版本（"" = 不限）

    # 状态
    has_update: bool = False  # 是否有更新
    is_major: bool = False  # 是否主版本更新
    is_security: bool = False  # 是否安全更新
    forced: bool = False  # 是否强制更新

    # 通道
    channel: str = "stable"  # 更新通道

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
        return f"{self.display_name or self.name}: {self.current_version} → {self.latest_version}"

    def __repr__(self) -> str:
        return (
            f"<UpdateInfo {self.name} "
            f"{self.current_version}->{self.latest_version} "
            f"has_update={self.has_update}>"
        )


# ============================================================
# 更新结果
# ============================================================


@dataclass
class UpdateResult:
    """
    更新操作的结果。
    """

    success: bool = False  # 是否成功
    name: str = ""  # 插件名
    old_version: str = ""  # 旧版本
    new_version: str = ""  # 新版本
    message: str = ""  # 结果消息
    error: str = ""  # 错误信息

    # 时间统计
    download_ms: float = 0.0  # 下载耗时
    install_ms: float = 0.0  # 安装耗时
    total_ms: float = 0.0  # 总耗时

    # 备份路径（用于回滚）
    backup_path: str = ""

    # 状态
    state: UpdateState = UpdateState.IDLE

    def get_summary(self) -> str:
        """获取摘要"""
        if self.success:
            return f"{self.name}: {self.old_version} → {self.new_version} ({self.total_ms:.0f} ms)"
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
    def from_dict(cls, d: Dict[str, Any]) -> "UpdateHistoryEntry":
        entry = cls()
        for key, value in d.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        return entry

    def __repr__(self) -> str:
        status = "✓" if self.success else "✗"
        return (
            f"<UpdateHistory {status} {self.name} "
            f"{self.old_version}->{self.new_version} "
            f"@ {self.timestamp[:19]}>"
        )


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
            if "+" in version:
                version, self.build = version.split("+", 1)

            # 分离 prerelease
            if "-" in version:
                version, self.prerelease = version.split("-", 1)

            parts = version.split(".")

            if len(parts) >= 1:
                self.major = int(parts[0]) if parts[0].isdigit() else 0
            if len(parts) >= 2:
                self.minor = int(parts[1]) if parts[1].isdigit() else 0
            if len(parts) >= 3:
                self.patch = int(parts[2]) if parts[2].isdigit() else 0

        except Exception:
            pass

    def __eq__(self, other: "SemVer") -> bool:
        return self.major == other.major and self.minor == other.minor and self.patch == other.patch

    def __lt__(self, other: "SemVer") -> bool:
        return self._compare(other) < 0

    def __gt__(self, other: "SemVer") -> bool:
        return self._compare(other) > 0

    def __le__(self, other: "SemVer") -> bool:
        return self._compare(other) <= 0

    def __ge__(self, other: "SemVer") -> bool:
        return self._compare(other) >= 0

    def _compare(self, other: "SemVer") -> int:
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

    def is_major_update(self, other: "SemVer") -> bool:
        """检查是否主版本更新"""
        return other.major > self.major

    def __str__(self) -> str:
        return self.raw

    def __repr__(self) -> str:
        return f"<SemVer {self.raw}>"


# ============================================================
# 插件更新器
# ============================================================

__all__ = [n for n in dir() if not n.startswith("__")]
