#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为主窗口模块，包含：
- MainWindow：主窗口（QMainWindow）
- 菜单栏、工具栏、状态栏
- 标签管理、编辑器切换
- 可停靠面板（大纲、目录树、全局搜索、控制台、插件、性能监控等）
- 无干扰模式
- 会话恢复
- 插件加载（修复：使用 api_factory 工厂函数）
- 状态栏信息（行列、编码、LSP、Git 分支、内存）
- 快捷键绑定

注意：
- 统一使用 PyQt5（QAction / QShortcut 均位于 QtWidgets）
- 使用 pyqtSignal 而非 Signal
- proxy 上的文件访问通过 proxy.document.filepath / proxy.document.encoding

修复记录:
- _load_plugins: 使用 api_factory 函数正确创建 PluginAPI 实例
- _build_docks: 新增 PluginsPanel / OutlinePanelEnhanced 注册
- _show_shortcuts: 确保 QPushButton / QTextBrowser 已导入
- closeEvent: 增加显式 QApplication.quit() 调用（双保险，配合
  main.py 中的 setQuitOnLastWindowClosed(True) 一起确保应用能正常退出）
- _create_main_api: 新增方法，为主窗口创建独立的全权限 API（P2-1）
- _load_plugins: self.api 由 _create_main_api 创建，不再取第一个插件的 API（P2-1）
- _autosave_session: 无打开文件时跳过，避免无谓 IO（P2-3）
- "符号跳转"快捷键改为 Ctrl+Alt+R，解决与"重新加载"Ctrl+R 的冲突（P2-4）
- _on_tab_changed: 同步 column_mode_action 状态（P2-5）
- _show_daily_tip: 每天只显示一次（P2-8）
- _show_line_palette: 重命名为 _goto_line_dialog（P3-2），
  保留旧名作为别名，向后兼容
