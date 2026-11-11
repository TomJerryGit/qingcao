# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""图标提供者（v2.25 从 icon_manager 拆出）。"""

from infrastructure.icon_manager_common import *  # noqa: F401,F403


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
    def get_icon(
        self, name: str, size: int = DEFAULT_ICON_SIZE, color: Optional[str] = None
    ) -> Optional[QIcon]:
        """获取图标"""
        pass

    def get_pixmap(
        self, name: str, size: int = DEFAULT_ICON_SIZE, color: Optional[str] = None
    ) -> Optional[QPixmap]:
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
            if not filename.endswith(".svg"):
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

    def get_icon(
        self, name: str, size: int = DEFAULT_ICON_SIZE, color: Optional[str] = None
    ) -> Optional[QIcon]:
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

    def _render_colored_svg(self, filepath: str, size: int, color: str) -> Optional[QPixmap]:
        """渲染带颜色的 SVG"""
        try:
            # 读取 SVG 内容
            if filepath not in self._svg_data:
                with open(filepath, "rb") as f:
                    self._svg_data[filepath] = f.read()

            content = self._svg_data[filepath].decode("utf-8")

            # 简单替换 currentColor 和 fill
            content = content.replace("currentColor", color)
            content = content.replace('fill="#000"', f'fill="{color}"')
            content = content.replace('fill="#000000"', f'fill="{color}"')
            content = content.replace('stroke="#000"', f'stroke="{color}"')
            content = content.replace('stroke="#000000"', f'stroke="{color}"')

            # 使用 QPixmap 加载 SVG（Qt 6.x 内建 SVG 支持）
            pixmap = QPixmap()
            if pixmap.loadFromData(content.encode("utf-8"), "SVG"):
                if pixmap.width() != size:
                    pixmap = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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

            if ext == ".svg":
                continue  # SVG 由 SVGIconProvider 处理

            if ext not in ICON_EXTENSIONS:
                continue

            name = os.path.splitext(filename)[0]
            candidates.setdefault(name, []).append(filename)

        # 选择优先级最高的
        for name, files in candidates.items():
            files.sort(key=lambda f: EXTENSION_PRIORITY.get(os.path.splitext(f)[1].lower(), 999))
            self._icons[name] = os.path.join(self.icon_dir, files[0])

    def reload(self):
        """重新扫描"""
        self._icons.clear()
        self._scan()

    def can_provide(self, name: str) -> bool:
        return name in self._icons

    def get_icon(
        self, name: str, size: int = DEFAULT_ICON_SIZE, color: Optional[str] = None
    ) -> Optional[QIcon]:
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
        "file": QStyle.SP_FileIcon,
        "file_new": QStyle.SP_FileIcon,
        "file_open": QStyle.SP_DialogOpenButton,
        "file_save": QStyle.SP_DialogSaveButton,
        "folder": QStyle.SP_DirIcon,
        "folder_open": QStyle.SP_DirOpenIcon,
        "folder_closed": QStyle.SP_DirClosedIcon,
        "file_dialog": QStyle.SP_FileDialogDetailedView,
        "file_dialog_info": QStyle.SP_FileDialogInfoView,
        "file_dialog_contents": QStyle.SP_FileDialogContentsView,
        "file_dialog_list": QStyle.SP_FileDialogListView,
        "file_dialog_new": QStyle.SP_FileDialogNewFolder,
        "file_dialog_start": QStyle.SP_FileDialogStart,
        "file_dialog_end": QStyle.SP_FileDialogEnd,
        "disk_drive": QStyle.SP_DriveHDIcon,
        "disk_fd": QStyle.SP_DriveFDIcon,
        "disk_cd": QStyle.SP_DriveCDIcon,
        "disk_dvd": QStyle.SP_DriveDVDIcon,
        "disk_net": QStyle.SP_DriveNetIcon,
        # 编辑操作
        "undo": QStyle.SP_ArrowBack,
        "redo": QStyle.SP_ArrowForward,
        "arrow_up": QStyle.SP_ArrowUp,
        "arrow_down": QStyle.SP_ArrowDown,
        "arrow_left": QStyle.SP_ArrowLeft,
        "arrow_right": QStyle.SP_ArrowRight,
        "up": QStyle.SP_ArrowUp,
        "down": QStyle.SP_ArrowDown,
        # 对话框
        "dialog_ok": QStyle.SP_DialogOkButton,
        "dialog_cancel": QStyle.SP_DialogCancelButton,
        "dialog_help": QStyle.SP_DialogHelpButton,
        "dialog_open": QStyle.SP_DialogOpenButton,
        "dialog_save": QStyle.SP_DialogSaveButton,
        "dialog_close": QStyle.SP_DialogCloseButton,
        "dialog_apply": QStyle.SP_DialogApplyButton,
        "dialog_reset": QStyle.SP_DialogResetButton,
        "dialog_discard": QStyle.SP_DialogDiscardButton,
        "dialog_yes": QStyle.SP_DialogYesButton,
        "dialog_no": QStyle.SP_DialogNoButton,
        # 消息
        "message_info": QStyle.SP_MessageBoxInformation,
        "message_warning": QStyle.SP_MessageBoxWarning,
        "message_critical": QStyle.SP_MessageBoxCritical,
        "message_question": QStyle.SP_MessageBoxQuestion,
        "info": QStyle.SP_MessageBoxInformation,
        "warning": QStyle.SP_MessageBoxWarning,
        "error": QStyle.SP_MessageBoxCritical,
        "question": QStyle.SP_MessageBoxQuestion,
        # 媒体
        "media_play": QStyle.SP_MediaPlay,
        "media_stop": QStyle.SP_MediaStop,
        "media_pause": QStyle.SP_MediaPause,
        "media_skip_forward": QStyle.SP_MediaSkipForward,
        "media_skip_backward": QStyle.SP_MediaSkipBackward,
        "media_seek_forward": QStyle.SP_MediaSeekForward,
        "media_seek_backward": QStyle.SP_MediaSeekBackward,
        "media_volume": QStyle.SP_MediaVolume,
        "media_volume_muted": QStyle.SP_MediaVolumeMuted,
        # 系统
        "trash": QStyle.SP_TrashIcon,
        "computer": QStyle.SP_ComputerIcon,
        "desktop": QStyle.SP_DesktopIcon,
        "terminal": QStyle.SP_ComputerIcon,
        "browser": QStyle.SP_BrowserReload,
        "refresh": QStyle.SP_BrowserReload,
        "stop": QStyle.SP_BrowserStop,
        "home": QStyle.SP_DirHomeIcon,
        "titlebar_menu": QStyle.SP_TitleBarMenuButton,
        "titlebar_min": QStyle.SP_TitleBarMinButton,
        "titlebar_max": QStyle.SP_TitleBarMaxButton,
        "titlebar_close": QStyle.SP_TitleBarCloseButton,
        "titlebar_normal": QStyle.SP_TitleBarNormalButton,
        "titlebar_shade": QStyle.SP_TitleBarShadeButton,
        "titlebar_unshade": QStyle.SP_TitleBarUnshadeButton,
        "titlebar_context": QStyle.SP_TitleBarContextHelpButton,
        # 其他
        "command_link": QStyle.SP_CommandLink,
        "link": QStyle.SP_CommandLink,
        "line_edit_clear": QStyle.SP_LineEditClearButton,
        "toolbar_extension": QStyle.SP_ToolBarHorizontalExtensionButton,
        "toolbar_vertical": QStyle.SP_ToolBarVerticalExtensionButton,
    }

    def __init__(self):
        super().__init__()
        self.priority = 50  # 中等优先级

    def can_provide(self, name: str) -> bool:
        return name in self.STANDARD_ICONS

    def get_icon(
        self, name: str, size: int = DEFAULT_ICON_SIZE, color: Optional[str] = None
    ) -> Optional[QIcon]:
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
        "file": "📄",
        "file_text": "📄",
        "file_code": "📝",
        "file_python": "🐍",
        "file_js": "📜",
        "file_ts": "📘",
        "file_json": "📊",
        "file_xml": "📋",
        "file_html": "🌐",
        "file_css": "🎨",
        "file_md": "📝",
        "file_log": "📃",
        "file_csv": "📈",
        "file_image": "🖼",
        "file_audio": "🎵",
        "file_video": "🎬",
        "file_zip": "📦",
        "file_pdf": "📕",
        "file_new": "📄",
        "folder": "📁",
        "folder_open": "📂",
        # 编辑
        "new": "➕",
        "open": "📂",
        "save": "💾",
        "save_as": "💾",
        "save_all": "💾",
        "close": "✖",
        "exit": "🚪",
        "undo": "↩",
        "redo": "↪",
        "cut": "✂",
        "copy": "📋",
        "paste": "📋",
        "delete": "🗑",
        "trash": "🗑",
        "select_all": "⬜",
        "find": "🔍",
        "replace": "🔁",
        "search": "🔎",
        "goto": "📍",
        "refresh": "🔄",
        "reload": "🔄",
        # 视图
        "view": "👁",
        "zoom_in": "🔍",
        "zoom_out": "🔍",
        "fullscreen": "⛶",
        "minimize": "➖",
        "maximize": "➕",
        "restore": "🗗",
        # 工具
        "settings": "⚙",
        "tools": "🔧",
        "wrench": "🔧",
        "hammer": "🔨",
        "palette": "🎨",
        "theme": "🎨",
        "plugin": "🧩",
        "extensions": "🧩",
        "terminal": "💻",
        "console": "💻",
        "debug": "🐞",
        "bug": "🐞",
        "run": "▶",
        "play": "▶",
        "stop": "⏹",
        "pause": "⏸",
        "record": "⏺",
        "macro": "⏺",
        # 状态
        "info": "ℹ",
        "warning": "⚠",
        "error": "✕",
        "success": "✓",
        "question": "❓",
        "help": "❓",
        "star": "⭐",
        "heart": "❤",
        "bookmark": "🔖",
        "flag": "🚩",
        # 导航
        "up": "↑",
        "down": "↓",
        "left": "←",
        "right": "→",
        "arrow_up": "⬆",
        "arrow_down": "⬇",
        "arrow_left": "⬅",
        "arrow_right": "➡",
        "expand": "⊞",
        "collapse": "⊟",
        "next": "▶",
        "prev": "◀",
        "first": "⏮",
        "last": "⏭",
        # 文件管理
        "new_file": "📄",
        "new_folder": "📁",
        "rename": "✏",
        "edit": "✏",
        "properties": "ℹ",
        # 界面
        "menu": "☰",
        "hamburger": "☰",
        "grid": "⊞",
        "list": "☰",
        "tree": "🌳",
        "panel": "▦",
        "sidebar": "▤",
        "layout": "▦",
        "window": "🗔",
        # 语言
        "python": "🐍",
        "javascript": "📜",
        "typescript": "📘",
        "rust": "🦀",
        "go": "🐹",
        "java": "☕",
        "cpp": "⚙",
        "ruby": "💎",
        "php": "🐘",
        "swift": "🦅",
        # 其他
        "sun": "☀",
        "moon": "🌙",
        "cloud": "☁",
        "lock": "🔒",
        "unlock": "🔓",
        "eye": "👁",
        "eye_off": "👁‍🗨",
        "user": "👤",
        "users": "👥",
        "clock": "🕐",
        "calendar": "📅",
        "mail": "📧",
        "link": "🔗",
        "external_link": "🔗",
        "download": "⬇",
        "upload": "⬆",
        "share": "📤",
        "import": "📥",
        "export": "📤",
        "print": "🖨",
        "camera": "📷",
        "image": "🖼",
        "video": "🎬",
        "audio": "🎵",
        "music": "🎵",
        "lightning": "⚡",
        "fire": "🔥",
        "seedling": "🌱",  # 青草
        "leaf": "🍃",
        "tree": "🌳",
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
            "Segoe UI Emoji",  # Windows
            "Apple Color Emoji",  # macOS
            "Noto Color Emoji",  # Linux
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

    def get_icon(
        self, name: str, size: int = DEFAULT_ICON_SIZE, color: Optional[str] = None
    ) -> Optional[QIcon]:
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

    def _render_emoji(
        self, emoji: str, size: int, color: Optional[str] = None
    ) -> Optional[QPixmap]:
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
            painter.drawText(rect, Qt.AlignCenter, emoji)

            painter.end()

            # 缩放回目标尺寸
            if render_size != size:
                pixmap = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

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

    def get_icon(
        self, name: str, size: int = DEFAULT_ICON_SIZE, color: Optional[str] = None
    ) -> Optional[QIcon]:
        """生成默认图标"""
        try:
            pixmap = self._draw_default_icon(name, size, color)
            if pixmap:
                return QIcon(pixmap)
        except Exception as e:
            print(f"[BuiltinIconProvider] 绘制失败 ({name}): {e}")

        return None

    def _draw_default_icon(
        self, name: str, size: int, color: Optional[str] = None
    ) -> Optional[QPixmap]:
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
            painter.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, text)

            painter.end()

            return pixmap

        except Exception as e:
            print(f"[BuiltinIconProvider] 绘制异常: {e}")
            return None


# ============================================================
# 图标管理器
# ============================================================
