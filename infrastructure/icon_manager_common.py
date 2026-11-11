#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为图标管理器模块，包含：
- IconManager：图标管理器（单例）
- IconProvider：图标提供者基类
- SVGIconProvider：SVG 文件图标提供者
- PNGIconProvider：PNG 文件图标提供者
- ThemeIconProvider：系统主题图标提供者
- BuiltinIconProvider：内置图标提供者（程序化绘制）
- EmojiIconProvider：Emoji 图标提供者
- IconCache：图标缓存
- 多尺寸图标支持
- 图标颜色主题化
- 图标热重载
- 图标目录扫描
- 图标别名映射
- 图标回退机制
"""

import hashlib
import json
import os
import sys
import threading
import time
from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSettings,
    QSize,
    Qt,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygon,
    QPolygonF,
    QTransform,
)
from PyQt5.QtWidgets import QApplication, QStyle


# ============================================================
# 常量
# ============================================================
# 默认图标目录
def _default_icon_dir() -> str:
    """资源目录用绝对路径（相对路径随工作目录变化）"""
    try:
        from infrastructure.plugin_loader import app_root_dir

        return os.path.join(app_root_dir(), "resources", "icons")
    except Exception:  # pragma: no cover
        return os.path.join("resources", "icons")


DEFAULT_ICON_DIR = _default_icon_dir()

# 内置图标尺寸
DEFAULT_ICON_SIZES = [16, 20, 24, 32, 48, 64, 96, 128]

# 默认图标尺寸
DEFAULT_ICON_SIZE = 16

# 图标缓存最大容量
MAX_CACHE_SIZE = 500

# 缓存过期时间（秒）
CACHE_TTL = 3600

# 图标文件扩展名
ICON_EXTENSIONS = (".svg", ".png", ".ico", ".jpg", ".jpeg", ".gif", ".bmp")

# 支持的图标格式优先级
EXTENSION_PRIORITY = {
    ".svg": 0,
    ".png": 1,
    ".ico": 2,
    ".jpg": 3,
    ".jpeg": 4,
    ".gif": 5,
    ".bmp": 6,
}


# ============================================================
# 图标状态枚举
# ============================================================
class IconState(Enum):
    """图标状态"""

    NORMAL = auto()  # 普通
    DISABLED = auto()  # 禁用
    ACTIVE = auto()  # 激活
    SELECTED = auto()  # 选中
    HOVER = auto()  # 悬停
    CHECKED = auto()  # 勾选


# ============================================================
# 图标缓存条目
# ============================================================
class CacheEntry:
    """图标缓存条目"""

    def __init__(self, icon: QIcon, timestamp: float = None):
        self.icon = icon
        self.timestamp = timestamp or time.time()
        self.access_count = 0
        self.last_access = time.time()

    def is_expired(self, ttl: float = CACHE_TTL) -> bool:
        """是否过期"""
        return (time.time() - self.timestamp) > ttl

    def touch(self):
        """更新访问时间"""
        self.access_count += 1
        self.last_access = time.time()


# ============================================================
# 图标缓存
# ============================================================

__all__ = [n for n in dir() if not n.startswith("__")]