"""

import hashlib
import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QDateTime, QSettings, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QFont, QIcon, QKeySequence

# ============================================================
# PyQt5 导入（全部统一）
# ============================================================
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QShortcut,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTextBrowser,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


# ============================================================
# 常量
# ============================================================
logger = logging.getLogger(__name__)

APP_NAME = "青草编辑器"
# P1-1: 版本号唯一来源 version.py
try:
    from version import __version__ as APP_VERSION
except ImportError:  # pragma: no cover
    APP_VERSION = "0.0.0"
ORG_NAME = "QingCao"

# 状态栏刷新间隔（毫秒）
STATUS_REFRESH_INTERVAL = 3000

# 会话自动保存间隔（毫秒）
SESSION_AUTOSAVE_INTERVAL = 120000

# 内存警告阈值（MB）
MEMORY_WARN_THRESHOLD = 800

# ============================================================
# 菜单项文本 → ActionManager 动作名
# ============================================================
# ★ 为什么需要这张表（本轮实测发现的重要缺陷）：
#   `MainWindow._add_action()` 原先**从不把动作注册进 `ActionManager`**
#   （全仓 `act_mgr.register(` 调用数为 0，插件除外）。于是
#   `ActionManager.actions` 是空的：
#     * 「⌨ 快捷键编辑器」列出**空表**；
#     * `core/keymap_profiles.py` 里 VSCode/Sublime/Vim 方案的 overrides
#       全部指向不存在的名字 → `set_shortcut()` 返回 False 被静默忽略
#       → **方案套用后毫无效果**；
#     * `reset_to_defaults()` 因 `defaults` 为空，会把快捷键**清空**。
#
#   本表里的名字是 `core/keymap_profiles.py` 的 overrides **直接引用**的，
#   必须逐字一致。改这里的 key（左侧菜单文本）时，请同步确认方案文件与
#   `tools/verify_keymap_profiles.py` 仍然通过。
#
#   不在表里的带快捷键项由 `_canonical_action_name()` 自动生成
#   `misc.<hash>` 名字 —— 目的是让快捷键编辑器列出**真实全量**动作，
#   而不是只有这十几个。
ACTION_NAME_BY_TEXT = {
    # ---- 文件 ----
    "📄 新建(&N)": "file.new",
    "📂 打开(&O)": "file.open",
    "💾 保存(&S)": "file.save",
    "💾 另存为(&A)": "file.save_as",
    # ---- 编辑 ----
    "↩ 撤销(&U)": "edit.undo",
    "↪ 重做(&R)": "edit.redo",
    "🔍 查找(&F)": "edit.find",
    "📍 跳转到行": "edit.goto_line",
    "💬 注释切换": "edit.toggle_comment",
    "📋 复制整行": "edit.duplicate_line",
    "⬆ 上移行": "edit.move_line_up",
    "⬇ 下移行": "edit.move_line_down",
    "🔷 选中下一个相同项": "edit.select_next",
    # ---- 视图 ----
    "列模式": "view.column_mode",
    # ---- 工具 ----
    "⌨ 命令面板": "tools.command_palette",
    "📂 文件切换": "tools.quick_open",
    "⚙ 首选项...": "tools.preferences",
    "🧩 插件市场": "tools.plugin_store",
    "🔌 插件管理": "tools.plugin_manage",
}

# 主 API 的全部权限（P2-1）
_MAIN_API_FALLBACK_PERMISSIONS = [
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
]


# ============================================================
# 主窗口
# ============================================================
from ui.mixins.capability_wiring_mixin import CapabilityWiringMixin
from ui.mixins.edit_ops_mixin import EditOpsMixin
from ui.mixins.file_ops_mixin import FileOpsMixin
from ui.mixins.menu_builder_mixin import MenuBuilderMixin
from ui.mixins.panel_registry_mixin import PanelRegistryMixin
from ui.mixins.plugins_ui_mixin import PluginsUIMixin
from ui.mixins.project_mixin import ProjectMixin
from ui.mixins.sandbox_ui_mixin import SandboxUIMixin
from ui.mixins.status_bar_mixin import StatusBarMixin


try:
    from PyQt5.QtCore import QEvent, QObject
    from PyQt5.QtWidgets import QWidget
except Exception:  # pragma: no cover - PyQt5 缺失时模块本就不可用
    QEvent = None
    QObject = object
    QWidget = object


class _TopLevelThemeFilter(QObject):
    """应用级事件过滤器：新创建的独立顶层窗口显示时套用当前主题 QSS"""

    def __init__(self, win):
        super().__init__(win)
        self._win = win

    def eventFilter(self, obj, event):
        try:
            try:
                import sip

                if sip.isdeleted(self._win) or sip.isdeleted(obj):
                    return False
            except Exception:
                pass
            if obj is self._win or not isinstance(obj, QWidget):
                return False
            if event.type() != QEvent.Show or not obj.isWindow():
                return False
            qss = getattr(self._win, "_current_theme_qss", "")
            if qss and not obj.styleSheet():
                obj.setStyleSheet(qss)
                theme = getattr(self._win, "_startup_theme", None)
                if theme is not None:
                    adapt_widget_styles(obj, theme)
        except Exception:
            pass
        return False


def adapt_widget_styles(root, theme):
    """递归把控件树内联 QSS 中硬编码的深色适配为当前主题配色

    为什么需要：部分面板只在内部子控件（QTreeWidget/QTextEdit 等）上
    设置了硬编码深色 QSS；dock 自身 refresh_theme 只能改 dock 级样式，
    浅色主题下会留下"黑块"（真实桌面截图确认）。

    保存首次原始 QSS，后续调用从原始值重新适配，避免多次叠加失真。
    """
    if root is None or theme is None:
        return 0
    try:
        from infrastructure.theme_loader import adapt_qss_colors
    except Exception:
        return 0
    # A 阶段优化：
    # 1) 只做一次 findChildren（原实现先按 type(root) 再按 QWidget 扫两遍）；
    # 2) 根控件缓存主题 key：同一主题重复套用（如惰性面板反复 ensure）
    #    直接短路，避免全树重复适配。
    try:
        theme_key = getattr(theme, "name", None) or hash(repr(theme))
    except Exception:
        theme_key = id(theme)
    if getattr(root, "_qc_theme_key", None) == theme_key:
        return 0
    root._qc_theme_key = theme_key
    try:
        from PyQt5.QtWidgets import QWidget

        targets = [root] + list(root.findChildren(QWidget))
    except Exception:
        targets = [root]
    count = 0
    for w in targets:
        try:
            # 自管理主题的控件（插件面板等）由 refresh_theme 处理，避免被覆盖
            if callable(getattr(w, "refresh_theme", None)):
                continue
            if getattr(w, "_qc_adapted_key", None) == theme_key:
                continue
            qss = w.styleSheet()
            if not qss:
                continue
            orig = getattr(w, "_qc_orig_qss", None)
            if orig is None:
                w._qc_orig_qss = qss
                orig = qss
            new = adapt_qss_colors(orig, theme)
            if new and new != qss:
                w.setStyleSheet(new)
                count += 1
            w._qc_adapted_key = theme_key
        except Exception:
            continue
    return count


class MainWindow(
    MenuBuilderMixin,
    PanelRegistryMixin,
    SandboxUIMixin,
    PluginsUIMixin,
    CapabilityWiringMixin,
    ProjectMixin,
    FileOpsMixin,
    EditOpsMixin,
    StatusBarMixin,
    QMainWindow,
):
    # 实时沙箱诊断的大文件阈值（超过则跳过，避免卡顿）
    MAX_LIVE_DIAGNOSTICS_BYTES = 5 * 1024 * 1024

    """
    青草编辑器主窗口。

    整合所有 UI 组件，协调应用层、核心层、UI 层。
    """

    # 自定义信号
    session_restored = pyqtSignal(int)

    def __init__(self, parent=None, startup_files: Optional[List[str]] = None):
        """
        参数:
            parent: 父窗口
            startup_files: 启动时打开的文件列表
        """
        super().__init__(parent)

        # 基础配置
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1100, 750)
        self.setMinimumSize(600, 400)

        # 启动文件
        self.startup_files = startup_files or []

        # 状态
        self._distraction_free = False
        self._fullscreen_mode = False
        self._hidden_widgets: List[QWidget] = []
        self._lsp_clients: Dict[str, Any] = {}
        self._current_project = None
        self.plugins: List[Any] = []
        self.api = None
        self.plugin_loader = None
        self.plugin_manager = None

        # P8-5: 快捷键 → QAction 的运行时登记表。
        # _add_action() 直接调用 QAction.setShortcut()，绕过了
        # app/actions.py 的冲突检测；这里补一道"重复绑定"防线。
        self._shortcut_owners: Dict[str, QAction] = {}

        # 关闭标志（避免 closeEvent 重入）
        self._closing = False

        # 偏好设置
        try:
            from app.preferences import Preferences

            self.prefs = Preferences()
        except Exception as e:
            print(f"[MainWindow] Preferences 加载失败: {e}")
            self.prefs = None

        # 动作管理器
        try:
            from app.actions import ActionManager

            self.act_mgr = ActionManager()
        except Exception as e:
            print(f"[MainWindow] ActionManager 加载失败: {e}")
            self.act_mgr = None

        # 宏录制
        try:
            from core.macro import MacroManager, MacroRecorder

            # P0-1 修复（实测：录制后命令数为 0）：
            #   原实现是 `MacroRecorder()` —— 没有 undo_manager。
            #   `core/macro.py` 的 `_register_hook()` 在
            #   `not self.undo_manager` 时直接 return，`record_hook`
            #   永不设置，于是录制器什么都收不到，录到 0 条。
            #
            #   这里不能简单地在构造时传一个固定引用：proxy 与其
            #   `UndoManager` 是**每个标签一个**（见 core/editor.py），
            #   而此刻 `self.tabs` 还没创建（`_build_central` 在后面）。
            #   因此传入"解析当前标签 undo_manager"的回调，
            #   由 MacroRecorder 在 start()/stop() 时动态绑定。
            self.macro = MacroRecorder(
                undo_manager_provider=self._current_undo_manager,
                parent=self,
            )
            # P0-1: 录制/回放的失败必须可见（原先只会 print 到控制台，
            # 打包成 GUI 程序后用户完全看不到）
            try:
                self.macro.error_occurred.connect(self._on_macro_error)
            except Exception:
                pass
            self.macro_manager = MacroManager()
        except Exception as e:
            print(f"[MainWindow] Macro 加载失败: {e}")
            self.macro = None
            self.macro_manager = None

        # 文档模型
        try:
            from core.document import DocumentModel

            self.doc_model = DocumentModel()
        except Exception as e:
            print(f"[MainWindow] DocumentModel 加载失败: {e}")
            self.doc_model = None

        # 会话管理
        try:
            from app.session import SessionManager

            self.session = SessionManager()
            self.session.bind_window(self)
        except Exception as e:
            print(f"[MainWindow] SessionManager 加载失败: {e}")
            self.session = None

        # 构建 UI
        self._build_central()

        # 项目状态（工作区/项目根）必须在 _build_menus 之前就绪：
        # `_setup_project_menu()` 会读 workspace 构建「最近项目」子菜单。
        self._init_project_state()

        self._build_menus()
        self._build_toolbar()
        self._build_docks()
        self._build_status_bar()
        self._build_npp_style_menus()
        self.setAcceptDrops(True)
        self._sandboxed_plugins = {}
        self._build_shortcuts()

        # 连接事件总线
        self._connect_event_bus()

        # 加载插件（延迟）
        QTimer.singleShot(100, self._load_plugins)

        # 恢复会话（延迟）
        QTimer.singleShot(200, self._restore_session)

        # 打开启动文件（延迟）
        if self.startup_files:
            QTimer.singleShot(300, self._open_startup_files)

        # 状态栏定时刷新
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(STATUS_REFRESH_INTERVAL)

        # 会话自动保存
        self._session_timer = QTimer(self)
        self._session_timer.timeout.connect(self._autosave_session)
        self._session_timer.start(SESSION_AUTOSAVE_INTERVAL)

        # 自动备份定时器（P1 修复：崩溃恢复的**生产者**）
        #
        # 缺陷背景（真实缺陷，已核实）：
        #   `SessionManager.start_autosave()` / `save_autosave()`
        #   —— 唯一会备份"未保存文件正文"的代码 —— **全仓零调用点**。
        #   于是 `backup/autosave/meta.json` 永不生成，
        #   main.py 的崩溃恢复分支（判 meta.json 是否存在）永不进入，
        #   草稿又没有任何读取端 → **崩溃后未保存内容 100% 丢失**。
        #
        #   注意：上面那个 `_session_timer` 连的是 `_autosave_session`，
        #   它只调 `session.save(...)`（存文件名/光标/布局），
        #   **不含正文**，因此不能替代本定时器。
        if self.session is not None:
            try:
                self.session.start_autosave()
            except Exception as e:
                logging.warning("启动自动备份定时器失败: %s", e)

    # ========================================================
    # 中央区域
    # ========================================================
    def _build_central(self):
        """构建中央区域"""
        # 用 QStackedWidget 实现欢迎页与编辑区的切换
        self.central_stack = QStackedWidget()

        # 标签管理器
        try:
            from app.tabs import TabManager

            self.tabs = TabManager()
        except Exception as e:
            print(f"[MainWindow] TabManager 加载失败: {e}")
            self.tabs = self._create_fallback_tabs()

        self.central_stack.addWidget(self.tabs)

        # 欢迎页
        try:
            from ui.welcome_widget import WelcomeWidget

            self.welcome = WelcomeWidget(self)

            # 兼容不同的信号名
            if hasattr(self.welcome, "new_file_requested"):
                self.welcome.new_file_requested.connect(self._new_file)
            elif hasattr(self.welcome, "new_file"):
                self.welcome.new_file.connect(self._new_file)

            if hasattr(self.welcome, "open_file_requested"):
                self.welcome.open_file_requested.connect(self._open_file)
            elif hasattr(self.welcome, "open_file"):
                self.welcome.open_file.connect(self._open_file)

            if hasattr(self.welcome, "open_folder_requested"):
                self.welcome.open_folder_requested.connect(self._open_folder)

            if hasattr(self.welcome, "open_recent_file"):
                self.welcome.open_recent_file.connect(self._open_recent_file)

            if hasattr(self.welcome, "open_recent_project"):
                self.welcome.open_recent_project.connect(self._open_recent_project)

            if hasattr(self.welcome, "open_plugin_store"):
                self.welcome.open_plugin_store.connect(self._show_plugin_store)

            if hasattr(self.welcome, "open_command_palette"):
                self.welcome.open_command_palette.connect(self._show_command_palette)

            self.central_stack.addWidget(self.welcome)
        except Exception as e:
            print(f"[MainWindow] WelcomeWidget 加载失败: {e}")
            self.welcome = None

        # 默认显示欢迎页（视图 → 显示欢迎页 可关闭；NPP 默认无欢迎页）
        show_welcome = True
        try:
            show_welcome = bool(self.prefs.get("show_welcome_page", True))
        except Exception:
            pass
        self._welcome_visible_pref = show_welcome
        if self.tabs.count() == 0 and show_welcome:
            self.central_stack.setCurrentIndex(1)
        else:
            self.central_stack.setCurrentIndex(0)

        self.setCentralWidget(self.central_stack)

        # 标签切换信号
        try:
            self.tabs.currentChanged.connect(self._on_tab_changed)
        except Exception:
            pass

        try:
            self.tabs.all_tabs_closed.connect(self._on_all_tabs_closed)
        except Exception:
            pass

        # 外部文件变更 → 在正常事件层级询问用户是否重新加载
        #
        # 为什么不在这里之外的地方弹框：信号由 `QFileSystemWatcher` 回调
        # 发出，在回调里直接弹模态对话框会重入事件循环，并在窗口销毁阶段
        # 崩溃（实测段错误 0xC0000005）。见 `TabManager._handle_file_change`。
        try:
            self.tabs.file_changed_externally.connect(self._on_file_changed_externally)
        except Exception:
            pass

    def _on_file_changed_externally(self, filepath: str):
        """外部文件变更：询问用户是否重新加载"""
        if getattr(self, "_closing", False):
            return
        try:
            editor = None
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                proxy = getattr(w, "proxy", None)
                doc = getattr(proxy, "document", None) if proxy else None
                fp = getattr(doc, "filepath", None) if doc else None
                if fp and os.path.normcase(os.path.abspath(fp)) == os.path.normcase(
                    os.path.abspath(filepath)
                ):
                    editor = w
                    break
            if editor is None:
                return

            ret = QMessageBox.question(
                self,
                "文件已修改",
                f"文件已被外部程序修改：\n{os.path.basename(filepath)}\n\n是否重新加载？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if ret == QMessageBox.Yes:
                self.tabs._reload_file(filepath, editor)
        except Exception as e:
            logger.debug("处理外部文件变更失败: %s", e)

    def _create_fallback_tabs(self):
        """创建后备标签管理器（当 TabManager 加载失败时使用）"""
        from PyQt5.QtWidgets import QTabWidget

        tabs = QTabWidget()
        tabs.setTabsClosable(True)
        tabs.setMovable(True)
        tabs._editors = []

        def add_tab(title="未命名"):
            try:
                from ui.editor_view import EditorWidget

                editor = EditorWidget()
                idx = tabs.addTab(editor, title)
                tabs.setCurrentIndex(idx)
                tabs._editors.append(editor)
                return editor.proxy
            except Exception as e:
                import traceback

                traceback.print_exc()
                print(f"[fallback] add_tab 失败: {e}")
                return None

        def close_tab(index):
            w = tabs.widget(index)
            tabs.removeTab(index)
            if w in tabs._editors:
                tabs._editors.remove(w)

        def current_proxy():
            w = tabs.currentWidget()
            return w.proxy if w and hasattr(w, "proxy") else None

        def open_file(path):
            try:
                from core.content_provider import LocalFileProvider
                from ui.editor_view import EditorWidget

                provider = LocalFileProvider()
                provider.open(path)

                editor = EditorWidget(provider=provider)
                idx = tabs.addTab(editor, os.path.basename(path))
                tabs.setCurrentIndex(idx)
                tabs._editors.append(editor)

                editor.proxy.open_file(path)
                return editor.proxy
            except Exception as e:
                import traceback

                traceback.print_exc()
                print(f"[fallback] open_file 失败: {e}")
                return None

        def count():
            return tabs.count()

        def currentIndex():
            return tabs.currentIndex()

        tabs.tabCloseRequested.connect(close_tab)
        tabs.add_tab = add_tab
        tabs.open_file = open_file
        tabs.current_proxy = current_proxy
        tabs.count = count
        tabs.currentIndex = currentIndex

        return tabs

    def _apply_theme_by_name(self, name: str):
        # 函数内后文有局部 `from PyQt5.QtWidgets import QApplication`，
        # Python 会把 QApplication 当整个函数的局部变量；若在 import
        # 之前使用（如"跟随系统"分支）会抛 UnboundLocalError。
        from PyQt5.QtWidgets import QApplication

        """按名称应用主题"""
        try:
            from infrastructure.theme_loader import ThemeLoader

            loader = ThemeLoader()

            if name == "__system__":
                loader.apply_system_theme(QApplication.instance(), self.tabs.currentWidget())
                self.status_bar.showMessage("已切换到跟随系统", 2000)
                return

            theme = loader.load_by_name(name)
            if not theme:
                self._show_error("主题加载失败", f"未找到主题: {name}")
                return

            for i in range(self.tabs.count()):
                loader.apply(self.tabs.widget(i), theme)

            # A(主题): 用 loader.apply_qss 处理无 qss 主题
            # 原实现只在 `if theme.qss:` 时才 setStyleSheet，而
            # themes/*.json 里都没有 qss 字段，导致 QSS 从未应用。
            # apply_qss 会在 qss 为空时从 colors 生成 QSS。
            try:
                from PyQt5.QtWidgets import QApplication

                _app = QApplication.instance()
                if _app is not None:
                    _pm = getattr(self, "plugin_manager", None)
                    if _pm is not None:
                        try:
                            _pm.pause_deferred_activation()
                        except Exception:
                            _pm = None
                    try:
                        # C-2：实测窗口级 QSS 35-49ms，应用级全局
                        # setStyleSheet 90-424ms；改为窗口级应用 +
                        # palette 兜底（子对话框随父控件继承样式）。
                        try:
                            loader.apply_palette(_app, theme)
                            self.setPalette(_app.palette())
                        except Exception:
                            pass
                        self._current_theme_name = name
                        _qss = loader.build_qss(theme)
                        if _qss:
                            try:
                                from ui.accessibility import focus_ring_qss

                                _acc = focus_ring_qss()
                            except Exception:
                                _acc = ""
                            _qss = (_qss or "") + _acc
                            self._current_theme_qss = _qss
                            self.setStyleSheet(_qss)
                            self._apply_theme_to_top_levels(_qss)
                            self._ensure_toplevel_theme_filter()
                    finally:
                        if _pm is not None:
                            try:
                                _pm.resume_deferred_activation()
                            except Exception:
                                pass
                    # 有些 QSS 选择器（QMainWindow 等）需要重设
                    _app.setStyleSheet(_app.styleSheet())
            except Exception as _e:
                print(f"[Theme] apply_qss 失败: {_e}")
                if theme.qss:
                    self.setStyleSheet(theme.qss)

            # v3.0: 先统一适配硬编码 QSS，再通知面板刷新（v2.14.1 顺序修复）
            try:
                adapt_widget_styles(self, theme)
            except Exception:
                pass
            loader.notify_widgets(self, theme)

            # B: 遍历所有顶层窗口（含独立对话框）
            # notify_widgets 只处理 self.findChildren，独立打开的
            # 对话框（AI 配置、Git 提交、快捷键编辑器等）不在其中
            try:
                from PyQt5.QtWidgets import QApplication

                for w in QApplication.topLevelWidgets():
                    if w is self:
                        continue
                    fn = getattr(w, "refresh_theme", None)
                    if callable(fn):
                        try:
                            fn(theme)
                        except Exception:
                            pass
            except Exception:
                pass

            # 持久化
            from PyQt5.QtCore import QSettings

            settings = QSettings("QingCao", "Editor")
            settings.setValue("theme_name", name)

            self.status_bar.showMessage(f"主题已切换: {name}", 2000)
        except Exception as e:
            self._show_error("主题切换失败", str(e))

    def _show_theme_editor(self):
        """打开主题编辑器（含实时预览）"""
        try:
            from ui.theme_editor import ThemeEditor

            dlg = ThemeEditor(self)

            # 保存后立即应用 + 刷新主题菜单
            def on_saved(path):
                try:
                    from infrastructure.theme_loader import ThemeLoader

                    loader = ThemeLoader()
                    theme = loader.load(path)
                    if theme:
                        for i in range(self.tabs.count()):
                            loader.apply(self.tabs.widget(i), theme)
                        if theme.qss:
                            self.setStyleSheet(theme.qss)
                    # 重新构建菜单
                    self.theme_menu.clear()
                    self._build_full_theme_menu()
                except Exception as e:
                    print(f"[ThemeEditor] 保存后应用失败: {e}")

            dlg.theme_saved.connect(on_saved)
            dlg.exec_()
        except Exception as e:
            self._show_error("打开主题编辑器失败", str(e))

    def _show_theme_market(self):
        """打开主题市场"""
        try:
            from ui.theme_market import ThemeMarketDialog

            dlg = ThemeMarketDialog(self, self)

            def on_installed(name):
                # 刷新菜单
                self.theme_menu.clear()
                self._build_full_theme_menu()

            def on_deleted(name):
                self.theme_menu.clear()
                self._build_full_theme_menu()

            dlg.theme_installed.connect(on_installed)
            dlg.theme_deleted.connect(on_deleted)
            dlg.exec_()
        except Exception as e:
            self._show_error("打开主题市场失败", str(e))

    def _import_theme_pack(self):
        """导入主题包（zip）"""
        try:
            from PyQt5.QtWidgets import QFileDialog

            from core.theme_pack import ThemePack

            path, _ = QFileDialog.getOpenFileName(
                self, "导入主题包", "", "主题包 (*.zip);;所有文件 (*.*)"
            )
            if not path:
                return

            themes_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "themes"
            )
            ok, msg = ThemePack.import_theme(path, themes_dir)
            if ok:
                QMessageBox.information(self, "成功", msg)
                # 刷新菜单
                self.theme_menu.clear()
                self._build_full_theme_menu()
            else:
                QMessageBox.warning(self, "导入失败", msg)
        except Exception as e:
            self._show_error("导入失败", str(e))

    def _export_theme_pack(self):
        """导出当前主题为 zip 包"""
        try:
            from PyQt5.QtCore import QSettings
            from PyQt5.QtWidgets import QFileDialog

            from core.theme_pack import ThemePack

            settings = QSettings("QingCao", "Editor")
            theme_name = settings.value("theme_name", "", type=str)
            if not theme_name:
                self._show_info("提示", "当前没有选中主题")
                return

            themes_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "themes"
            )
            source = os.path.join(themes_dir, f"{theme_name}.json")
            if not os.path.exists(source):
                self._show_error("导出失败", f"主题文件不存在: {source}")
                return

            path, _ = QFileDialog.getSaveFileName(
                self, "导出主题包", f"{theme_name}.zip", "主题包 (*.zip)"
            )
            if not path:
                return

            ok, msg = ThemePack.export_theme(source, path)
            if ok:
                QMessageBox.information(self, "成功", msg)
            else:
                QMessageBox.warning(self, "导出失败", msg)
        except Exception as e:
            self._show_error("导出失败", str(e))

    def _open_theme_dir(self):
        """打开主题目录"""
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QDesktopServices

        themes_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "themes"
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(themes_dir))

    def _show_preferences(self):
        """打开首选项面板"""
        try:
            from ui.preferences_panel import PreferencesDialog

            dlg = PreferencesDialog(self, self)
            dlg.exec_()
        except Exception as e:
            self._show_error("打开首选项失败", str(e))

    def _canonical_action_name(self, text: str, shortcut: Optional[str]) -> Optional[str]:
        """给一个菜单项决定它在 `ActionManager` 里的名字

        两级策略：

        1. **映射表优先**：`ACTION_NAME_BY_TEXT` 里的名字是
           `core/keymap_profiles.py` 的方案 overrides 直接引用的
           （如 `file.save` / `edit.find`）—— 必须逐字一致，
           否则 `set_shortcut()` 会静默返回 False，方案失效。
        2. **兜底自动生成**：其余带快捷键的项用一个由文本+快捷键导出的
           稳定 slug（`misc.<hash>`）。这样快捷键编辑器能列出**真实全量**
           动作，而不是只有 15 个；同时 `defaults` 被填上，
           `reset_to_defaults()` 不会把它们的快捷键清空。

        没有快捷键又不在映射表里的项返回 None（不注册）——
        它们进快捷键编辑器没有意义。
        """
        if text in ACTION_NAME_BY_TEXT:
            return ACTION_NAME_BY_TEXT[text]
        if not shortcut:
            return None
        digest = hashlib.md5(("%s|%s" % (text, shortcut)).encode("utf-8")).hexdigest()[:10]
        return "misc.%s" % digest

    # ========================================================
    # 运行 / 转到定义 / LSP（P8-2 / P6）
    # ========================================================
    def _run_current_file(self):
        """运行当前文件（P8-2: F5）。

        优先交给已激活的调试类插件（如 python_debugger）；插件未激活
        时**明确提示**用户，而不是静默什么都不做。
        """
        try:
            proxy = self.tabs.current_proxy()
            if not proxy:
                self.status_bar.showMessage("没有打开的编辑器，无法运行", 4000)
                return

            filepath = ""
            try:
                filepath = (proxy.document.filepath or "") if proxy.document else ""
            except Exception:
                filepath = ""

            if not filepath:
                self.status_bar.showMessage("请先保存文件再运行", 4000)
                return

            # 1) 已激活的调试插件
            for plugin in self.plugins or []:
                runner = getattr(plugin, "run_current", None)
                if callable(runner):
                    try:
                        runner()
                        return
                    except Exception as e:
                        logger.error("插件运行当前文件失败: %s", e)
                        self.status_bar.showMessage(f"运行失败: {e}", 5000)
                        return

            # 2) 没有调试插件：给出可操作的提示（不静默失败）
            self.status_bar.showMessage(
                "未启用调试插件，无法运行当前文件；"
                "请启用「python_debugger」等调试插件（工具 → 插件管理）。"
                f"（{os.path.basename(filepath)}）",
                6000,
            )
            logger.warning("运行当前文件：没有可用的调试插件（filepath=%s）", filepath)
        except Exception as e:
            logger.error("运行当前文件失败: %s", e)
            try:
                self.status_bar.showMessage(f"运行失败: {e}", 5000)
            except Exception:
                pass

    def _goto_definition(self):
        """转到定义（P6: F12）。

        实际请求由 `EditorProxy.goto_definition()` 发出；失败原因
        （未启用 LSP / 语言服务器缺失 等）通过 `lsp_error` 信号经
        `_on_lsp_message` 显示在状态栏。
        """
        try:
            proxy = self.tabs.current_proxy()
            if not proxy or not hasattr(proxy, "goto_definition"):
                self.status_bar.showMessage("没有活动的编辑器", 3000)
                return
            self._connect_lsp_signals(proxy)
            if not proxy.goto_definition():
                self.status_bar.showMessage("转到定义不可用（详见状态栏提示 / 日志）", 5000)
        except Exception as e:
            logger.error("转到定义失败: %s", e)
            try:
                self.status_bar.showMessage(f"转到定义失败: {e}", 5000)
            except Exception:
                pass

    def _lsp_pref_enabled(self) -> bool:
        """读取 LSP 开关偏好（健壮：prefs 不可用时返回 False）"""
        try:
            if self.prefs is None:
                return False
            return bool(self.prefs.get("lsp_enabled", False))
        except Exception:
            return False

    def _set_lsp_checked(self, checked: bool):
        """设置 LSP 菜单勾选状态（阻断信号，避免递归）"""
        try:
            if not hasattr(self, "lsp_action"):
                return
            self.lsp_action.blockSignals(True)
            self.lsp_action.setChecked(checked)
            self.lsp_action.blockSignals(False)
        except Exception:
            pass

    def _connect_lsp_signals(self, proxy):
        """把编辑器代理的 LSP 信号接到状态栏（幂等）。

        P6 要求"失败必须用户可见"：EditorProxy 通过 `lsp_error` 信号
        发出人类可读的原因，主窗口负责显示 + 记日志。
        """
        if getattr(proxy, "_lsp_ui_connected", False):
            return
        connected = False
        for sig_name, slot in (
            ("lsp_error", self._on_lsp_message),
            ("lsp_status_changed", self._on_lsp_status),
            ("definition_requested", self._on_definition_requested),
            # B 阶段：LSP 其余能力的结果展示
            ("hover_text", self._on_lsp_hover_text),
            ("references_ready", self._on_lsp_references),
            ("rename_applied", self._on_lsp_rename_applied),
            ("symbols_ready", self._on_lsp_symbols),
            ("code_actions_ready", self._on_lsp_code_actions),
            ("formatting_applied", self._on_lsp_formatting_applied),
            ("signature_help", self._on_lsp_signature),
        ):
            try:
                sig = getattr(proxy, sig_name, None)
                if sig is not None:
                    sig.connect(slot)
                    connected = True
            except Exception as e:
                logger.debug("连接 %s 失败: %s", sig_name, e)
        if connected:
            try:
                proxy._lsp_ui_connected = True
            except Exception:
                pass

    def _on_lsp_message(self, message: str):
        """LSP 用户可见提示（失败原因 / 安装提示）"""
        try:
            logger.warning("[LSP] %s", message)
        except Exception:
            pass
        try:
            self.status_bar.showMessage(str(message), 8000)
        except Exception:
            pass

    def _on_lsp_status(self, state: str):
        """LSP 状态变化 → 状态栏"""
        try:
            text = {
                "running": "LSP 已启动",
                "off": "LSP 已停止",
                "error": "LSP 错误（详见日志）",
                "unsupported": "当前文件类型无 LSP 支持",
                "no_server": "未配置该语言的 LSP 服务器",
                "not_found": "未找到语言服务器，请先安装",
            }.get(str(state), f"LSP: {state}")
            self.status_bar.showMessage(text, 4000)
        except Exception:
            pass

    # --------------------------------------------------------
    # B 阶段：LSP 其余能力的结果展示（此前结果信号零 connect）
    # --------------------------------------------------------
    def _on_lsp_hover_text(self, text: str):
        """悬停信息 → 弹窗展示（内容可能较长，用信息框而非状态栏）"""
        try:
            self._show_info("悬停信息", text)
        except Exception as e:
            logger.debug("显示悬停信息失败: %s", e)

    def _on_lsp_references(self, items: list):
        """引用列表 → 文本弹窗（点击跳转留待后续）"""
        try:
            lines = []
            for it in items or []:
                path = it.get("path") or ""
                name = os.path.basename(path) if path else "(未知)"
                lines.append(
                    "%s:%d:%d"
                    % (
                        name,
                        int(it.get("line", 0)) + 1,
                        int(it.get("character", 0)) + 1,
                    )
                )
            if not lines:
                self.status_bar.showMessage("未找到引用", 4000)
                return
            self._show_info(
                "引用（%d 处）" % len(lines),
                "\n".join(lines),
            )
        except Exception as e:
            logger.debug("显示引用失败: %s", e)

    def _on_lsp_rename_applied(self, count: int):
        """重命名结果：目前只报告影响范围

        真正跨文件应用 WorkspaceEdit 涉及多文件原子写入，未在本轮范围内；
        这里明确告知用户"会影响多少处"，而不是假装已经改好。
        """
        try:
            self.status_bar.showMessage("重命名将影响 %d 处（跨文件应用尚未实现）" % count, 8000)
        except Exception:
            pass

    def _on_lsp_symbols(self, symbols: list):
        """文档符号 → 列表展示"""
        try:
            lines = []
            for s in symbols or []:
                indent = "  " * int(s.get("depth", 0) or 0)
                lines.append(
                    "%s%s  (行 %d)"
                    % (
                        indent,
                        s.get("name") or "",
                        int(s.get("line", 0)) + 1,
                    )
                )
            if not lines:
                self.status_bar.showMessage("未获取到文档符号", 4000)
                return
            self._show_info("文档符号（%d 项）" % len(lines), "\n".join(lines))
        except Exception as e:
            logger.debug("显示文档符号失败: %s", e)

    def _on_lsp_formatting_applied(self, ok: bool):
        try:
            self.status_bar.showMessage(
                "已应用 LSP 格式化" if ok else "无需格式化或未返回结果",
                4000,
            )
        except Exception:
            pass

    def _on_lsp_signature(self, label: str):
        try:
            self.status_bar.showMessage("签名: %s" % label, 8000)
        except Exception:
            pass

    # --------------------------------------------------------
    # B 阶段：LSP 其余能力的用户入口
    # --------------------------------------------------------
    def _with_proxy(self, method_name: str, what: str):
        """取得当前编辑器代理并调用其 LSP 方法（统一的前置检查）"""
        try:
            proxy = self.tabs.current_proxy()
            if not proxy or not hasattr(proxy, method_name):
                self.status_bar.showMessage("没有活动的编辑器", 3000)
                return None
            self._connect_lsp_signals(proxy)
            return proxy
        except Exception as e:
            logger.error("%s失败: %s", what, e)
            return None

    def _lsp_hover(self):
        proxy = self._with_proxy("hover_at_cursor", "悬停信息")
        if proxy is not None:
            proxy.hover_at_cursor()

    def _lsp_find_references(self):
        proxy = self._with_proxy("find_references", "查找引用")
        if proxy is not None:
            proxy.find_references()

    def _lsp_rename(self):
        proxy = self._with_proxy("rename_symbol", "重命名")
        if proxy is None:
            return
        from PyQt5.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "重命名符号", "新名称:")
        if ok and name:
            proxy.rename_symbol(name)

    def _lsp_document_symbols(self):
        proxy = self._with_proxy("document_symbols", "文档符号")
        if proxy is not None:
            proxy.document_symbols()

    def _lsp_format(self):
        proxy = self._with_proxy("format_document", "格式化")
        if proxy is not None:
            proxy.format_document()

    def _lsp_signature(self):
        proxy = self._with_proxy("request_signature", "签名帮助")
        if proxy is not None:
            proxy.request_signature()

    def _on_definition_requested(self, filepath: str, line: int, character: int):
        """P6: 定义位于**别的文件**时打开它。

        同一文件内的跳转由 `EditorProxy._on_lsp_definition` 直接完成，
        不会走到这里。
        """
        try:
            if not filepath:
                return
            current = ""
            proxy = self.tabs.current_proxy()
            if proxy is not None and getattr(proxy, "document", None) is not None:
                current = proxy.document.filepath or ""

            if os.path.normcase(filepath) == os.path.normcase(current):
                return

            if hasattr(self.tabs, "open_file"):
                self.tabs.open_file(filepath, line=line)
            else:
                self.status_bar.showMessage(f"定义位于: {filepath}:{line + 1}", 6000)
        except Exception as e:
            logger.error("打开定义位置失败: %s", e)

    def _paste_plain(self):
        """粘贴为纯文本（P8-3: Ctrl+Alt+Shift+V）。

        与 `_paste` 的区别：直接插入系统剪贴板的纯文本，不经过
        QScintilla 的富文本/多光标粘贴路径。``insert()`` 在有选区时
        替换选区、无选区时插入。
        """
        try:
            proxy = self.tabs.current_proxy()
            if not proxy or not getattr(proxy, "sc", None):
                self.status_bar.showMessage("没有活动的编辑器", 3000)
                return
            text = QApplication.clipboard().text()
            if not text:
                self.status_bar.showMessage("剪贴板为空", 3000)
                return
            proxy.sc.insert(text)
            self.status_bar.showMessage("已粘贴为纯文本", 2000)
        except Exception as e:
            logger.error("粘贴为纯文本失败: %s", e)
            try:
                self.status_bar.showMessage(f"粘贴失败: {e}", 4000)
            except Exception:
                pass

    def _insert_datetime(self):
        """插入日期时间（P7/P8: 统一走 EditorProxy，格式来自 Preferences）。

        这里**覆盖**了 `EditOpsMixin._insert_datetime`
        （ui/mixins/edit_ops_mixin.py:139）—— 那份实现把格式硬编码为
        ``"%Y-%m-%d %H:%M:%S"``，**完全不读** Preferences 的
        ``date_format`` / ``time_format``，用户在首选项里改了没反应。

        `core/editor.py::insert_datetime` 是唯一读取这两个键的实现，
        编辑器的右键菜单（ui/editor_view.py:1535）已经在用它。此处把
        **编辑菜单** 也统一到同一条路径，避免两份实现再次漂移。
        """
        try:
            proxy = self.tabs.current_proxy()
            if proxy is None:
                self.status_bar.showMessage("没有活动的编辑器", 3000)
                return
            if hasattr(proxy, "insert_datetime"):
                proxy.insert_datetime()
                return
            # 兜底：代理缺该方法时退回 mixin 的历史实现
            super()._insert_datetime()
        except Exception as e:
            logger.error("插入日期时间失败: %s", e)
            try:
                self.status_bar.showMessage(f"插入日期时间失败: {e}", 4000)
            except Exception:
                pass

    def _toggle_lsp(self, checked: bool):
        """P6: 启用/停用当前编辑器的 LSP（工具菜单可勾选项）。

        - 默认关闭：大多数用户本机没有语言服务器。
        - **失败必须用户可见**：具体原因通过 `lsp_error` 信号进入
          状态栏（`_on_lsp_message`），并写入日志。
        - 失败时回滚勾选状态，避免菜单显示"已启用"但实际未生效。
        """
        try:
            proxy = self.tabs.current_proxy()
            if proxy is None or not hasattr(proxy, "toggle_lsp"):
                self.status_bar.showMessage("没有活动的编辑器，无法启用 LSP", 4000)
                self._set_lsp_checked(False)
                return

            self._connect_lsp_signals(proxy)

            if checked:
                ok = bool(proxy.toggle_lsp(True))
                if not ok:
                    # EditorProxy 已经通过 lsp_error 给出具体原因
                    self._set_lsp_checked(False)
                    return
                filepath = ""
                if getattr(proxy, "document", None) is not None:
                    filepath = proxy.document.filepath or ""
                if filepath:
                    self._lsp_clients[filepath] = proxy
            else:
                proxy.toggle_lsp(False)
                stale = [k for k, v in self._lsp_clients.items() if v is proxy]
                for k in stale:
                    self._lsp_clients.pop(k, None)

            if self.prefs is not None:
                try:
                    self.prefs.set("lsp_enabled", bool(checked))
                except Exception:
                    pass
        except Exception as e:
            logger.error("切换 LSP 失败: %s", e)
            self._set_lsp_checked(False)
            try:
                self.status_bar.showMessage(f"切换 LSP 失败: {e}", 5000)
            except Exception:
                pass

    # ========================================================
    # 面板惰性构造（P1-3）
    # ========================================================
    # 修复说明:
    #   原实现在启动时同步构造全部 9 个面板（大纲×2、目录树、
    #   Minimap、全局搜索、Python 控制台、插件面板、性能监控、
    #   搜索栏），其中 6 个构造完立刻 hide()。实测
    #   MainWindow() 构造耗时约 2.46s，是冷启动的最大单项开销。
    #
    #   现在改为按需构造：_build_docks 只登记"面板还没建"，
    #   用户第一次打开某个面板（或外部代码首次访问）时才真正
    #   创建 widget。面板属性仍保持原名字与类型，调用方无需改动。
    _LAZY_PANELS = (
        "outline",
        "outline_enhanced",
        "dir_tree",
        "minimap",
        "gsearch",
        "console",
        "plugins_panel",
        "perf_monitor",
        "search_bar",
        "problems",
        # 本轮接线：两个此前零实例化的孤立面板
        # （`ui/lsp_panel.py` 含语言服务器安装向导；
        #   `ui/undo_history_panel.py` 展示自研撤销栈）
        "lsp",
        "undo_history",
        # 项目任务面板（`ui/task_panel.py` + `core/project_tasks.py`
        # 此前零实例化；由 project_mixin 绑定当前项目根）
        "task",
        # v2.21 P1-1：终端面板
        "terminal",
    )

    # 启动时构造的面板（**保留**延迟构造，但恢复"开箱即有"的界面）
    #
    # 为什么需要（真实回归）：改成纯延迟构造后，启动时一个面板都不存在
    #   → 会话保存采集到空的 docks
    #   → 关闭时覆盖掉用户已有的面板布局
    #   → 之后每次启动界面都是空的（只剩欢迎页）
    # 用户观感就是"功能不见了"。这里在启动时只构造这几个常用面板
    # （仍少于原先的 9 个），既保住冷启动优化，又让界面开箱可用。
    _DEFAULT_PANELS = (
        "dir_tree",  # 左侧：项目目录树
        "gsearch",  # 底部：全局搜索
        "plugins_panel",  # 右侧：插件
        "perf_monitor",  # 底部：性能监控
    )

    def apply_theme_to_widget(self, widget):
        """把一个控件（及其子控件）套用当前主题（若已确定）

        主题是否已知取决于 `apply_startup_theme()` 是否已执行 ——
        惰性面板/插件面板都可能在它之后创建，因此统一走这里。
        """
        theme = getattr(self, "_startup_theme", None)
        if theme is None or widget is None:
            return
        for target in [widget]:
            try:
                children = widget.findChildren(QWidget)
            except Exception:
                children = []
            for w in [target] + list(children):
                fn = getattr(w, "refresh_theme", None)
                if callable(fn):
                    try:
                        fn(theme)
                    except Exception:
                        pass
        # 子控件内联深色 QSS 也要适配（dock 级 refresh_theme 覆盖不到）
        try:
            adapt_widget_styles(widget, theme)
        except Exception:
            pass

    # ========================================================
    # 快捷键
    # ========================================================
    def _build_shortcuts(self):
        """绑定快捷键（QShortcut 在 PyQt5 中位于 QtWidgets）"""
        # 注意：以下快捷键中，与菜单 QAction 重复的已移除，
        #       避免 Qt 报 "Ambiguous shortcut overload"。
        #       QAction 的快捷键在 _build_menus 中定义。
        #
        # 这里只保留菜单里没有的快捷键。
        shortcuts = [
            ("Ctrl+Space", self._auto_complete),
            ("Ctrl+Tab", self._next_tab),
            ("Ctrl+Shift+Tab", self._prev_tab),
        ]

        self._shortcuts = []
        for shortcut, slot in shortcuts:
            try:
                sc = QShortcut(QKeySequence(shortcut), self)
                sc.activated.connect(slot)
                self._shortcuts.append(sc)
            except Exception as e:
                print(f"[MainWindow] 快捷键 {shortcut} 绑定失败: {e}")

    # ========================================================
    # 事件总线
    # ========================================================
    def _connect_event_bus(self):
        """连接事件总线"""
        try:
            from app.event_bus import bus

            bus.status_message.connect(self._on_status_message)
            bus.cursor_moved.connect(self._on_cursor_moved)
            bus.file_opened.connect(self._on_file_opened)
            bus.file_saved.connect(self._on_file_saved)
        except Exception as e:
            print(f"[MainWindow] 事件总线连接失败: {e}")

    def _open_language_packs_dir(self):
        """设置 → 打开语言包目录（data/language_packs）"""
        try:
            import os

            from PyQt5.QtCore import QUrl
            from PyQt5.QtGui import QDesktopServices

            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(root, "data", "language_packs")
            os.makedirs(path, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception as e:
            self.status_bar.showMessage("打开语言包目录失败: %s" % e, 3000)

    def _local_open_paths(self):
        paths = set()
        try:
            for i in range(self.tabs.count()):
                ed = self.tabs.widget(i)
                fp = getattr(getattr(ed, "document", None), "filepath", "") or ""
                if fp:
                    paths.add(fp)
        except Exception:
            pass
        return paths

    def _on_local_tab_opened(self, index):
        """打开文件：同一路径只广播一次（v2.12.0 重复事件抑制）"""
        try:
            ed = self.tabs.widget(index)
            fp = getattr(getattr(ed, "document", None), "filepath", "") or ""
            self._hook_sandbox_live_tab(index)
            if not fp:
                return
            known = set(getattr(self, "_known_open_paths", set()))
            already = fp in known
            known.add(fp)
            self._known_open_paths = known
            if already:
                return
            from infrastructure.instance_broadcast import notify_file_event

            notify_file_event("file_opened", fp)
        except Exception:
            pass

    def _on_local_tab_closed(self, index):
        try:
            from infrastructure.instance_broadcast import notify_file_event

            current = self._local_open_paths()
            known = getattr(self, "_known_open_paths", set())
            for fp in known - current:
                notify_file_event("file_closed", fp)
            self._known_open_paths = current
        except Exception:
            pass

    def _on_remote_file_opened(self, path, mtime, pid):
        """其它实例打开了文件：状态栏提示（不自动打开）"""
        import os

        if pid == os.getpid():
            return
        try:
            self.status_bar.showMessage("其它实例已打开: %s" % os.path.basename(path), 2000)
        except Exception:
            pass

    def _on_remote_file_closed(self, path, mtime, pid):
        import os

        if pid == os.getpid():
            return
        try:
            self.status_bar.showMessage("其它实例已关闭: %s" % os.path.basename(path), 2000)
        except Exception:
            pass

    def _follow_system_high_contrast(self) -> bool:
        try:
            from PyQt5.QtCore import QSettings

            return bool(
                QSettings("QingCao", "Editor").value("follow_system_high_contrast", True, type=bool)
            )
        except Exception:
            return True

    def apply_high_contrast_if_needed(self) -> bool:
        """系统高对比度开启时应用系统调色板 QSS（v2.13.0 P0）"""
        try:
            from infrastructure.theme_loader import build_high_contrast_qss, system_high_contrast

            hc = system_high_contrast()
            self._system_high_contrast = bool(hc)
            if hc and self._follow_system_high_contrast():
                self._suppress_panel_qss()
                qss = build_high_contrast_qss()
                self._current_theme_qss = qss
                self.setStyleSheet(qss)
                self._apply_theme_to_top_levels(qss)
                self.status_bar.showMessage("已启用高对比度适配（跟随系统）", 3000)
                return True
            self._restore_panel_qss()
        except Exception:
            pass
        return False

    def _set_follow_system_high_contrast(self, enabled):
        try:
            from PyQt5.QtCore import QSettings

            s = QSettings("QingCao", "Editor")
            s.setValue("follow_system_high_contrast", bool(enabled))
            s.sync()
        except Exception:
            pass
        if enabled:
            self.apply_high_contrast_if_needed()
        else:
            self._system_high_contrast = False
            self._restore_panel_qss()
            try:
                self._apply_theme_by_name(self._current_theme_name or "")
            except Exception:
                pass
        self.status_bar.showMessage("跟随系统高对比度: %s" % ("开启" if enabled else "关闭"), 2500)

    def _on_remote_config_changed(self, plugin_name):
        """其它实例修改了插件配置：重新读取并下发（配置变更广播）"""
        try:
            from infrastructure.plugin_sandbox_manager import load_plugin_config

            plugins = self._get_sandboxed_plugins() or {}
            sp = plugins.get(plugin_name)
            if sp is None:
                return
            schema = sp.config_schema()
            if not schema:
                return
            values = load_plugin_config(plugin_name, schema)
            ok = bool(sp.config_apply(values))
            self._last_synced_config = (plugin_name, values)
            try:
                self.run_sandboxed_diagnostics()
            except Exception:
                pass
            try:
                self.refresh_sandbox_plugin_menus(quiet=True)
            except Exception:
                pass
            self._refresh_sandbox_status()
            self.status_bar.showMessage(
                "配置已同步（来自其它实例）: %s · %s%s"
                % (plugin_name, "成功" if ok else "失败", " · 已刷新菜单/诊断" if ok else ""),
                5000,
            )
        except Exception:
            pass

    def apply_accessibility_settings(self):
        """应用无障碍设置：字体缩放 + 可访问名称（v2.17）"""
        try:
            from PyQt5.QtCore import QSettings

            from ui.accessibility import apply_accessible_names, apply_font_scale

            factor = QSettings("QingCao", "Editor").value("ui_scale", 1.0, type=float)
            apply_font_scale(self, factor or 1.0)
            apply_accessible_names(self)
        except Exception:
            pass

    def _live_diag_limit(self) -> int:
        """实时沙箱诊断大文件阈值（可配置，v2.17）"""
        try:
            from core.large_file import live_diagnostics_limit_bytes

            return live_diagnostics_limit_bytes()
        except Exception:
            return self.MAX_LIVE_DIAGNOSTICS_BYTES

    def _on_peer_versions_changed(self, versions):
        """多实例协议版本协商结果（v2.15.x）"""
        try:
            from infrastructure.instance_broadcast import PROTOCOL_VERSION

            bad = {
                int(p): int(v) for p, v in (versions or {}).items() if int(v) != PROTOCOL_VERSION
            }
        except Exception:
            return
        if bad and not getattr(self, "_compat_warned", False):
            self._compat_warned = True
            try:
                self.status_bar.showMessage(
                    "检测到不同协议版本的实例（%s），已按兼容模式处理" % bad, 5000
                )
            except Exception:
                pass

    def _on_focus_requested(self):
        """其它实例请求聚焦：还原并激活当前窗口（单实例行为）"""
        try:
            if self.isMinimized():
                self.showNormal()
            self.raise_()
            self.activateWindow()
            self.status_bar.showMessage("已切换到运行中的实例", 2000)
        except Exception:
            pass

    def _start_instance_broadcast(self):
        """多实例：启动保存广播并处理远端保存事件（P0）"""
        try:
            from infrastructure.instance_broadcast import start_broadcast

            self._broadcast = start_broadcast()
            self._broadcast.file_saved.connect(self._on_remote_file_saved)
            self._broadcast.file_opened.connect(self._on_remote_file_opened)
            self._broadcast.file_closed.connect(self._on_remote_file_closed)
            self._broadcast.focus_requested.connect(self._on_focus_requested)
            self._broadcast.config_changed.connect(self._on_remote_config_changed)
            try:
                from PyQt5.QtCore import QTimer as _QTimer

                self._broadcast.peer_versions_changed.connect(self._on_peer_versions_changed)
                _QTimer.singleShot(1500, self._broadcast.announce_hello)
            except Exception:
                pass
            try:
                from PyQt5.QtCore import QTimer

                def _deferred_sandbox_ui():
                    try:
                        self._apply_sandbox_configs()
                    except Exception:
                        pass
                    self.refresh_sandbox_plugin_menus(quiet=True)

                QTimer.singleShot(1500, _deferred_sandbox_ui)
            except Exception:
                pass
            if hasattr(self.tabs, "tab_opened"):
                self._known_open_paths = self._local_open_paths()
                self.tabs.tab_opened.connect(self._on_local_tab_opened)
                self.tabs.tab_closed.connect(self._on_local_tab_closed)
                for _i in range(self.tabs.count()):
                    self._hook_sandbox_live_tab(_i)
        except Exception as e:
            print(f"[MainWindow] 启动多实例广播失败: {e}")

    def _on_remote_file_saved(self, path, mtime, pid):
        """其它实例保存了同一文件：冲突检测 + 自动重载/询问（v2.12.0 P0）"""
        import os

        if not path or pid == os.getpid():
            return
        try:
            count = self.tabs.count()
        except Exception:
            return
        for idx in range(count):
            try:
                editor = self.tabs.widget(idx)
                fp = getattr(getattr(editor, "document", None), "filepath", "") or ""
                if not fp or os.path.normcase(fp) != os.path.normcase(path):
                    continue
                doc = getattr(editor, "document", None)
                if doc is None:
                    modified = False
                else:
                    try:
                        modified = bool(doc.is_modified)
                    except TypeError:
                        modified = bool(doc.is_modified())
                if modified:
                    self._last_remote_conflict = {"path": path, "mtime": mtime, "pid": pid}
                    from PyQt5.QtWidgets import QMessageBox

                    ret = QMessageBox.question(
                        self,
                        "保存冲突",
                        "该文件已被其它实例保存，而本地还有未保存修改。\n"
                        "继续保留本地修改可能与对方互相覆盖。\n\n"
                        "是否重新加载磁盘上的最新内容？\n%s" % path,
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No,
                    )
                    if ret != QMessageBox.Yes:
                        try:
                            self.status_bar.showMessage(
                                "保留本地修改（冲突未解决）: %s" % os.path.basename(path), 4000
                            )
                        except Exception:
                            pass
                        return
                reload_fn = getattr(self.tabs, "_reload_file", None)
                if reload_fn is not None:
                    reload_fn(path, editor)
                    self._last_remote_conflict = None
                    self.status_bar.showMessage("已从磁盘重载: %s" % os.path.basename(path), 3000)
                return
            except Exception:
                continue

    def _apply_theme_to_top_levels(self, qss=None):
        """把当前主题 QSS 套到所有独立顶层窗口（C-2）"""
        qss = qss or getattr(self, "_current_theme_qss", "")
        if not qss:
            return 0
        try:
            from PyQt5.QtWidgets import QApplication, QMenu, QToolTip
        except Exception:
            return 0
        theme = getattr(self, "_startup_theme", None)
        count = 0
        for w in QApplication.topLevelWidgets():
            try:
                if w is self or not w.isWindow():
                    continue
                if isinstance(w, (QMenu, QToolTip)):
                    continue
                if w.styleSheet() != qss:
                    w.setStyleSheet(qss)
                    count += 1
                if theme is not None:
                    adapt_widget_styles(w, theme)
            except Exception:
                continue
        return count

    def _ensure_toplevel_theme_filter(self):
        """确保安装了"新窗口显示时套主题"的应用级事件过滤器"""
        try:
            from PyQt5.QtWidgets import QApplication

            if getattr(self, "_toplevel_theme_filter", None) is not None:
                return
            self._toplevel_theme_filter = _TopLevelThemeFilter(self)
            QApplication.instance().installEventFilter(self._toplevel_theme_filter)
        except Exception as e:
            print(f"[MainWindow] 安装顶层主题过滤器失败: {e}")

    def _open_dropped_paths(self, paths):
        """打开拖入的文件/目录（供 dropEvent 与测试复用）"""
        import os as _os

        opened = 0
        for path in paths or []:
            try:
                if not path:
                    continue
                if _os.path.isdir(path):
                    if hasattr(self, "_open_folder"):
                        self._open_folder(path)
                    continue
                if hasattr(self, "tabs") and self.tabs is not None:
                    self.tabs.open_file(path)
                    opened += 1
            except Exception as e:
                print(f"[MainWindow] 拖放打开失败({path}): {e}")
        if opened:
            try:
                self.status_bar.showMessage("已打开 %d 个拖入文件" % opened, 2500)
            except Exception:
                pass
        return opened

    def dragEnterEvent(self, event):
        try:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                return
        except Exception:
            pass
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        try:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                return
        except Exception:
            pass
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        try:
            if not event.mimeData().hasUrls():
                super().dropEvent(event)
                return
            paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            event.acceptProposedAction()
            self._open_dropped_paths(paths)
        except Exception as e:
            print(f"[MainWindow] 拖放处理失败: {e}")

    def _build_print_document(self):
        """把当前编辑器文本构建为 QTextDocument（供打印/预览复用）"""
        from PyQt5.QtGui import QFont, QTextDocument

        proxy = self.tabs.current_proxy()
        text = ""
        try:
            if proxy is not None:
                text = proxy.get_text() or ""
        except Exception:
            text = ""
        doc = QTextDocument()
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(10)
        doc.setDefaultFont(font)
        doc.setPlainText(text)
        return doc, proxy

    def _print_document(self):
        """文件 → 打印…（NPP 对齐）"""
        try:
            from PyQt5.QtPrintSupport import QPrintDialog, QPrinter

            doc, _proxy = self._build_print_document()
            if doc.isEmpty():
                self.status_bar.showMessage("没有可打印的内容", 2500)
                return
            printer = QPrinter(QPrinter.HighResolution)
            dlg = QPrintDialog(printer, self)
            dlg.setWindowTitle("打印")
            if dlg.exec_() == QPrintDialog.Accepted:
                doc.print_(printer)
                self.status_bar.showMessage("已发送到打印机", 2500)
        except Exception as e:
            self.status_bar.showMessage("打印失败: %s" % e, 3000)

    def _print_preview(self):
        """文件 → 打印预览…（NPP 对齐）"""
        try:
            from PyQt5.QtPrintSupport import QPrinter, QPrintPreviewDialog

            doc, _proxy = self._build_print_document()
            if doc.isEmpty():
                self.status_bar.showMessage("没有可打印的内容", 2500)
                return
            printer = QPrinter(QPrinter.HighResolution)
            dlg = QPrintPreviewDialog(printer, self)
            dlg.setWindowTitle("打印预览")
            dlg.resize(900, 700)
            dlg.paintRequested.connect(lambda pr: doc.print_(pr))
            dlg.exec_()
        except Exception as e:
            self.status_bar.showMessage("打印预览失败: %s" % e, 3000)

    _TOOLBAR_ICONS = (
        ("新建", "📄"),
        ("打开", "📂"),
        ("保存", "💾"),
        ("撤销", "↶"),
        ("重做", "↷"),
        ("查找", "🔍"),
        ("替换", "🔁"),
        ("运行", "▶"),
        ("终端", "🖥"),
        ("插件", "🧩"),
        ("主题", "🎨"),
        ("格式化", "✨"),
        ("对比", "🔀"),
        ("书签", "🔖"),
        ("导出", "📤"),
    )

    def _build_emoji_icon(self, text: str):
        """用 emoji 生成工具栏图标（无需图片资源）"""
        from PyQt5.QtCore import Qt as _Qt
        from PyQt5.QtGui import QFont, QPainter, QPixmap

        emoji = "🔹"
        for key, e in self._TOOLBAR_ICONS:
            if key in (text or ""):
                emoji = e
                break
        pm = QPixmap(22, 22)
        pm.fill(_Qt.transparent)
        painter = QPainter(pm)
        try:
            font = QFont()
            font.setPointSize(13)
            painter.setFont(font)
            painter.drawText(pm.rect(), _Qt.AlignCenter, emoji)
        finally:
            painter.end()
        return QIcon(pm)

    def _set_welcome_page_enabled(self, enabled: bool):
        """视图 → 显示欢迎页（持久化偏好；NPP 默认无欢迎页）"""
        enabled = bool(enabled)
        self._welcome_visible_pref = enabled
        try:
            self.prefs.set("show_welcome_page", enabled)
        except Exception:
            pass
        try:
            if not enabled:
                self.central_stack.setCurrentIndex(0)
            elif self.tabs.count() == 0 and getattr(self, "welcome", None) is not None:
                self.central_stack.setCurrentIndex(1)
        except Exception:
            pass

    def _apply_language_by_extension(self):
        """语言 → 自动：按当前文件扩展名重新应用词法器"""
        try:
            proxy = self.tabs.current_proxy()
            sc = getattr(proxy, "sc", None) if proxy else None
            if sc is None:
                self.status_bar.showMessage("没有打开的编辑器", 2500)
                return
            path = ""
            try:
                path = getattr(proxy.document, "filepath", "") or ""
            except Exception:
                pass
            sc._last_lexer_filepath = None
            self._active_language_pack_name = None
            sc.set_lexer_by_filename(path)
            self.status_bar.showMessage("语言：已按扩展名自动识别", 2000)
        except Exception as e:
            self.status_bar.showMessage("切换语言失败: %s" % e, 3000)

    def _apply_language_pack(self, pack):
        """语言 → 声明式语言包：对当前编辑器应用通用词法器"""
        try:
            proxy = self.tabs.current_proxy()
            sc = getattr(proxy, "sc", None) if proxy else None
            if sc is None:
                self.status_bar.showMessage("没有打开的编辑器", 2500)
                return
            from ui.generic_lexer import create_generic_lexer

            self._active_language_pack_name = pack.name
            sc.set_lexer(create_generic_lexer(pack, sc))
            self.status_bar.showMessage("语言：已应用 %s" % (pack.name or "语言包"), 2000)
        except Exception as e:
            self.status_bar.showMessage("应用语言包失败: %s" % e, 3000)

    def _show_search(self):
        """显示搜索栏"""
        try:
            # P1-3: 惰性构造
            self._ensure_panel("search_bar")
            if self.search_bar:
                self.search_bar.show()
                if hasattr(self.search_bar, "show_and_focus"):
                    self.search_bar.show_and_focus()
        except Exception as e:
            print(f"[MainWindow] 显示搜索栏失败: {e}")

    def _show_global_search(self):
        """显示全局搜索"""
        try:
            # P1-3: 惰性构造
            self._ensure_panel("gsearch")
            if self.gsearch:
                self.gsearch.show()
                if hasattr(self.gsearch, "focus_search"):
                    self.gsearch.focus_search()
        except Exception as e:
            print(f"[MainWindow] 显示全局搜索失败: {e}")

    def _goto_line_dialog(self):
        """跳转到行（对话框形式，P3-2 由 _show_line_palette 改名）"""
        try:
            proxy = self.tabs.current_proxy()
            if not proxy or not proxy.sc:
                return

            total = proxy.sc.SendScintilla(proxy.sc.SCI_GETLINECOUNT)
            if total <= 0:
                total = 1
            line, ok = QInputDialog.getInt(self, "跳转到行", "行号:", 1, 1, total)
            if ok:
                proxy.sc.setCursorPosition(line - 1, 0)
                proxy.sc.ensureLineVisible(line - 1)
        except Exception as e:
            print(f"[MainWindow] 跳转失败: {e}")

    # 向后兼容别名（P3-2）
    def _show_line_palette(self):
        """[已弃用] 请使用 _goto_line_dialog"""
        return self._goto_line_dialog()

    # ========================================================
    # 视图操作
    # ========================================================
    def _toggle_column_mode(self, checked=None):
        """切换列模式。

        修复 P0-C4:
            菜单里的"▦ 列模式"用 _add_action 创建的非 checkable
            QAction，triggered 信号固定传 checked=False。
            原代码 `if isinstance(checked, bool): enabled = checked`
            会因此认为"用户想关闭列模式"，从菜单点击无效。

            改为：始终基于工具栏 action 的**真实状态**翻转，
            忽略 triggered 传入的 checked 参数。
        """
        try:
            if hasattr(self, "column_mode_action"):
                # 修复 P0-C4: 忽略 triggered 的 checked 参数，
                # 始终基于工具栏 action 的当前状态翻转
                enabled = not self.column_mode_action.isChecked()
                self.column_mode_action.blockSignals(True)
                self.column_mode_action.setChecked(enabled)
                self.column_mode_action.blockSignals(False)
            else:
                # 无工具栏按钮时，退回到 checked 参数
                enabled = not (checked if isinstance(checked, bool) else False)

            proxy = self.tabs.current_proxy()
            if proxy and hasattr(proxy, "set_column_mode"):
                proxy.set_column_mode(enabled)

            self.status_bar.showMessage("列模式" if enabled else "流模式", 2000)
        except Exception as e:
            print(f"[MainWindow] 切换列模式失败: {e}")

    def toggle_fullscreen(self):
        """切换全屏"""
        if self._fullscreen_mode:
            self.showNormal()
            self._fullscreen_mode = False
        else:
            self.showFullScreen()
            self._fullscreen_mode = True

    def _zoom_in(self):
        """放大字体"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.sc:
                proxy.sc.zoomIn()
        except Exception:
            pass

    def _zoom_out(self):
        """缩小字体"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.sc:
                proxy.sc.zoomOut()
        except Exception:
            pass

    def _zoom_reset(self):
        """重置字体"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.sc:
                font = QFont("Consolas", 12)
                proxy.sc.setFont(font)
        except Exception:
            pass

    # ========================================================
    # 大文件高亮开关（性能 vs 视觉的显式取舍）
    # ========================================================
    def _toggle_force_highlight_large_files(self, checked: bool):
        """切换"大文件强制高亮"

        默认关闭：大文档（>20 万行或 >8MB）跳过语法高亮与缩略图，
        把 2MB/50 万行的打开时间从 2.1s 降到 ~0.5s。
        开启后对当前标签立即重新应用词法器（用户自己承担耗时）。
        """
        self._force_highlight_large_files = bool(checked)
        try:
            proxy = self.tabs.current_proxy()
        except Exception:
            proxy = None
        sc = getattr(proxy, "sc", None) if proxy is not None else None
        if sc is None:
            return
        try:
            # 清掉去重标记，强制重新判定
            sc._last_lexer_filepath = None
            path = ""
            try:
                path = getattr(proxy.document, "filepath", "") or ""
            except Exception:
                pass
            sc.set_lexer_by_filename(path)
            if self.minimap is not None:
                self.minimap.set_editor(sc)
            self.statusBar().showMessage(
                "大文件强制高亮：%s" % ("已开启" if checked else "已关闭"), 3000
            )
        except Exception as e:
            print(f"[MainWindow] 切换大文件高亮失败: {e}")

    # ========================================================
    # 面板切换
    # ========================================================
    def _toggle_outline(self, checked):
        """切换大纲面板（基础版）"""
        if self._ensure_panel("outline") and self.outline:
            self.outline.setVisible(checked)

    def _toggle_outline_enhanced(self, checked):
        """切换增强版大纲面板"""
        if self._ensure_panel("outline_enhanced") and self.outline_enhanced:
            self.outline_enhanced.setVisible(checked)

    def _toggle_directory(self, checked):
        """切换目录树面板"""
        if self._ensure_panel("dir_tree") and self.dir_tree_dock:
            self.dir_tree_dock.setVisible(checked)

    def _toggle_minimap(self, checked):
        """切换 Minimap"""
        if self._ensure_panel("minimap") and self.minimap_dock:
            self.minimap_dock.setVisible(checked)

    def _toggle_global_search(self, checked):
        """切换全局搜索"""
        if self._ensure_panel("gsearch") and self.gsearch:
            self.gsearch.setVisible(checked)

    def _toggle_console(self):
        """切换控制台"""
        try:
            if self._ensure_panel("console") and self.console:
                self.console.setVisible(not self.console.isVisible())
        except Exception as e:
            print(f"[MainWindow] 控制台切换失败: {e}")

    def _toggle_perf_monitor(self, checked):
        """切换性能监控"""
        if self._ensure_panel("perf_monitor") and self.perf_monitor:
            self.perf_monitor.setVisible(checked)

    # ========================================================
    # 工具
    # ========================================================
    def _show_command_palette(self):
        """显示命令面板"""
        try:
            from ui.command_palette import create_command_palette

            palette = create_command_palette(
                self.act_mgr, self, tab_mgr=self.tabs, outline=self.outline
            )
            if hasattr(palette, "center_on_parent"):
                palette.center_on_parent()
            palette.exec_()
        except Exception as e:
            import traceback

            traceback.print_exc()
            print(f"[MainWindow] 命令面板失败: {e}")

    def _show_file_palette(self):
        """显示文件切换面板"""
        try:
            from ui.command_palette import create_file_palette

            palette = create_file_palette(self.act_mgr, self.tabs, self)
            if hasattr(palette, "center_on_parent"):
                palette.center_on_parent()
            palette.exec_()
        except Exception as e:
            print(f"[MainWindow] 文件面板失败: {e}")

    def _show_symbol_palette(self):
        """显示符号跳转面板"""
        try:
            from ui.command_palette import create_symbol_palette

            palette = create_symbol_palette(self.act_mgr, self.tabs, self.outline, self)
            if hasattr(palette, "center_on_parent"):
                palette.center_on_parent()
            palette.exec_()
        except Exception as e:
            print(f"[MainWindow] 符号面板失败: {e}")

    def _current_undo_manager(self):
        """当前标签 proxy 的 UndoManager（P0-1 的绑定来源）

        为什么是"回调"而不是保存一个引用:
            每个标签页都有自己的 `EditorProxy` 与 `UndoManager`
            （`core/editor.py` 的 `EditorProxy.__init__`），用户随时可能
            切换标签。若在构造 `MacroRecorder` 时固定绑定一个 manager，
            录制中切换标签就会记到错误的对象上（或什么都记不到）。
            `MacroRecorder` 在 start()/stop() 时会调用本方法重新解析。
        """
        try:
            proxy = self.tabs.current_proxy()
        except Exception:
            return None
        if proxy is None:
            return None
        return getattr(proxy, "undo_manager", None)

    def _on_macro_error(self, message: str):
        """宏录制/回放错误 → 状态栏（P0-1）

        缺陷背景：`MacroRecorder.error_occurred` 原先**没有任何接收者**，
        录不到命令时只有 `print()`（GUI 打包后不可见）—— 用户看到的是
        "录制中"却录不到东西的静默失败。
        """
        try:
            self.status_bar.showMessage(f"宏: {message}", 5000)
        except Exception:
            pass

    def _toggle_macro(self):
        """切换宏录制"""
        if not self.macro:
            self.status_bar.showMessage("宏功能不可用", 2000)
            return
        try:
            # 兼容不同版本：使用 recording 属性或 is_recording 方法
            is_recording = False
            if hasattr(self.macro, "recording"):
                is_recording = bool(self.macro.recording)
            elif hasattr(self.macro, "is_recording"):
                is_recording = bool(self.macro.is_recording())

            if is_recording:
                macro = self.macro.stop()
                self.rec_label.hide()
                # P0-1: 明确回报录到几条 —— "录制中"却不显示数量时，
                # 用户无法察觉"录到 0 条"这种静默失败。
                count = 0
                try:
                    count = len(getattr(macro, "commands", []) or [])
                except Exception:
                    count = 0
                self.status_bar.showMessage(f"宏录制已停止（{count} 条命令）", 3000)
            else:
                # P0-1: 开始录制前先绑定当前标签的 undo_manager
                # （标签可能自上次录制后已切换；start() 内部也会再解析一次）
                if hasattr(self.macro, "bind_current_undo_manager"):
                    self.macro.bind_current_undo_manager()
                self.macro.start()
                self.rec_label.setText("● REC")
                self.rec_label.show()
                # 没绑上 = 必然录到 0 条：立刻可见地告诉用户，
                # 而不是等他录完、回放时才提示"没有可回放的宏"。
                if hasattr(self.macro, "has_hook") and not self.macro.has_hook:
                    self.status_bar.showMessage(
                        "宏录制已开始，但当前没有可录制的编辑器（请先打开或新建标签）", 5000
                    )
                else:
                    self.status_bar.showMessage("宏录制已开始", 2000)
        except Exception as e:
            print(f"[MainWindow] 宏录制失败: {e}")

    def _play_macro(self):
        """回放宏"""
        if not self.macro:
            self.status_bar.showMessage("宏功能不可用", 2000)
            return
        try:
            proxy = self.tabs.current_proxy()
            if not proxy:
                return

            has_commands = False
            if hasattr(self.macro, "has_commands"):
                has_commands = self.macro.has_commands()
            elif hasattr(self.macro, "commands"):
                has_commands = bool(self.macro.commands)

            if not has_commands:
                self.status_bar.showMessage("没有可回放的宏", 2000)
                return

            self.macro.replay(proxy, repeat=1)
            self.status_bar.showMessage("宏回放完成", 2000)
        except Exception as e:
            self._show_error("宏回放失败", str(e))

    def _show_keymap_editor(self):
        """显示快捷键编辑器"""
        try:
            from ui.keymap_editor import KeymapEditor

            dlg = KeymapEditor(self.act_mgr, self)
            dlg.exec_()
        except Exception as e:
            self._show_error("快捷键编辑器失败", str(e))

    def _show_perf_monitor(self):
        """显示性能监控面板"""
        try:
            # P1-3: 惰性构造
            self._ensure_panel("perf_monitor")
            if self.perf_monitor:
                self.perf_monitor.show()
                self.perf_monitor.raise_()
        except Exception as e:
            self._show_error("性能监控失败", str(e))

    # VimMode 实例（增强：信号连接 + setFocus）
    def _toggle_vim_mode(self, checked: bool):
        """切换 Vim 模式

        为当前编辑器附加/移除 VimMode 实例。
        """
        try:
            from core.vim_mode import VimMode

            proxy = self.tabs.current_proxy()
            if not proxy or not proxy.sc:
                self.status_bar.showMessage("没有活动的编辑器", 2000)
                self.vim_mode_action.setChecked(False)
                return

            editor = proxy.sc

            if checked:
                vim = getattr(editor, "_vim_mode", None)
                if vim is None:
                    vim = VimMode(editor)
                    editor._vim_mode = vim

                # 首次创建时连接信号（状态栏显示模式）
                if not getattr(vim, "_signal_connected", False):
                    try:
                        vim.status_message.connect(
                            lambda msg: self.status_bar.showMessage(msg, 2000) if msg else None
                        )
                        vim.state_changed.connect(
                            lambda st: self.status_bar.showMessage(f"Vim: {st}", 1500)
                        )
                        vim._signal_connected = True
                    except Exception:
                        pass

                vim.set_enabled(True)

                # 焦点给编辑器，否则按键进不来
                try:
                    editor.setFocus()
                except Exception:
                    pass

                # A: 缩短启用提示，避免覆盖 VimMode 的状态显示
                # 原来显示 4000ms，会盖住 VimMode 的 "-- 普通 --"
                self.status_bar.showMessage("Vim 模式已启用", 1500)
                print("[MainWindow] Vim 模式已启用")
            else:
                vim = getattr(editor, "_vim_mode", None)
                if vim is not None:
                    vim.set_enabled(False)
                self.status_bar.showMessage("Vim 模式已禁用", 2000)
                print("[MainWindow] Vim 模式已禁用")
        except Exception as e:
            print(f"[MainWindow] Vim 切换失败: {e}")
            import traceback

            traceback.print_exc()
            self.status_bar.showMessage(f"Vim 切换失败: {e}", 3000)

    def _export_config(self):
        """导出配置"""
        try:
            from app.config_manager import ConfigManager

            cm = ConfigManager()
            cm.export_config(self)
        except Exception as e:
            self._show_error("导出失败", str(e))

    def _import_config(self):
        """导入配置"""
        try:
            from app.config_manager import ConfigManager

            cm = ConfigManager()
            cm.import_config(self)
        except Exception as e:
            self._show_error("导入失败", str(e))

    # ========================================================
    # 帮助
    # ========================================================
    def _show_shortcuts(self):
        """显示快捷键参考"""
        shortcuts = [
            ("Ctrl+N", "新建文件"),
            ("Ctrl+O", "打开文件"),
            ("Ctrl+S", "保存文件"),
            ("Ctrl+Shift+S", "另存为"),
            ("Ctrl+W", "关闭标签"),
            ("Ctrl+Z / Ctrl+Y", "撤销 / 重做"),
            ("Ctrl+X/C/V", "剪切 / 复制 / 粘贴"),
            ("Ctrl+F", "查找"),
            ("Ctrl+Shift+F", "全局搜索"),
            ("Ctrl+Shift+P", "命令面板"),
            ("Ctrl+P", "文件切换"),
            ("Ctrl+Alt+R", "符号跳转"),
            ("Ctrl+G", "跳转到行"),
            ("Ctrl+/", "注释切换"),
            ("Ctrl+D", "选择下一项"),
            ("Alt+C", "列模式"),
            ("Ctrl+`", "Python 控制台"),
            ("Ctrl+Space", "自动补全"),
            ("F5", "插入日期时间"),
            ("F11", "无干扰模式"),
            ("Shift+F11", "全屏"),
        ]

        text = "青草编辑器快捷键参考\n" + "=" * 40 + "\n\n"
        for key, desc in shortcuts:
            text += f"{key:25s} {desc}\n"

        dlg = QDialog(self)
        dlg.setWindowTitle("快捷键参考")
        dlg.resize(500, 600)
        layout = QVBoxLayout(dlg)

        browser = QTextBrowser()
        browser.setPlainText(text)
        layout.addWidget(browser)

        btn = QPushButton("关闭")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)

        dlg.exec_()

    def _show_daily_tip(self, manual: bool = False):
        """
        显示每日技巧。

        P2-8: 一天只显示一次（基于 QSettings 记录日期）。
        P2-C4: manual=True 时（菜单手动点击）跳过日期限制，
               否则用户当天已自动弹过，手动点击就没反应了。
        """
        try:
            import datetime

            settings = QSettings(ORG_NAME, "Editor")
            today = datetime.date.today().isoformat()

            last_date = settings.value("last_tip_date", "", type=str)
            # P2-C4: manual 参数
            if not manual and last_date == today:
                return  # 今天已弹过，且是自动触发

            # 标记今天已弹
            # P2-2: 仅自动触发时更新 last_tip_date
            # 原实现手动点击也更新，导致用户当天手动点一次后，
            # 第二天的自动弹出会被抑制到后天。
            if not manual:
                settings.setValue("last_tip_date", today)
                settings.sync()
        except Exception as e:
            # 若 QSettings 异常，则退回为"每次都弹"
            print(f"[MainWindow] 每日技巧日期检查失败: {e}")

        # 显示技巧
        try:
            from ui.tips import get_tip

            tip = get_tip()
        except Exception:
            tips = [
                "按 Ctrl+Shift+P 打开命令面板，搜索所有功能。",
                "按 Alt+C 进入列模式，可同时编辑多行。",
                "Ctrl+D 选中当前单词，再按一次选中下一个相同单词。",
                "拖拽标签到窗口外可分离为独立窗口。",
                "按 Ctrl+Shift+R 录制宏，Ctrl+Shift+M 回放。",
                "选中文本后输入括号可自动包裹。",
                "按 F5 插入当前日期时间。",
                "按 Ctrl+/ 注释或取消注释当前行。",
            ]
            import random

            tip = random.choice(tips)

        QMessageBox.information(self, "💡 每日技巧", tip)

    def _show_online_docs(self):
        """打开在线文档"""
        try:
            QDesktopServices.openUrl(QUrl("https://qingcao-editor.github.io/docs"))
        except Exception:
            pass

    def _show_github(self):
        """打开 GitHub"""
        try:
            QDesktopServices.openUrl(QUrl("https://github.com/qingcao-editor/qingcao"))
        except Exception:
            pass

    def _about(self):
        """关于对话框"""
        QMessageBox.about(
            self,
            "关于青草编辑器",
            f"<h2>{APP_NAME} v{APP_VERSION}</h2>"
            "<p>轻量 · 极速 · 可扩展</p>"
            "<p>开发者：TomJerry</p>"
            "<p>联系：1265338136@qq.com</p>"
            "<p><i>青草枯荣，野火重生。</i></p>",
        )

    # ========================================================
    # 状态栏更新
    # ========================================================
    def _on_status_message(self, event):
        """状态消息事件"""
        try:
            msg = getattr(event, "message", str(event))
            timeout = getattr(event, "timeout", 3000)
            self.status_bar.showMessage(msg, timeout)
        except Exception:
            pass

    def _on_cursor_moved(self, event):
        """光标移动"""
        try:
            line = getattr(event, "line", 1)
            col = getattr(event, "col", 0)
            self.cursor_label.setText(f"行 {line}, 列 {col}")
        except Exception:
            pass

    def _on_tab_changed(self, index: int):
        """
        标签切换。

        P2-5: 同步 column_mode_action 状态，避免 UI 与实际不一致。
        """
        try:
            if index < 0:
                return

            editor = self.tabs.widget(index)
            if not editor:
                return

            # 大纲（基础版）
            if self.outline:
                try:
                    if hasattr(self.outline, "update_symbols"):
                        self.outline.update_symbols(editor)
                    elif hasattr(self.outline, "schedule_update"):
                        self.outline.schedule_update()
                except Exception as e:
                    print(f"[MainWindow] 大纲更新失败: {e}")

            # 大纲（增强版）
            if self.outline_enhanced:
                try:
                    if hasattr(self.outline_enhanced, "update_symbols"):
                        self.outline_enhanced.update_symbols(editor)
                    elif hasattr(self.outline_enhanced, "schedule_update"):
                        self.outline_enhanced.schedule_update()
                except Exception as e:
                    print(f"[MainWindow] 增强大纲更新失败: {e}")

            # Minimap（安全调用）
            if self.minimap:
                try:
                    if hasattr(self.minimap, "set_editor"):
                        self.minimap.set_editor(editor)
                except Exception as e:
                    print(f"[MainWindow] Minimap 更新失败: {e}")

            # 状态栏
            self._update_status_for_editor()

            # Git 分支
            self._update_git_branch()

            # P2-5: 同步列模式状态
            self._sync_column_mode_state()

            # P6: LSP 总开关打开时，为新标签补上 LSP（幂等）
            self._sync_lsp_for_current_tab()

            # P0-1: 录制中切换标签 → 录制钩子必须跟着切到新标签的
            # undo_manager（proxy 是每标签一个）。否则用户在录制过程中
            # 切了标签，之后的编辑一条也录不到，而 UI 仍显示"● REC"。
            try:
                macro = getattr(self, "macro", None)
                if (
                    macro is not None
                    and getattr(macro, "recording", False)
                    and hasattr(macro, "bind_current_undo_manager")
                ):
                    macro.bind_current_undo_manager()
            except Exception as e:
                print(f"[MainWindow] 切换标签后重绑宏录制失败: {e}")

        except Exception as e:
            print(f"[MainWindow] 标签切换失败: {e}")

    def _sync_column_mode_state(self):
        """同步工具栏列模式按钮状态（P2-5）"""
        try:
            if not hasattr(self, "column_mode_action"):
                return

            proxy = self.tabs.current_proxy()
            if not proxy or not hasattr(proxy, "is_column_mode"):
                return

            is_col = bool(proxy.is_column_mode())
            if self.column_mode_action.isChecked() != is_col:
                # 阻断信号避免触发 _toggle_column_mode 再次调用
                self.column_mode_action.blockSignals(True)
                self.column_mode_action.setChecked(is_col)
                self.column_mode_action.blockSignals(False)
        except Exception as e:
            print(f"[MainWindow] 同步列模式状态失败: {e}")

    def _sync_lsp_for_current_tab(self):
        """P6: LSP 总开关打开时，切标签后为新编辑器补上 LSP（幂等）。

        只对 `LSP_LANGUAGE_BY_EXT` 里认得出的文件类型自动启用，避免
        每次切到 .txt / .log 都弹一次"不支持"的提示。
        """
        try:
            if not hasattr(self, "lsp_action") or not self.lsp_action.isChecked():
                return
            proxy = self.tabs.current_proxy()
            if proxy is None or not hasattr(proxy, "toggle_lsp"):
                return
            if getattr(proxy, "lsp_client", None) is not None:
                return

            filepath = ""
            if getattr(proxy, "document", None) is not None:
                filepath = proxy.document.filepath or ""
            try:
                from core.editor import lsp_language_for_file

                if not filepath or not lsp_language_for_file(filepath):
                    return
            except Exception:
                return

            self._connect_lsp_signals(proxy)
            if proxy.toggle_lsp(True) and filepath:
                self._lsp_clients[filepath] = proxy
        except Exception as e:
            logger.debug("切换标签后同步 LSP 失败: %s", e)

    def _on_all_tabs_closed(self):
        """所有标签关闭"""
        try:
            self.central_stack.setCurrentIndex(1)

            if self.minimap and hasattr(self.minimap, "set_editor"):
                try:
                    self.minimap.set_editor(None)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_symbol_clicked(self, line: int):
        """大纲符号点击"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.sc:
                proxy.sc.setCursorPosition(line, 0)
                proxy.sc.ensureLineVisible(line)
                proxy.sc.setFocus()
        except Exception:
            pass

    def _on_file_from_tree(self, filepath: str):
        """从目录树打开文件"""
        try:
            self.central_stack.setCurrentIndex(0)
            self.tabs.open_file(filepath)
        except Exception as e:
            print(f"[MainWindow] 打开文件失败: {e}")

    def _on_search_match_activated(self, filepath: str, start: int, end: int, line: int, col: int):
        """全局搜索匹配激活"""
        try:
            proxy = self.tabs.open_file(filepath)
            if proxy and proxy.sc:
                try:
                    proxy.sc.SendScintilla(proxy.sc.SCI_SETSEL, start, end)
                except Exception:
                    pass
                proxy.sc.setCursorPosition(line - 1, col)
                proxy.sc.ensureLineVisible(line - 1)
        except Exception as e:
            print(f"[MainWindow] 搜索跳转失败: {e}")

    def _current_search_options(self, pattern: str):
        """取"当前搜索选项"：优先全局搜索面板的勾选（P0-3）

        缺陷背景（P0-3，实测确认）:
            `_on_global_replace` 原先自己 new 了一份
            `SearchOptions(pattern=pattern)` —— 即
            `is_regex=False / case_sensitive=False / whole_word=False`
            的**默认值**，完全无视面板上的勾选。后果是"正则搜索 + 全部替换"
            按字面量替换：例如用 `\\d+` 搜到 12 个匹配，替换阶段却去找
            字面量 `\\d+`，一处也匹配不上（静默 0 处替换）。

        修复策略：面板的 `build_options()` 是选项的**唯一构造点**，
        并把选项对象随 `replace_requested` 信号一起传进来（见
        `ui/global_search_panel.py`）。本方法只是"面板不可用"时的兜底，
        行为与修复前一致，不会更差。
        """
        gsearch = getattr(self, "gsearch", None)
        if gsearch is not None and hasattr(gsearch, "build_options"):
            try:
                options = gsearch.build_options()
                if options is not None:
                    if pattern and not options.pattern:
                        options.pattern = pattern
                    return options
            except Exception as e:
                print(f"[MainWindow] 读取搜索选项失败: {e}")

        from core.search import SearchOptions

        return SearchOptions.from_preferences(pattern=pattern)

    def _on_global_replace(self, pattern: str, replace_text: str, file_results: dict, options=None):
        """P2-C5: 全局搜索 → 全部替换。

        参数:
            pattern: 搜索模式
            replace_text: 替换文本
            file_results: {filepath: [SearchMatch, ...]}
            options: 搜索选项（P0-3；由面板随信号传入）

        缺陷背景（P0-3，已实测）:
            本方法原先用 `SearchOptions(pattern=pattern)` 重建选项 ——
            面板上勾选的"正则 / 大小写 / 全词 / 转义 / 多行"被**静默丢弃**。
            更隐蔽的是：这里对每个文件**重新搜索**一遍来确定匹配位置，
            用默认选项重搜，得到的匹配集与用户看到的搜索结果根本不是同一批
            （正则表达式在字面量模式下往往匹配到 0 处），替换位置随之错乱。

            修复后：搜索与替换共用同一个 `SearchOptions` 对象
            （`GlobalSearchPanel.build_options()` 构造、
            `replace_requested` 信号携带），语义上保证"所见即所替"。
        """
        if not pattern or not file_results:
            return

        if options is None:
            options = self._current_search_options(pattern)

        try:
            from core.content_provider import LocalFileProvider
            from core.search import ReplaceEngine, SearchEngine

            total = 0
            abs_paths = set()

            for filepath in file_results:
                abs_paths.add(os.path.abspath(filepath))
                try:
                    provider = LocalFileProvider()
                    provider.open(filepath)
                    try:
                        # P0-3: 复用同一套选项（正则/大小写/全词/转义/多行），
                        # 而不是 SearchOptions 的默认值
                        engine = SearchEngine(provider, options)
                        result = engine.search()
                        if result.is_empty:
                            continue

                        replace_engine = ReplaceEngine(provider)
                        n = replace_engine.replace_all(
                            result,
                            replace_text,
                            is_regex=options.is_regex,
                            pattern=options.pattern,
                        )
                        provider.save(filepath)
                        total += n
                    finally:
                        provider.close()
                except Exception as e:
                    print(f"[MainWindow] 替换 {filepath} 失败: {e}")

            # 刷新已打开的受影响文件
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if not hasattr(w, "proxy") or not w.proxy:
                    continue
                fp = None
                try:
                    if w.proxy.document:
                        fp = w.proxy.document.filepath
                except Exception:
                    pass
                if fp and os.path.abspath(fp) in abs_paths:
                    try:
                        if w.proxy.document:
                            w.proxy.document.reload()
                        if w.proxy.sc and w.proxy.document:
                            w.proxy.sc.setText(w.proxy.document.get_text())
                    except Exception:
                        pass

            self.status_bar.showMessage(f"已替换 {total} 处", 3000)

        except Exception as e:
            print(f"[MainWindow] 全局替换失败: {e}")

    # ========================================================
    # 标签切换辅助
    # ========================================================
    def _next_tab(self):
        """下一个标签"""
        try:
            count = self.tabs.count()
            if count > 1:
                idx = (self.tabs.currentIndex() + 1) % count
                self.tabs.setCurrentIndex(idx)
        except Exception:
            pass

    def _prev_tab(self):
        """上一个标签"""
        try:
            count = self.tabs.count()
            if count > 1:
                idx = (self.tabs.currentIndex() - 1) % count
                self.tabs.setCurrentIndex(idx)
        except Exception:
            pass

    # ========================================================
    # 会话
    # ========================================================
    def _restore_session(self):
        """恢复会话"""
        try:
            if not self.session:
                return

            if self.prefs and not self.prefs.get("restore_session", True):
                return

            count = self.session.restore(self.tabs, self, confirm_recovery=False)

            if count and count > 0:
                self.central_stack.setCurrentIndex(0)
                self.status_bar.showMessage(f"已恢复 {count} 个文件", 3000)
                self.session_restored.emit(count)
        except Exception as e:
            print(f"[MainWindow] 恢复会话失败: {e}")

    def restore_session(self):
        """公开接口：恢复会话（供 main.py 调用）"""
        self._restore_session()

    def _autosave_session(self):
        """
        自动保存会话。

        P2-3: 无打开文件时跳过，避免每 2 分钟无谓写盘。
        """
        try:
            if not self.session:
                return

            if self.prefs and not self.prefs.get("restore_session", True):
                return

            # 无打开文件则跳过
            if self.tabs.count() == 0:
                return

            self.session.save(self.tabs, self)
        except Exception:
            pass

    def save_session(self):
        """手动保存会话"""
        try:
            if self.session:
                self.session.save(self.tabs, self)
        except Exception as e:
            print(f"[MainWindow] 保存会话失败: {e}")

    # ========================================================
    # 插件
    # ========================================================
    def _create_main_api(self):
        """
        创建主窗口的独立 API（P2-1）。

        与插件的 API 不同，主 API 拥有全部权限，
        不受任何插件 manifest 中 permissions 的限制。
        用于 Python 控制台、插件管理等场景。
        """
        try:
            from app.plugins import PluginAPI
        except Exception as e:
            print(f"[MainWindow] 无法导入 PluginAPI: {e}")
            return None

        # 尝试获取完整的权限列表
        perms = []
        try:
            from app.plugins import ALL_PERMISSIONS

            if ALL_PERMISSIONS:
                perms = list(ALL_PERMISSIONS)
        except Exception:
            pass

        # 若无法获取，使用内置的回退列表
        if not perms:
            perms = list(_MAIN_API_FALLBACK_PERMISSIONS)

        try:
            return PluginAPI(
                self,
                permissions=perms,
                plugin_name="__main__",
            )
        except Exception as e:
            print(f"[MainWindow] 创建主 API 失败: {e}")
            return None

    # ========================================================
    # 错误处理
    # ========================================================
    def _show_error(self, title: str, message: str):
        """显示错误"""
        # P1-2: 音效接线（默认关闭）
        try:
            from infrastructure.sound_manager import SoundEvent, play_sound

            play_sound(SoundEvent.NOTIFY_ERROR)
        except Exception:
            pass
        QMessageBox.critical(self, title, message)

    def _show_info(self, title: str, message: str):
        """显示信息"""
        QMessageBox.information(self, title, message)

    # ========================================================
    # 关闭事件
    # ========================================================
    def closeEvent(self, event):
        try:
            checker = getattr(self, "_update_checker", None)
            if checker is not None:
                checker.cancel()
        except Exception:
            pass

        # 主题事件过滤器挂在 QApplication 上：窗口销毁前必须显式移除，
        # 否则多窗口/多测试连续创建时可能访问已销毁对象（崩溃）。
        try:
            from PyQt5.QtWidgets import QApplication

            filt = getattr(self, "_toplevel_theme_filter", None)
            if filt is not None:
                QApplication.instance().removeEventFilter(filt)
                self._toplevel_theme_filter = None
        except Exception:
            pass
        self._closeEvent_impl(event)

    def _closeEvent_impl(self, event):
        self._close_sandboxed_plugins()
        """
        关闭事件。

        修复说明（P0）：
            - 原实现仅调用 event.accept()，依赖 main.py 中的
              setQuitOnLastWindowClosed(True) 退出事件循环。
            - 这里额外显式调用 QApplication.quit()（双保险），
              以覆盖"关闭主窗口时仍有其他 QDialog/子窗口存活"的
              边缘场景，确保事件循环一定能退出。
        """
        if getattr(self, "_closing", False):
            event.accept()
            return

        self._closing = True

        # 卸载多键序列的应用级按键过滤器
        #
        # ★ 修复（实测访问违例 0xC0000005）：
        #   QApplication 上的事件过滤器若在窗口销毁后仍挂着，
        #   Qt 会在下一次事件派发时调用已析构对象 → 崩溃。
        #   必须在 `_closing` 置位后**立即**卸载（此时过滤器已能安全跳过）。
        try:
            self._teardown_key_sequences()
        except Exception as e:
            logger.debug("卸载按键序列过滤器失败: %s", e)

        # 先停止文件监听并释放 provider 句柄
        #
        # 修复（实测段错误 0xC0000005 / 句柄泄漏）：
        #   `QFileSystemWatcher` 的回调可能在窗口销毁过程中被事件循环触发，
        #   此时弹模态对话框会访问正在析构的 Qt 对象 → 崩溃。
        #   同时每个标签的 provider 持有文件句柄，不释放会在 Windows 上
        #   阻止文件被外部程序修改。见 `TabManager.dispose` 的说明。
        try:
            if hasattr(self.tabs, "dispose"):
                self.tabs.dispose()
        except Exception as e:
            logger.debug("释放 TabManager 资源失败: %s", e)

        try:
            # 检查未保存文件
            modified = []
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if not hasattr(w, "proxy"):
                    continue
                proxy = w.proxy
                if proxy and hasattr(proxy, "is_modified") and proxy.is_modified:
                    fp = None
                    if proxy.document:
                        fp = proxy.document.filepath
                    modified.append(fp or "(未命名)")

            if modified:
                msg = "以下文件有未保存的修改：\n\n" + "\n".join(
                    f"• {os.path.basename(f)}" for f in modified[:10]
                )
                if len(modified) > 10:
                    msg += f"\n... 及其他 {len(modified) - 10} 个文件"
                msg += "\n\n是否放弃所有修改并退出？"

                reply = QMessageBox.question(
                    self,
                    "未保存的修改",
                    msg,
                    QMessageBox.Discard | QMessageBox.Cancel,
                    QMessageBox.Cancel,
                )

                if reply == QMessageBox.Cancel:
                    event.ignore()
                    return

            # 保存会话
            try:
                if self.session and (not self.prefs or self.prefs.get("restore_session", True)):
                    self.session.save(self.tabs, self)
            except Exception:
                pass

            # 停止定时器
            if hasattr(self, "_status_timer"):
                self._status_timer.stop()
            if hasattr(self, "_session_timer"):
                self._session_timer.stop()

            # 停止自动备份定时器（P1 收尾）
            #
            # 与构造处的 `start_autosave()` 配对。虽然定时器停不停都不影响
            # 进程退出，但显式停止能让"最后一次保存"发生在可预期的时刻，
            # 也避免对象析构后回调仍被触发。
            try:
                if self.session is not None:
                    self.session.stop_autosave()
            except Exception as e:
                logging.debug("停止自动备份定时器失败: %s", e)

            # 阶段 2.1（关闭路径收尾）：停止插件后台线程与文件监听。
            #
            # 背景：closeEvent 原先只停两个主窗口定时器就 app.quit()，
            # 而插件可能持有 QThread（如 AI 助手的 Ollama 刷新/拉取线程）
            # 与 QFileSystemWatcher（插件热重载）。Windows 上父进程退出
            # 不会连带清理子进程，且 QThread 在**运行中**被析构时 Qt 会
            # 打印 "QThread: Destroyed while thread is still running"
            # 并可能 qFatal() 导致异常退出。
            #
            # 这里逐个显式收尾，任何一步失败都不影响退出流程。
            self._shutdown_background_work()

            event.accept()

            # 显式退出事件循环（双保险，不依赖 setQuitOnLastWindowClosed）
            try:
                app = QApplication.instance()
                if app is not None:
                    app.quit()
            except Exception as quit_err:
                print(f"[MainWindow] quit() 失败: {quit_err}")

        except Exception as e:
            print(f"[MainWindow] 关闭失败: {e}")
            event.accept()
            # 即使异常也尽力退出事件循环
            try:
                app = QApplication.instance()
                if app is not None:
                    app.quit()
            except Exception:
                pass

    # ========================================================
    # 关闭时的后台资源收尾（阶段 2.1）
    # ========================================================
    def _shutdown_background_work(self, timeout_ms: int = 2000):
        """在退出前显式停止后台线程、插件监听与语言服务器。

        这是对审计报告 F-2 的修复：原先 `closeEvent` 只停两个主窗口
        定时器就 `app.quit()`，导致：

          * 插件持有的 `QThread`（AI 助手 Ollama 刷新/拉取）在运行中被
            析构 → Qt 打印 "QThread: Destroyed while thread is still
            running"，可能 `qFatal()`；
          * 插件热重载的 `QFileSystemWatcher` 未停止；
          * 每份文档的语言服务器子进程未被 kill（Windows 上会变孤儿）。

        所有步骤各自 try/except，任何失败都不阻断退出。
        """
        import time as _time

        # 1. 插件线程 + 面板线程
        try:
            pm = getattr(self, "plugin_manager", None)
            loader = getattr(pm, "loader", None) if pm is not None else None
            specs = getattr(loader, "specs", None) or {}
            for spec in specs.values():
                inst = getattr(spec, "instance", None)
                if inst is None:
                    continue
                # 面板的线程收尾
                panel = getattr(inst, "ollama_panel", None)
                if panel is not None:
                    try:
                        panel._stop_threads(timeout_ms)
                    except Exception:
                        pass
                # 插件自定义的线程收尾钩子（若实现）
                hook = getattr(inst, "shutdown_background", None)
                if callable(hook):
                    try:
                        hook()
                    except Exception:
                        pass
        except Exception:
            pass

        # 2. 插件热重载目录监控
        try:
            pm = getattr(self, "plugin_manager", None)
            loader = getattr(pm, "loader", None) if pm is not None else None
            if loader is not None and hasattr(loader, "stop_watching"):
                loader.stop_watching()
        except Exception:
            pass

        # 3. 各标签的编辑器资源（停 LSP 子进程、停草稿定时器、摘文件监听）
        #    注意：这里不弹"未保存"对话框 —— closeEvent 已经在前面问过了。
        try:
            tabs = getattr(self, "tabs", None)
            if tabs is not None and hasattr(tabs, "count"):
                for i in range(tabs.count()):
                    try:
                        widget = tabs.widget(i)
                        proxy = getattr(widget, "proxy", None)
                        if proxy is not None and hasattr(proxy, "close"):
                            proxy.close()
                    except Exception:
                        pass
        except Exception:
            pass

        # 4. 给事件循环一点时间处理 deleteLater（避免悬空对象告警）
        try:
            app = QApplication.instance()
            if app is not None:
                deadline = _time.time() + (timeout_ms / 1000.0)
                while _time.time() < deadline:
                    app.processEvents()
                    _time.sleep(0.01)
                    break
        except Exception:
            pass

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出窗口信息"""
        lines = [f"{APP_NAME} v{APP_VERSION}", "=" * 60]
        lines.append(f"标签数: {self.tabs.count()}")
        lines.append(f"当前标签: {self.tabs.currentIndex()}")
        lines.append(f"全屏: {self._fullscreen_mode}")
        lines.append(f"无干扰: {self._distraction_free}")
        lines.append(f"插件数: {len(self.plugins)}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<MainWindow tabs={self.tabs.count()} current={self.tabs.currentIndex()}>"
