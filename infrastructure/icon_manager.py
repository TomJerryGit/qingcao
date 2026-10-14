#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
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
ICON_EXTENSIONS = ('.svg', '.png', '.ico', '.jpg', '.jpeg', '.gif', '.bmp')

# 支持的图标格式优先级
EXTENSION_PRIORITY = {
    '.svg': 0,
    '.png': 1,
    '.ico': 2,
    '.jpg': 3,
    '.jpeg': 4,
    '.gif': 5,
    '.bmp': 6,
}


# ============================================================
# 图标状态枚举
# ============================================================
class IconState(Enum):
    """图标状态"""
    NORMAL = auto()      # 普通
    DISABLED = auto()    # 禁用
    ACTIVE = auto()      # 激活
    SELECTED = auto()    # 选中
    HOVER = auto()       # 悬停
    CHECKED = auto()     # 勾选


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
class IconCache:
    """
    图标缓存。

    线程安全的 LRU 缓存，支持过期清理。
    """

    def __init__(self, max_size: int = MAX_CACHE_SIZE,
                 ttl: float = CACHE_TTL):
        self.max_size = max_size
        self.ttl = ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[QIcon]:
        """获取缓存图标"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            if entry.is_expired(self.ttl):
                del self._cache[key]
                return None

            entry.touch()
            return entry.icon

    def put(self, key: str, icon: QIcon):
        """写入缓存"""
        with self._lock:
            # 检查容量
            if len(self._cache) >= self.max_size:
                self._evict_lru()

            self._cache[key] = CacheEntry(icon)

    def _evict_lru(self):
        """淘汰最久未使用的条目"""
        if not self._cache:
            return

        # 找到最久未访问的
        lru_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_access
        )
        del self._cache[lru_key]

    def invalidate(self, key: str):
        """使指定键失效"""
        with self._lock:
            self._cache.pop(key, None)

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()

    def cleanup(self):
        """清理过期条目"""
        with self._lock:
            expired = [
                k for k, v in self._cache.items()
                if v.is_expired(self.ttl)
            ]
            for k in expired:
                del self._cache[k]

    def size(self) -> int:
        """当前缓存大小"""
        return len(self._cache)

    def stats(self) -> Dict[str, Any]:
        """缓存统计"""
        with self._lock:
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'ttl': self.ttl,
                'total_access': sum(
                    e.access_count for e in self._cache.values()
                ),
            }


# ============================================================
# 图标提供者基类
# ============================================================
class IconProvider(ABC):
    """
    图标提供者抽象基类。

    子类需实现:
    - can_provide(name): 是否能提供图标
    - get_icon(name, size, color): 获取图标
    """

    def __init__(self):
        self.priority = 100  # 优先级，越小越先尝试

    @abstractmethod
    def can_provide(self, name: str) -> bool:
        """检查是否能提供指定名称的图标"""
        pass

    @abstractmethod
    def get_icon(self, name: str, size: int = DEFAULT_ICON_SIZE,
                 color: Optional[str] = None) -> Optional[QIcon]:
        """获取图标"""
        pass

    def get_pixmap(self, name: str, size: int = DEFAULT_ICON_SIZE,
                   color: Optional[str] = None) -> Optional[QPixmap]:
        """获取图标 Pixmap"""
        icon = self.get_icon(name, size, color)
        if icon:
            return icon.pixmap(size, size)
        return None

    def list_icons(self) -> List[str]:
        """列出所有可用的图标名称"""
        return []


# ============================================================
# SVG 图标提供者
# ============================================================
class SVGIconProvider(IconProvider):
    """
    SVG 图标提供者。

    从目录中加载 SVG 文件，支持动态颜色。
    """

    def __init__(self, icon_dir: str = DEFAULT_ICON_DIR):
        super().__init__()
        self.priority = 10  # 最高优先级

        self.icon_dir = icon_dir
        self._icons: Dict[str, str] = {}  # name -> filepath
        self._svg_data: Dict[str, bytes] = {}  # name -> content

        self._scan()

    def _scan(self):
        """扫描目录"""
        if not os.path.isdir(self.icon_dir):
            return

        for filename in os.listdir(self.icon_dir):
            if not filename.endswith('.svg'):
                continue

            name = os.path.splitext(filename)[0]
            filepath = os.path.join(self.icon_dir, filename)
            self._icons[name] = filepath

    def reload(self):
        """重新扫描"""
        self._icons.clear()
        self._svg_data.clear()
        self._scan()

    def can_provide(self, name: str) -> bool:
        return name in self._icons

    def get_icon(self, name: str, size: int = DEFAULT_ICON_SIZE,
                 color: Optional[str] = None) -> Optional[QIcon]:
        """获取 SVG 图标"""
        filepath = self._icons.get(name)
        if not filepath or not os.path.exists(filepath):
            return None

        try:
            if color:
                # 动态着色：读取 SVG，替换颜色
                pixmap = self._render_colored_svg(filepath, size, color)
                if pixmap:
                    return QIcon(pixmap)
            else:
                # 直接使用 QIcon
                icon = QIcon(filepath)
                if not icon.isNull():
                    return icon

        except Exception as e:
            print(f"[SVGIconProvider] 加载失败 ({name}): {e}")

        return None

    def _render_colored_svg(self, filepath: str, size: int,
                             color: str) -> Optional[QPixmap]:
        """渲染带颜色的 SVG"""
        try:
            # 读取 SVG 内容
            if filepath not in self._svg_data:
                with open(filepath, 'rb') as f:
                    self._svg_data[filepath] = f.read()

            content = self._svg_data[filepath].decode('utf-8')

            # 简单替换 currentColor 和 fill
            content = content.replace('currentColor', color)
            content = content.replace('fill="#000"', f'fill="{color}"')
            content = content.replace('fill="#000000"', f'fill="{color}"')
            content = content.replace('stroke="#000"', f'stroke="{color}"')
            content = content.replace('stroke="#000000"',
                                       f'stroke="{color}"')

            # 使用 QPixmap 加载 SVG（Qt 6.x 内建 SVG 支持）
            pixmap = QPixmap()
            if pixmap.loadFromData(content.encode('utf-8'), 'SVG'):
                if pixmap.width() != size:
                    pixmap = pixmap.scaled(
                        size, size,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                return pixmap

        except Exception as e:
            print(f"[SVGIconProvider] 渲染失败: {e}")

        return None

    def list_icons(self) -> List[str]:
        return list(self._icons.keys())


# ============================================================
# PNG 图标提供者
# ============================================================
class PNGIconProvider(IconProvider):
    """
    PNG 图标提供者。

    从目录中加载 PNG/ICO 等位图图标。
    """

    def __init__(self, icon_dir: str = DEFAULT_ICON_DIR):
        super().__init__()
        self.priority = 20

        self.icon_dir = icon_dir
        self._icons: Dict[str, str] = {}

        self._scan()

    def _scan(self):
        """扫描目录"""
        if not os.path.isdir(self.icon_dir):
            return

        # 按扩展名优先级排序
        candidates: Dict[str, List[str]] = {}

        for filename in os.listdir(self.icon_dir):
            ext = os.path.splitext(filename)[1].lower()

            if ext == '.svg':
                continue  # SVG 由 SVGIconProvider 处理

            if ext not in ICON_EXTENSIONS:
                continue

            name = os.path.splitext(filename)[0]
            candidates.setdefault(name, []).append(filename)

        # 选择优先级最高的
        for name, files in candidates.items():
            files.sort(key=lambda f: EXTENSION_PRIORITY.get(
                os.path.splitext(f)[1].lower(), 999
            ))
            self._icons[name] = os.path.join(self.icon_dir, files[0])

    def reload(self):
        """重新扫描"""
        self._icons.clear()
        self._scan()

    def can_provide(self, name: str) -> bool:
        return name in self._icons

    def get_icon(self, name: str, size: int = DEFAULT_ICON_SIZE,
                 color: Optional[str] = None) -> Optional[QIcon]:
        """获取位图图标"""
        filepath = self._icons.get(name)
        if not filepath or not os.path.exists(filepath):
            return None

        try:
            icon = QIcon(filepath)
            if not icon.isNull():
                return icon
        except Exception as e:
            print(f"[PNGIconProvider] 加载失败 ({name}): {e}")

        return None

    def list_icons(self) -> List[str]:
        return list(self._icons.keys())


# ============================================================
# 系统主题图标提供者
# ============================================================
class ThemeIconProvider(IconProvider):
    """
    系统主题图标提供者。

    使用 Qt 内置的标准图标和系统主题图标。
    """

    # 名称到 QStyle 标准图标的映射
    STANDARD_ICONS = {
        # 文件操作
        'file': QStyle.SP_FileIcon,
        'file_new': QStyle.SP_FileIcon,
        'file_open': QStyle.SP_DialogOpenButton,
        'file_save': QStyle.SP_DialogSaveButton,
        'folder': QStyle.SP_DirIcon,
        'folder_open': QStyle.SP_DirOpenIcon,
        'folder_closed': QStyle.SP_DirClosedIcon,
        'file_dialog': QStyle.SP_FileDialogDetailedView,
        'file_dialog_info': QStyle.SP_FileDialogInfoView,
        'file_dialog_contents': QStyle.SP_FileDialogContentsView,
        'file_dialog_list': QStyle.SP_FileDialogListView,
        'file_dialog_new': QStyle.SP_FileDialogNewFolder,
        'file_dialog_start': QStyle.SP_FileDialogStart,
        'file_dialog_end': QStyle.SP_FileDialogEnd,
        'disk_drive': QStyle.SP_DriveHDIcon,
        'disk_fd': QStyle.SP_DriveFDIcon,
        'disk_cd': QStyle.SP_DriveCDIcon,
        'disk_dvd': QStyle.SP_DriveDVDIcon,
        'disk_net': QStyle.SP_DriveNetIcon,

        # 编辑操作
        'undo': QStyle.SP_ArrowBack,
        'redo': QStyle.SP_ArrowForward,
        'arrow_up': QStyle.SP_ArrowUp,
        'arrow_down': QStyle.SP_ArrowDown,
        'arrow_left': QStyle.SP_ArrowLeft,
        'arrow_right': QStyle.SP_ArrowRight,
        'up': QStyle.SP_ArrowUp,
        'down': QStyle.SP_ArrowDown,

        # 对话框
        'dialog_ok': QStyle.SP_DialogOkButton,
        'dialog_cancel': QStyle.SP_DialogCancelButton,
        'dialog_help': QStyle.SP_DialogHelpButton,
        'dialog_open': QStyle.SP_DialogOpenButton,
        'dialog_save': QStyle.SP_DialogSaveButton,
        'dialog_close': QStyle.SP_DialogCloseButton,
        'dialog_apply': QStyle.SP_DialogApplyButton,
        'dialog_reset': QStyle.SP_DialogResetButton,
        'dialog_discard': QStyle.SP_DialogDiscardButton,
        'dialog_yes': QStyle.SP_DialogYesButton,
        'dialog_no': QStyle.SP_DialogNoButton,

        # 消息
        'message_info': QStyle.SP_MessageBoxInformation,
        'message_warning': QStyle.SP_MessageBoxWarning,
        'message_critical': QStyle.SP_MessageBoxCritical,
        'message_question': QStyle.SP_MessageBoxQuestion,
        'info': QStyle.SP_MessageBoxInformation,
        'warning': QStyle.SP_MessageBoxWarning,
        'error': QStyle.SP_MessageBoxCritical,
        'question': QStyle.SP_MessageBoxQuestion,

        # 媒体
        'media_play': QStyle.SP_MediaPlay,
        'media_stop': QStyle.SP_MediaStop,
        'media_pause': QStyle.SP_MediaPause,
        'media_skip_forward': QStyle.SP_MediaSkipForward,
        'media_skip_backward': QStyle.SP_MediaSkipBackward,
        'media_seek_forward': QStyle.SP_MediaSeekForward,
        'media_seek_backward': QStyle.SP_MediaSeekBackward,
        'media_volume': QStyle.SP_MediaVolume,
        'media_volume_muted': QStyle.SP_MediaVolumeMuted,

        # 系统
        'trash': QStyle.SP_TrashIcon,
        'computer': QStyle.SP_ComputerIcon,
        'desktop': QStyle.SP_DesktopIcon,
        'terminal': QStyle.SP_ComputerIcon,
        'browser': QStyle.SP_BrowserReload,
        'refresh': QStyle.SP_BrowserReload,
        'stop': QStyle.SP_BrowserStop,
        'home': QStyle.SP_DirHomeIcon,
        'titlebar_menu': QStyle.SP_TitleBarMenuButton,
        'titlebar_min': QStyle.SP_TitleBarMinButton,
        'titlebar_max': QStyle.SP_TitleBarMaxButton,
        'titlebar_close': QStyle.SP_TitleBarCloseButton,
        'titlebar_normal': QStyle.SP_TitleBarNormalButton,
        'titlebar_shade': QStyle.SP_TitleBarShadeButton,
        'titlebar_unshade': QStyle.SP_TitleBarUnshadeButton,
        'titlebar_context': QStyle.SP_TitleBarContextHelpButton,

        # 其他
        'command_link': QStyle.SP_CommandLink,
        'link': QStyle.SP_CommandLink,
        'line_edit_clear': QStyle.SP_LineEditClearButton,
        'toolbar_extension': QStyle.SP_ToolBarHorizontalExtensionButton,
        'toolbar_vertical': QStyle.SP_ToolBarVerticalExtensionButton,
    }

    def __init__(self):
        super().__init__()
        self.priority = 50  # 中等优先级

    def can_provide(self, name: str) -> bool:
        return name in self.STANDARD_ICONS

    def get_icon(self, name: str, size: int = DEFAULT_ICON_SIZE,
                 color: Optional[str] = None) -> Optional[QIcon]:
        """获取系统标准图标"""
        style_icon = self.STANDARD_ICONS.get(name)
        if style_icon is None:
            return None

        try:
            app = QApplication.instance()
            if app:
                style = app.style()
                return style.standardIcon(style_icon)
        except Exception as e:
            print(f"[ThemeIconProvider] 获取失败 ({name}): {e}")

        return None

    def list_icons(self) -> List[str]:
        return list(self.STANDARD_ICONS.keys())


# ============================================================
# Emoji 图标提供者
# ============================================================
class EmojiIconProvider(IconProvider):
    """
    Emoji 图标提供者。

    使用 Unicode Emoji 字符渲染为图标。
    """

    # Emoji 名称到字符的映射
    EMOJI_ICONS = {
        # 文件
        'file': '📄',
        'file_text': '📄',
        'file_code': '📝',
        'file_python': '🐍',
        'file_js': '📜',
        'file_ts': '📘',
        'file_json': '📊',
        'file_xml': '📋',
        'file_html': '🌐',
        'file_css': '🎨',
        'file_md': '📝',
        'file_log': '📃',
        'file_csv': '📈',
        'file_image': '🖼',
        'file_audio': '🎵',
        'file_video': '🎬',
        'file_zip': '📦',
        'file_pdf': '📕',
        'file_new': '📄',
        'folder': '📁',
        'folder_open': '📂',

        # 编辑
        'new': '➕',
        'open': '📂',
        'save': '💾',
        'save_as': '💾',
        'save_all': '💾',
        'close': '✖',
        'exit': '🚪',
        'undo': '↩',
        'redo': '↪',
        'cut': '✂',
        'copy': '📋',
        'paste': '📋',
        'delete': '🗑',
        'trash': '🗑',
        'select_all': '⬜',
        'find': '🔍',
        'replace': '🔁',
        'search': '🔎',
        'goto': '📍',
        'refresh': '🔄',
        'reload': '🔄',

        # 视图
        'view': '👁',
        'zoom_in': '🔍',
        'zoom_out': '🔍',
        'fullscreen': '⛶',
        'minimize': '➖',
        'maximize': '➕',
        'restore': '🗗',

        # 工具
        'settings': '⚙',
        'tools': '🔧',
        'wrench': '🔧',
        'hammer': '🔨',
        'palette': '🎨',
        'theme': '🎨',
        'plugin': '🧩',
        'extensions': '🧩',
        'terminal': '💻',
        'console': '💻',
        'debug': '🐞',
        'bug': '🐞',
        'run': '▶',
        'play': '▶',
        'stop': '⏹',
        'pause': '⏸',
        'record': '⏺',
        'macro': '⏺',

        # 状态
        'info': 'ℹ',
        'warning': '⚠',
        'error': '✕',
        'success': '✓',
        'question': '❓',
        'help': '❓',
        'star': '⭐',
        'heart': '❤',
        'bookmark': '🔖',
        'flag': '🚩',

        # 导航
        'up': '↑',
        'down': '↓',
        'left': '←',
        'right': '→',
        'arrow_up': '⬆',
        'arrow_down': '⬇',
        'arrow_left': '⬅',
        'arrow_right': '➡',
        'expand': '⊞',
        'collapse': '⊟',
        'next': '▶',
        'prev': '◀',
        'first': '⏮',
        'last': '⏭',

        # 文件管理
        'new_file': '📄',
        'new_folder': '📁',
        'rename': '✏',
        'edit': '✏',
        'properties': 'ℹ',

        # 界面
        'menu': '☰',
        'hamburger': '☰',
        'grid': '⊞',
        'list': '☰',
        'tree': '🌳',
        'panel': '▦',
        'sidebar': '▤',
        'layout': '▦',
        'window': '🗔',

        # 语言
        'python': '🐍',
        'javascript': '📜',
        'typescript': '📘',
        'rust': '🦀',
        'go': '🐹',
        'java': '☕',
        'cpp': '⚙',
        'ruby': '💎',
        'php': '🐘',
        'swift': '🦅',

        # 其他
        'sun': '☀',
        'moon': '🌙',
        'cloud': '☁',
        'lock': '🔒',
        'unlock': '🔓',
        'eye': '👁',
        'eye_off': '👁‍🗨',
        'user': '👤',
        'users': '👥',
        'clock': '🕐',
        'calendar': '📅',
        'mail': '📧',
        'link': '🔗',
        'external_link': '🔗',
        'download': '⬇',
        'upload': '⬆',
        'share': '📤',
        'import': '📥',
        'export': '📤',
        'print': '🖨',
        'camera': '📷',
        'image': '🖼',
        'video': '🎬',
        'audio': '🎵',
        'music': '🎵',
        'lightning': '⚡',
        'fire': '🔥',
        'seedling': '🌱',  # 青草
        'leaf': '🍃',
        'tree': '🌳',
    }

    def __init__(self):
        super().__init__()
        self.priority = 80  # 低优先级（作为回退）

        # 缓存 emoji 字体
        self._font_family = self._find_emoji_font()

    def _find_emoji_font(self) -> str:
        """查找系统中可用的 Emoji 字体"""
        # Windows / macOS / Linux 的 Emoji 字体
        candidates = [
            "Segoe UI Emoji",      # Windows
            "Apple Color Emoji",    # macOS
            "Noto Color Emoji",     # Linux
            "Noto Emoji",
            "Twemoji Mozilla",
            "EmojiOne Color",
        ]

        try:
            from PyQt5.QtGui import QFontDatabase
            available = QFontDatabase.families()

            for candidate in candidates:
                if candidate in available:
                    return candidate
        except Exception:
            pass

        # 回退到系统默认
        return "Segoe UI Emoji"

    def can_provide(self, name: str) -> bool:
        return name in self.EMOJI_ICONS

    def get_icon(self, name: str, size: int = DEFAULT_ICON_SIZE,
                 color: Optional[str] = None) -> Optional[QIcon]:
        """获取 Emoji 图标"""
        emoji = self.EMOJI_ICONS.get(name)
        if not emoji:
            return None

        try:
            pixmap = self._render_emoji(emoji, size, color)
            if pixmap:
                return QIcon(pixmap)
        except Exception as e:
            print(f"[EmojiIconProvider] 渲染失败 ({name}): {e}")

        return None

    def _render_emoji(self, emoji: str, size: int,
                       color: Optional[str] = None) -> Optional[QPixmap]:
        """渲染 Emoji 到 Pixmap"""
        try:
            # 使用稍大的尺寸以容纳 emoji
            render_size = int(size * 1.4)

            pixmap = QPixmap(render_size, render_size)
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)

            # 设置字体
            font = QFont(self._font_family)
            font.setPixelSize(int(render_size * 0.75))
            painter.setFont(font)

            # 颜色（Emoji 通常使用彩色，但可以为单色 emoji 设置颜色）
            if color:
                painter.setPen(QColor(color))
            else:
                painter.setPen(Qt.black)

            # 居中绘制
            rect = QRectF(0, 0, render_size, render_size)
            painter.drawText(
                rect,
                Qt.AlignCenter,
                emoji
            )

            painter.end()

            # 缩放回目标尺寸
            if render_size != size:
                pixmap = pixmap.scaled(
                    size, size,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )

            return pixmap

        except Exception as e:
            print(f"[EmojiIconProvider] 渲染异常: {e}")
            return None

    def list_icons(self) -> List[str]:
        return list(self.EMOJI_ICONS.keys())


# ============================================================
# 内置图标提供者（程序化绘制）
# ============================================================
class BuiltinIconProvider(IconProvider):
    """
    内置图标提供者。

    通过程序化绘制生成图标，无需外部文件。
    作为最后的回退方案。
    """

    def __init__(self):
        super().__init__()
        self.priority = 90  # 最低优先级

    def can_provide(self, name: str) -> bool:
        # 总是可以回退到默认图标
        return True

    def get_icon(self, name: str, size: int = DEFAULT_ICON_SIZE,
                 color: Optional[str] = None) -> Optional[QIcon]:
        """生成默认图标"""
        try:
            pixmap = self._draw_default_icon(name, size, color)
            if pixmap:
                return QIcon(pixmap)
        except Exception as e:
            print(f"[BuiltinIconProvider] 绘制失败 ({name}): {e}")

        return None

    def _draw_default_icon(self, name: str, size: int,
                            color: Optional[str] = None) -> Optional[QPixmap]:
        """绘制默认图标"""
        try:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)

            # 颜色
            fg_color = QColor(color) if color else QColor("#7ec850")
            bg_color = QColor("#1e1e1e")

            # 绘制圆形背景
            painter.setBrush(QBrush(bg_color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(0, 0, size - 1, size - 1)

            # 绘制字母或符号
            painter.setPen(QPen(fg_color))

            font = QFont("Arial", int(size * 0.5), QFont.Bold)
            painter.setFont(font)

            # 使用图标名的首字母
            text = name[0].upper() if name else "?"
            painter.drawText(
                QRectF(0, 0, size, size),
                Qt.AlignCenter,
                text
            )

            painter.end()

            return pixmap

        except Exception as e:
            print(f"[BuiltinIconProvider] 绘制异常: {e}")
            return None


# ============================================================
# 图标管理器
# ============================================================
class IconManager(QObject):
    """
    图标管理器（单例）。

    统一管理所有图标，支持:
    - 多提供者回退
    - 图标缓存
    - 动态颜色
    - 多尺寸
    - 别名
    - 热重载

    信号:
        icon_loaded(str): 图标加载完成（名称）
        cache_cleared(): 缓存清空
    """

    icon_loaded = pyqtSignal(str)
    cache_cleared = pyqtSignal()

    _instance: Optional['IconManager'] = None
    _lock = threading.RLock()

    def __new__(cls, *args, **kwargs):
        """单例"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, icon_dir: str = DEFAULT_ICON_DIR,
                 parent: Optional[QObject] = None):
        """
        参数:
            icon_dir: 图标目录
            parent: 父 QObject
        """
        if getattr(self, '_initialized', False):
            return

        super().__init__(parent)

        self.icon_dir = icon_dir

        # 图标缓存
        self.cache = IconCache()

        # 提供者列表（按优先级排序）
        self._providers: List[IconProvider] = []

        # 别名映射
        self._aliases: Dict[str, str] = {}

        # 初始化
        self._init_providers()
        self._init_aliases()

        self._initialized = True

    # ========================================================
    # 初始化
    # ========================================================
    def _init_providers(self):
        """初始化图标提供者"""
        providers = [
            SVGIconProvider(self.icon_dir),
            PNGIconProvider(self.icon_dir),
            ThemeIconProvider(),
            EmojiIconProvider(),
            BuiltinIconProvider(),
        ]

        # 按优先级排序
        providers.sort(key=lambda p: p.priority)
        self._providers = providers

    def _init_aliases(self):
        """初始化别名映射"""
        self._aliases = {
            # 文件操作
            'new_file': 'file_new',
            'open_file': 'file_open',
            'save_file': 'file_save',

            # 编辑
            'undo_action': 'undo',
            'redo_action': 'redo',
            'cut_action': 'cut',
            'copy_action': 'copy',
            'paste_action': 'paste',

            # 查找
            'find_action': 'find',
            'replace_action': 'replace',
            'search_action': 'search',

            # 视图
            'sidebar': 'panel',
            'bottom_panel': 'panel',
            'minimap': 'layout',

            # 文件类型
            'py': 'python',
            'js': 'javascript',
            'ts': 'typescript',
            'md': 'file_md',
            'txt': 'file_text',
            'log': 'file_log',
            'json': 'file_json',
            'xml': 'file_xml',
            'html': 'file_html',
            'css': 'file_css',

            # 状态
            'ok': 'success',
            'fail': 'error',
            'danger': 'error',
            'note': 'info',
        }

    # ========================================================
    # 获取图标
    # ========================================================
    def get(self, name: str, size: int = DEFAULT_ICON_SIZE,
            color: Optional[str] = None) -> QIcon:
        """
        获取图标。

        参数:
            name: 图标名称
            size: 尺寸（像素）
            color: 颜色（十六进制，如 "#7ec850"）

        返回:
            QIcon 实例（永不返回 None，回退到默认图标）
        """
        # 解析别名
        actual_name = self._aliases.get(name, name)

        # 生成缓存键
        cache_key = self._make_cache_key(actual_name, size, color)

        # 检查缓存
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        # 遍历提供者
        for provider in self._providers:
            try:
                if provider.can_provide(actual_name):
                    icon = provider.get_icon(actual_name, size, color)
                    if icon and not icon.isNull():
                        self.cache.put(cache_key, icon)
                        self.icon_loaded.emit(actual_name)
                        return icon
            except Exception as e:
                print(f"[IconManager] 提供者失败 "
                      f"({provider.__class__.__name__}): {e}")
                continue

        # 回退到默认图标
        return self._get_fallback_icon(name, size, color)

    def _get_fallback_icon(self, name: str, size: int,
                            color: Optional[str]) -> QIcon:
        """获取回退图标"""
        cache_key = f"__fallback__::{size}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            # 创建一个简单的默认图标
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)

            # 灰色圆点
            painter.setBrush(QBrush(QColor("#888888")))
            painter.setPen(Qt.NoPen)
            margin = max(2, size // 4)
            painter.drawEllipse(
                margin, margin,
                size - margin * 2, size - margin * 2
            )

            painter.end()

            icon = QIcon(pixmap)
            self.cache.put(cache_key, icon)
            return icon

        except Exception:
            return QIcon()

    def get_pixmap(self, name: str, size: int = DEFAULT_ICON_SIZE,
                   color: Optional[str] = None) -> QPixmap:
        """获取图标 Pixmap"""
        icon = self.get(name, size, color)
        return icon.pixmap(size, size)

    def _make_cache_key(self, name: str, size: int,
                         color: Optional[str]) -> str:
        """生成缓存键"""
        color_part = color or "default"
        return f"{name}::{size}::{color_part}"

    # ========================================================
    # 别名
    # ========================================================
    def add_alias(self, alias: str, target: str):
        """添加别名"""
        self._aliases[alias] = target

    def remove_alias(self, alias: str):
        """移除别名"""
        self._aliases.pop(alias, None)

    def resolve_alias(self, name: str) -> str:
        """解析别名"""
        return self._aliases.get(name, name)

    # ========================================================
    # 可用性检查
    # ========================================================
    def has_icon(self, name: str) -> bool:
        """检查图标是否可用"""
        actual_name = self._aliases.get(name, name)

        for provider in self._providers:
            try:
                if provider.can_provide(actual_name):
                    return True
            except Exception:
                continue

        return False

    def list_icons(self) -> List[str]:
        """列出所有可用图标名称"""
        names = set()

        for provider in self._providers:
            try:
                names.update(provider.list_icons())
            except Exception:
                continue

        return sorted(names)

    def list_icons_by_provider(self) -> Dict[str, List[str]]:
        """按提供者列出图标"""
        result = {}

        for provider in self._providers:
            provider_name = provider.__class__.__name__
            try:
                result[provider_name] = provider.list_icons()
            except Exception:
                result[provider_name] = []

        return result

    # ========================================================
    # 缓存管理
    # ========================================================
    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()
        self.cache_cleared.emit()

    def cleanup_cache(self):
        """清理过期缓存"""
        self.cache.cleanup()

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return self.cache.stats()

    # ========================================================
    # 热重载
    # ========================================================
    def reload(self):
        """重新加载所有图标"""
        # 清空缓存
        self.clear_cache()

        # 让提供者重新扫描
        for provider in self._providers:
            if hasattr(provider, 'reload'):
                try:
                    provider.reload()
                except Exception as e:
                    print(f"[IconManager] 重载失败 "
                          f"({provider.__class__.__name__}): {e}")

    def set_icon_dir(self, icon_dir: str):
        """设置图标目录"""
        self.icon_dir = icon_dir

        # 重建目录相关的提供者
        self._init_providers()
        self.clear_cache()

    # ========================================================
    # 图标组合
    # ========================================================
    def combine(self, base_name: str, overlay_name: str,
                size: int = DEFAULT_ICON_SIZE) -> QIcon:
        """
        组合两个图标（叠加）。

        参数:
            base_name: 底层图标
            overlay_name: 叠加图标
            size: 尺寸

        返回:
            组合后的 QIcon
        """
        cache_key = f"__combined__::{base_name}::{overlay_name}::{size}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            base = self.get_pixmap(base_name, size)
            overlay = self.get_pixmap(overlay_name, size // 2)

            if base.isNull():
                return QIcon()

            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)

            # 绘制底层
            painter.drawPixmap(0, 0, base)

            # 绘制叠加（右下角）
            offset = size - overlay.width()
            painter.drawPixmap(offset, offset, overlay)

            painter.end()

            icon = QIcon(pixmap)
            self.cache.put(cache_key, icon)
            return icon

        except Exception as e:
            print(f"[IconManager] 组合失败: {e}")
            return self.get(base_name, size)

    # ========================================================
    # 从颜色生成图标
    # ========================================================
    def colored_circle(self, color: str,
                        size: int = DEFAULT_ICON_SIZE) -> QIcon:
        """
        生成一个纯色圆点图标。

        参数:
            color: 颜色
            size: 尺寸

        返回:
            QIcon
        """
        cache_key = f"__circle__::{color}::{size}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.transparent)

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)

            painter.setBrush(QBrush(QColor(color)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(0, 0, size - 1, size - 1)

            painter.end()

            icon = QIcon(pixmap)
            self.cache.put(cache_key, icon)
            return icon

        except Exception as e:
            print(f"[IconManager] 生成圆点失败: {e}")
            return QIcon()

    def colored_square(self, color: str,
                        size: int = DEFAULT_ICON_SIZE) -> QIcon:
        """生成纯色方块图标"""
        cache_key = f"__square__::{color}::{size}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            pixmap = QPixmap(size, size)
            pixmap.fill(QColor(color))

            icon = QIcon(pixmap)
            self.cache.put(cache_key, icon)
            return icon

        except Exception as e:
            return QIcon()

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出管理器信息"""
        lines = ["IconManager", "=" * 60]
        lines.append(f"图标目录: {self.icon_dir}")
        lines.append(f"提供者数: {len(self._providers)}")
        lines.append(f"别名数: {len(self._aliases)}")

        stats = self.cache.stats()
        lines.append(f"缓存大小: {stats['size']}/{stats['max_size']}")

        lines.append("")
        lines.append("提供者:")
        for provider in self._providers:
            try:
                count = len(provider.list_icons())
                lines.append(
                    f"  [{provider.priority}] "
                    f"{provider.__class__.__name__}: "
                    f"{count} 个图标"
                )
            except Exception:
                lines.append(
                    f"  [{provider.priority}] "
                    f"{provider.__class__.__name__}: 错误"
                )

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<IconManager providers={len(self._providers)} "
                f"cache={self.cache.size()}>")


# ============================================================
# 全局单例访问
# ============================================================
def get_icon_manager(icon_dir: str = DEFAULT_ICON_DIR) -> IconManager:
    """
    获取全局 IconManager 单例。

    参数:
        icon_dir: 图标目录（仅首次创建时有效）

    返回:
        IconManager 实例
    """
    return IconManager(icon_dir=icon_dir)


# 便捷函数
def get_icon(name: str, size: int = DEFAULT_ICON_SIZE,
              color: Optional[str] = None) -> QIcon:
    """
    获取图标的便捷函数。

    参数:
        name: 图标名称
        size: 尺寸
        color: 颜色

    返回:
        QIcon 实例
    """
    manager = get_icon_manager()
    return manager.get(name, size, color)


def get_pixmap(name: str, size: int = DEFAULT_ICON_SIZE,
                color: Optional[str] = None) -> QPixmap:
    """获取 Pixmap 的便捷函数"""
    manager = get_icon_manager()
    return manager.get_pixmap(name, size, color)


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys
    import tempfile

    from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow

    app = QApplication(sys.argv)

    # 创建主窗口
    win = QMainWindow()
    win.setWindowTitle("IconManager 测试")
    win.resize(900, 700)

    # 创建临时图标目录
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_icon_test_")

    try:
        # 测试 IconManager
        print("=== 测试 IconManager ===")
        manager = IconManager(icon_dir=tmp_dir)

        print(manager.dump())
        print()

        # 测试系统图标
        print("=== 测试系统标准图标 ===")
        system_icons = ['file', 'folder', 'undo', 'redo',
                          'dialog_ok', 'dialog_cancel', 'trash']
        for name in system_icons:
            icon = manager.get(name, 24)
            has = manager.has_icon(name)
            print(f"  {name}: {'✓' if has else '✗'} "
                  f"({icon.availableSizes()})")
        print()

        # 测试 Emoji 图标
        print("=== 测试 Emoji 图标 ===")
        emoji_icons = ['file_python', 'folder', 'star',
                        'warning', 'success', 'seedling']
        for name in emoji_icons:
            icon = manager.get(name, 32)
            print(f"  {name}: {icon.availableSizes()}")
        print()

        # 测试别名
        print("=== 测试别名 ===")
        alias_tests = ['new_file', 'open_file', 'py', 'ok']
        for alias in alias_tests:
            resolved = manager.resolve_alias(alias)
            icon = manager.get(alias, 16)
            print(f"  {alias} -> {resolved}: "
                  f"{icon.availableSizes()}")
        print()

        # 测试缓存
        print("=== 测试缓存 ===")
        manager.clear_cache()

        # 第一次获取
        start = time.time()
        for _ in range(100):
            manager.get('file', 24)
        first_time = time.time() - start

        # 第二次获取（应该更快）
        start = time.time()
        for _ in range(100):
            manager.get('file', 24)
        second_time = time.time() - start

        print(f"  首次 100 次: {first_time * 1000:.2f} ms")
        print(f"  缓存后 100 次: {second_time * 1000:.2f} ms")
        print(f"  加速比: {first_time / max(0.0001, second_time):.1f}x")
        print()

        stats = manager.get_cache_stats()
        print(f"  缓存统计: {stats}")
        print()

        # 测试颜色着色
        print("=== 测试颜色着色 ===")
        colors = ['#7ec850', '#f14c4c', '#4dabf7']
        for color in colors:
            icon = manager.get('file', 24, color)
            print(f"  {color}: {icon.availableSizes()}")
        print()

        # 测试组合图标
        print("=== 测试组合图标 ===")
        combined = manager.combine('folder', 'star', 32)
        print(f"  组合图标: {combined.availableSizes()}")
        print()

        # 测试生成的图标
        print("=== 测试生成的图标 ===")
        circle = manager.colored_circle('#7ec850', 16)
        square = manager.colored_square('#f14c4c', 16)
        print(f"  圆点: {circle.availableSizes()}")
        print(f"  方块: {square.availableSizes()}")
        print()

        # 列出所有可用图标
        print("=== 所有可用图标 ===")
        all_icons = manager.list_icons()
        print(f"  总数: {len(all_icons)}")

        by_provider = manager.list_icons_by_provider()
        for provider, icons in by_provider.items():
            print(f"  {provider}: {len(icons)} 个")

        print()
        print(f"  前 20 个图标: {all_icons[:20]}")
        print()

        # 测试单例
        print("=== 测试单例 ===")
        manager2 = get_icon_manager()
        print(f"  同一实例: {manager is manager2}")
        print()

        print("测试完成。")

    finally:
        # 清理
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    sys.exit(0)