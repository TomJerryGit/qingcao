#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
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
from ui.mixins.edit_ops_mixin import EditOpsMixin
from ui.mixins.file_ops_mixin import FileOpsMixin
from ui.mixins.status_bar_mixin import StatusBarMixin


class MainWindow(FileOpsMixin, EditOpsMixin, StatusBarMixin, QMainWindow):
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
            self.macro = MacroRecorder()
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
        self._build_menus()
        self._build_toolbar()
        self._build_docks()
        self._build_status_bar()
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
            if hasattr(self.welcome, 'new_file_requested'):
                self.welcome.new_file_requested.connect(self._new_file)
            elif hasattr(self.welcome, 'new_file'):
                self.welcome.new_file.connect(self._new_file)

            if hasattr(self.welcome, 'open_file_requested'):
                self.welcome.open_file_requested.connect(self._open_file)
            elif hasattr(self.welcome, 'open_file'):
                self.welcome.open_file.connect(self._open_file)

            if hasattr(self.welcome, 'open_folder_requested'):
                self.welcome.open_folder_requested.connect(self._open_folder)

            if hasattr(self.welcome, 'open_recent_file'):
                self.welcome.open_recent_file.connect(self._open_recent_file)

            if hasattr(self.welcome, 'open_recent_project'):
                self.welcome.open_recent_project.connect(self._open_recent_project)

            if hasattr(self.welcome, 'open_plugin_store'):
                self.welcome.open_plugin_store.connect(self._show_plugin_store)

            if hasattr(self.welcome, 'open_command_palette'):
                self.welcome.open_command_palette.connect(self._show_command_palette)

            self.central_stack.addWidget(self.welcome)
        except Exception as e:
            print(f"[MainWindow] WelcomeWidget 加载失败: {e}")
            self.welcome = None

        # 默认显示欢迎页
        if self.tabs.count() == 0:
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
            return w.proxy if w and hasattr(w, 'proxy') else None

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

    # ========================================================
    # 菜单栏
    # ========================================================
    def _build_menus(self):
        """构建菜单栏"""
        menubar = self.menuBar()

        # ============ 文件菜单 ============
        self.file_menu = menubar.addMenu("文件(&F)")

        self._add_action(self.file_menu, "📄 新建(&N)", "Ctrl+N",
                          self._new_file)
        self._add_action(self.file_menu, "📂 打开(&O)", "Ctrl+O",
                          self._open_file)
        self._add_action(self.file_menu, "📁 打开文件夹", None,
                          self._open_folder)
        self.file_menu.addSeparator()
        self._add_action(self.file_menu, "💾 保存(&S)", "Ctrl+S",
                          self._save_file)
        self._add_action(self.file_menu, "💾 另存为(&A)", "Ctrl+Shift+S",
                          self._save_file_as)
        self._add_action(self.file_menu, "💾 全部保存", "Ctrl+Alt+S",
                          self._save_all)
        self.file_menu.addSeparator()
        self._add_action(self.file_menu, "❌ 关闭标签", "Ctrl+W",
                          self._close_current_tab)
        self._add_action(self.file_menu, "❌ 关闭所有标签", "Ctrl+Shift+W",
                          self._close_all_tabs)
        self._add_action(self.file_menu, "↩ 恢复关闭的标签", "Ctrl+Shift+T",
                          self._restore_closed_tab)
        self.file_menu.addSeparator()
        self._add_action(self.file_menu, "🚪 退出(&X)", "Ctrl+Q",
                          self.close)

        # ============ 编辑菜单 ============
        self.edit_menu = menubar.addMenu("编辑(&E)")

        self._add_action(self.edit_menu, "↩ 撤销(&U)", "Ctrl+Z", self._undo)
        self._add_action(self.edit_menu, "↪ 重做(&R)", "Ctrl+Y", self._redo)
        self.edit_menu.addSeparator()
        self._add_action(self.edit_menu, "✂ 剪切(&T)", "Ctrl+X", self._cut)
        self._add_action(self.edit_menu, "📋 复制(&C)", "Ctrl+C", self._copy)
        self._add_action(self.edit_menu, "📋 粘贴(&P)", "Ctrl+V", self._paste)
        # P8-3: "粘贴为纯文本"。
        #   历史沿革：Ctrl+Alt+V 在 Windows 上被系统解释为 AltGr+V 而
        #   收不到；改到 Ctrl+Shift+V 后又与"Vim 模式"开关冲突，导致
        #   该功能在 Qt 的 ambiguous shortcut 下**完全失效**。
        #   现改绑 Ctrl+Alt+Shift+V（已穷举本文件所有 setShortcut /
        #   register_shortcut 调用确认无重复）。
        self._add_action(self.edit_menu, "📋 粘贴为纯文本", "Ctrl+Alt+Shift+V",
                          self._paste_plain)
        self._add_action(self.edit_menu, "全选(&A)", "Ctrl+A",
                          self._select_all)
        self.edit_menu.addSeparator()
        self._add_action(self.edit_menu, "🔍 查找(&F)", "Ctrl+F",
                          self._show_search)
        self._add_action(self.edit_menu, "🔎 全局搜索", "Ctrl+Shift+F",
                          self._show_global_search)
        self.edit_menu.addSeparator()
        self._add_action(self.edit_menu, "📍 跳转到行", "Ctrl+G",
                          self._goto_line_dialog)
        self._add_action(self.edit_menu, "💬 注释切换", "Ctrl+/",
                          self._toggle_comment)
        self._add_action(self.edit_menu, "🧮 计算表达式", "Ctrl+Shift+E",
                          self._eval_expression)
        # P8-2: F5 从"插入日期时间"改为"运行当前文件"（主流 IDE 语义）。
        #   日期时间改绑 Ctrl+Alt+D，见下面的编辑菜单。
        #   运行入口见 _run_current_file()：调试插件未激活时给出**明确
        #   提示**，不再静默失败。
        self._add_action(self.edit_menu, "📅 插入日期时间", "Ctrl+Alt+D",
                          self._insert_datetime)
        self.edit_menu.addSeparator()
        self._add_action(self.edit_menu, "📋 复制整行", "Ctrl+Shift+D",
                          self._duplicate_line)
        self._add_action(self.edit_menu, "⬆ 上移行", "Ctrl+Shift+Up",
                          self._move_line_up)
        self._add_action(self.edit_menu, "⬇ 下移行", "Ctrl+Shift+Down",
                          self._move_line_down)
        self._add_action(self.edit_menu, "🔷 选中下一个相同项", "Ctrl+D",
                          self._select_next_occurrence)
        self.edit_menu.addSeparator()
        self._add_action(self.edit_menu, "🔠 转为大写", None, self._to_upper)
        self._add_action(self.edit_menu, "🔡 转为小写", None, self._to_lower)

        # ============ 视图菜单 ============
        self.view_menu = menubar.addMenu("视图(&V)")

        # P8-1: 列模式 —— 菜单项与工具栏按钮**共用同一个 QAction**。
        #   修复前"视图 → 列模式"（_add_action）与工具栏
        #   column_mode_action 各自 setShortcut("Alt+C")，Qt 判定为
        #   ambiguous shortcut overload，按 Alt+C 两个都不触发。
        #   该 QAction 在 _build_menus 中创建（早于 _build_toolbar），
        #   工具栏在 _build_toolbar 里直接 addAction 复用。
        self.column_mode_action = QAction("▦ 列模式", self)
        self.column_mode_action.setCheckable(True)
        self.column_mode_action.setShortcut(QKeySequence("Alt+C"))
        self.column_mode_action.toggled.connect(self._toggle_column_mode)
        self.view_menu.addAction(self.column_mode_action)
        self._register_action_shortcut(self.column_mode_action)
        self.view_menu.addSeparator()
        self._add_action(self.view_menu, "🖥 无干扰模式", "F11",
                          self.toggle_distraction_free)
        self._add_action(self.view_menu, "⛶ 全屏", "Shift+F11",
                          self.toggle_fullscreen)
        self.view_menu.addSeparator()
        self._add_action(self.view_menu, "🔍 放大字体", "Ctrl+=",
                          self._zoom_in)
        self._add_action(self.view_menu, "🔍 缩小字体", "Ctrl+-",
                          self._zoom_out)
        self._add_action(self.view_menu, "🔍 重置字体", "Ctrl+0",
                          self._zoom_reset)
        self.view_menu.addSeparator()

        # 面板切换子菜单
        self.panel_menu = self.view_menu.addMenu("📊 面板")
        self._build_panel_menu()

        # --- 主题子菜单（完整版）---
        self.theme_menu = self.view_menu.addMenu("🎨 主题")
        self._build_full_theme_menu()

        # ============ 工具菜单 ============
        self.tools_menu = menubar.addMenu("工具(&T)")

        # P8-2: F5 = 运行当前文件（原来的"插入日期时间"已改绑 Ctrl+Alt+D）
        self._add_action(self.tools_menu, "▶ 运行当前文件", "F5",
                          self._run_current_file)
        # P6: F12 = 转到定义，把 LspClient.request_definition 接进生产路径
        self._add_action(self.tools_menu, "🔎 转到定义", "F12",
                          self._goto_definition)
        self.tools_menu.addSeparator()

        self._add_action(self.tools_menu, "⌨ 命令面板", "Ctrl+Shift+P",
                          self._show_command_palette)
        self._add_action(self.tools_menu, "📂 文件切换", "Ctrl+P",
                          self._show_file_palette)
        # P2-4: 符号跳转改为 Ctrl+Alt+R，避免与"重新加载"Ctrl+R 冲突
        self._add_action(self.tools_menu, "🔣 符号跳转", "Ctrl+Alt+R",
                          self._show_symbol_palette)
        self.tools_menu.addSeparator()
        self._add_action(self.tools_menu, "🐍 Python 控制台", "Ctrl+`",
                          self._toggle_console)
        self.tools_menu.addSeparator()
        self._add_action(self.tools_menu, "⏺ 录制/停止宏", "Ctrl+Shift+R",
                          self._toggle_macro)
        self._add_action(self.tools_menu, "▶ 回放宏", "Ctrl+Shift+M",
                          self._play_macro)
        self.tools_menu.addSeparator()
        self._add_action(self.tools_menu, "🧩 插件市场", None,
                          self._show_plugin_store)
        self._add_action(self.tools_menu, "🔌 插件管理", None,
                          self._show_plugins_panel)
        self._add_action(self.tools_menu, "⌨ 快捷键编辑器", None,
                          self._show_keymap_editor)
        self.tools_menu.addSeparator()
        self._add_action(self.tools_menu, "📊 性能监控", None,
                          self._show_perf_monitor)
        # C: Vim 模式菜单开关
        self.vim_mode_action = QAction("Vim 模式", self)
        self.vim_mode_action.setCheckable(True)
        # B: Ctrl+Alt+V 在 Windows 被解释为 AltGr+V，改为 Ctrl+Shift+V
        self.vim_mode_action.setShortcut(QKeySequence("Ctrl+Shift+V"))
        self.vim_mode_action.toggled.connect(self._toggle_vim_mode)
        self.tools_menu.addAction(self.vim_mode_action)
        self._register_action_shortcut(self.vim_mode_action)

        # P6: LSP 总开关（可勾选，**默认关闭** —— 需要用户本机装有
        # 语言服务器；没有服务器时会在状态栏给出可操作的安装提示）。
        # 不分配默认快捷键，避免与用户自定义/插件注册的键冲突。
        self.lsp_action = QAction("启用/停用 LSP（智能补全）", self)
        self.lsp_action.setCheckable(True)
        self.lsp_action.setChecked(self._lsp_pref_enabled())
        self.lsp_action.toggled.connect(self._toggle_lsp)
        self.tools_menu.addAction(self.lsp_action)
        # --- 首选项入口 ---
        self.tools_menu.addSeparator()
        self._add_action(self.tools_menu, "⚙ 首选项...", "Ctrl+,",
                          self._show_preferences)

        self.tools_menu.addSeparator()
        self._add_action(self.tools_menu, "📤 导出配置", None,
                          self._export_config)
        self._add_action(self.tools_menu, "📥 导入配置", None,
                          self._import_config)

        # ============ 帮助菜单 ============
        self.help_menu = menubar.addMenu("帮助(&H)")

        self._add_action(self.help_menu, "⌨ 快捷键参考", None,
                          self._show_shortcuts)
        # P2-C4: manual 参数
        self._add_action(
            self.help_menu, "💡 每日技巧", None,
            lambda checked=False: self._show_daily_tip(manual=True)
        )
        self.help_menu.addSeparator()
        self._add_action(self.help_menu, "📖 在线文档", None,
                          self._show_online_docs)
        self._add_action(self.help_menu, "🐙 GitHub", None,
                          self._show_github)
        self.help_menu.addSeparator()
        self._add_action(self.help_menu, "ℹ 关于", None, self._about)

    def _build_panel_menu(self):
        """构建面板切换子菜单"""
        panels = [
            ("大纲", "panel.outline", self._toggle_outline),
            ("大纲（增强）", "panel.outline_enhanced", self._toggle_outline_enhanced),
            ("目录树", "panel.directory", self._toggle_directory),
            ("Minimap", "panel.minimap", self._toggle_minimap),
            ("全局搜索", "panel.global_search", self._toggle_global_search),
            ("Python 控制台", "panel.console", self._toggle_console),
            ("插件", "panel.plugins", self._toggle_plugins_panel),
            ("性能监控", "panel.perf_monitor", self._toggle_perf_monitor),
        ]

        for name, action_name, slot in panels:
            action = QAction(name, self)
            action.setCheckable(True)
            action.toggled.connect(slot)
            self.panel_menu.addAction(action)

    def _build_full_theme_menu(self):
        """构建完整的主题子菜单"""
        # 跟随系统
        self._add_action(
            self.theme_menu, "跟随系统", None,
            lambda: self._apply_theme_by_name("__system__")
        )

        self.theme_menu.addSeparator()

        # 动态扫描 themes/
        themes_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "themes"
        )
        if os.path.isdir(themes_dir):
            for f in sorted(os.listdir(themes_dir)):
                if f.endswith('.json'):
                    name = os.path.splitext(f)[0]
                    # B(主题): 菜单显示 display_name
                    # 读取 display_name 用于展示，name 保留给回调用
                    display = name
                    try:
                        import json as _json
                        with open(
                            os.path.join(themes_dir, f), encoding='utf-8'
                        ) as _fp:
                            _data = _json.load(_fp)
                        display = _data.get('display_name', name)
                    except Exception:
                        pass
                    self._add_action(
                        self.theme_menu, display, None,
                        lambda checked=False, n=name:
                        self._apply_theme_by_name(n)
                    )

        self.theme_menu.addSeparator()

        # 编辑 / 市场 / 导入 / 导出 / 删除
        self._add_action(
            self.theme_menu, "📝 编辑当前主题...", None,
            self._show_theme_editor
        )
        self._add_action(
            self.theme_menu, "🎨 主题市场...", None,
            self._show_theme_market
        )
        self.theme_menu.addSeparator()
        self._add_action(
            self.theme_menu, "📥 导入主题包...", None,
            self._import_theme_pack
        )
        self._add_action(
            self.theme_menu, "📤 导出当前主题...", None,
            self._export_theme_pack
        )
        self.theme_menu.addSeparator()
        self._add_action(
            self.theme_menu, "📁 打开主题目录", None,
            self._open_theme_dir
        )

    def _apply_theme_by_name(self, name: str):
        """按名称应用主题"""
        try:
            from infrastructure.theme_loader import ThemeLoader
            loader = ThemeLoader()

            if name == "__system__":
                loader.apply_system_theme(
                    QApplication.instance(),
                    self.tabs.currentWidget()
                )
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
                    loader.apply_qss(_app, theme)
                    # 有些 QSS 选择器（QMainWindow 等）需要重设
                    _app.setStyleSheet(_app.styleSheet())
            except Exception as _e:
                print(f"[Theme] apply_qss 失败: {_e}")
                if theme.qss:
                    self.setStyleSheet(theme.qss)

            # v3.0: 通知所有面板刷新样式
            loader.notify_widgets(self, theme)

            # B: 遍历所有顶层窗口（含独立对话框）
            # notify_widgets 只处理 self.findChildren，独立打开的
            # 对话框（AI 配置、Git 提交、快捷键编辑器等）不在其中
            try:
                from PyQt5.QtWidgets import QApplication
                for w in QApplication.topLevelWidgets():
                    if w is self:
                        continue
                    fn = getattr(w, 'refresh_theme', None)
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
                self, "导入主题包", "",
                "主题包 (*.zip);;所有文件 (*.*)"
            )
            if not path:
                return

            themes_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "themes"
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
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "themes"
            )
            source = os.path.join(themes_dir, f"{theme_name}.json")
            if not os.path.exists(source):
                self._show_error("导出失败", f"主题文件不存在: {source}")
                return

            path, _ = QFileDialog.getSaveFileName(
                self, "导出主题包",
                f"{theme_name}.zip",
                "主题包 (*.zip)"
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
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "themes"
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

    def _add_action(self, menu: QMenu, text: str, shortcut: Optional[str],
                     slot) -> QAction:
        """
        添加菜单项。

        参数:
            menu: 目标菜单
            text: 显示文本
            shortcut: 快捷键字符串（可选）
            slot: 槽函数

        返回:
            创建的 QAction
        """
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
            # P8-5: 运行时重复检测（不抛异常，避免打断启动）
            self._register_action_shortcut(action)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _register_action_shortcut(self, action: QAction):
        """P8-5: 记录 QAction 的快捷键并检测重复绑定。

        `_add_action()` 直接调用 `QAction.setShortcut()`，绕过了
        `app/actions.py` 的冲突检测；此前的 Alt+C 重复绑定就是这样
        悄悄产生的（Qt 判定 ambiguous shortcut，按键完全无响应）。

        这里维护 `self._shortcut_owners: {快捷键字符串: QAction}`：
        同一个非空快捷键被**另一个** QAction 再次绑定时，用
        `logging.warning` 记录并保留首个绑定。刻意不抛异常 ——
        启动期间不能因为一个冲突就整体失败。
        """
        try:
            seq = action.shortcut()
            if seq is None or seq.isEmpty():
                return
            key = seq.toString()
            if not key:
                return

            owners = getattr(self, "_shortcut_owners", None)
            if owners is None:
                owners = {}
                self._shortcut_owners = owners

            previous = owners.get(key)
            if previous is not None and previous is not action:
                logger.warning(
                    "快捷键冲突: %s 已绑定到「%s」，现又被「%s」绑定；"
                    "后者的快捷键已失效（Qt ambiguous shortcut）",
                    key, previous.text(), action.text(),
                )
                return
            owners[key] = action
        except Exception as e:
            logger.warning("快捷键重复检测失败: %s", e)

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
            for plugin in (self.plugins or []):
                runner = getattr(plugin, "run_current", None)
                if callable(runner):
                    try:
                        runner()
                        return
                    except Exception as e:
                        logger.error("插件运行当前文件失败: %s", e)
                        self.status_bar.showMessage(
                            f"运行失败: {e}", 5000
                        )
                        return

            # 2) 没有调试插件：给出可操作的提示（不静默失败）
            self.status_bar.showMessage(
                "未启用调试插件，无法运行当前文件；"
                "请启用「python_debugger」等调试插件（工具 → 插件管理）。"
                f"（{os.path.basename(filepath)}）",
                6000,
            )
            logger.warning(
                "运行当前文件：没有可用的调试插件（filepath=%s）", filepath
            )
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
                self.status_bar.showMessage(
                    "转到定义不可用（详见状态栏提示 / 日志）", 5000
                )
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

    def _on_definition_requested(self, filepath: str, line: int,
                                 character: int):
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
                self.status_bar.showMessage(
                    f"定义位于: {filepath}:{line + 1}", 6000
                )
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
                self.status_bar.showMessage(
                    "没有活动的编辑器，无法启用 LSP", 4000
                )
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
    # 工具栏
    # ========================================================
    def _build_toolbar(self):
        """构建工具栏"""
        toolbar = QToolBar("主工具栏")
        toolbar.setObjectName("MainToolBar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(Qt.TopToolBarArea, toolbar)
        self.toolbar = toolbar

        # 文件操作
        toolbar.addAction(self._toolbar_action("新建", self._new_file))
        toolbar.addAction(self._toolbar_action("打开", self._open_file))
        toolbar.addAction(self._toolbar_action("保存", self._save_file))
        toolbar.addSeparator()

        # 编辑操作
        toolbar.addAction(self._toolbar_action("撤销", self._undo))
        toolbar.addAction(self._toolbar_action("重做", self._redo))
        toolbar.addSeparator()

        # 查找
        toolbar.addAction(self._toolbar_action("查找", self._show_search))
        toolbar.addAction(self._toolbar_action("全局搜索",
                                                self._show_global_search))
        toolbar.addSeparator()

        # 列模式（P8-1: 与"视图 → 列模式"共用同一个 QAction。
        # 全窗口只保留**一处** Alt+C 绑定，避免 Qt 的
        # ambiguous shortcut overload 导致按键完全无响应。）
        if getattr(self, 'column_mode_action', None) is None:
            # 兜底：万一 _build_menus 未执行（只需工具栏的场景）
            self.column_mode_action = QAction("列模式", self)
            self.column_mode_action.setCheckable(True)
            self.column_mode_action.setShortcut(QKeySequence("Alt+C"))
            self.column_mode_action.toggled.connect(self._toggle_column_mode)
            self._register_action_shortcut(self.column_mode_action)
        toolbar.addAction(self.column_mode_action)

        # 命令面板
        toolbar.addAction(self._toolbar_action("命令面板",
                                                self._show_command_palette))

    def _toolbar_action(self, text: str, slot) -> QAction:
        """创建工具栏动作"""
        action = QAction(text, self)
        action.triggered.connect(slot)
        return action

    # ========================================================
    # 可停靠面板
    # ========================================================
    def _build_docks(self):
        """构建所有可停靠面板"""
        # 面板引用（初始为 None）
        self.outline = None
        self.outline_enhanced = None
        self.outline_enhanced_dock = None
        self.dir_tree = None
        self.dir_tree_dock = None
        self.minimap = None
        self.minimap_dock = None
        self.gsearch = None
        self.console = None
        self.search_bar = None
        self.plugins_panel = None
        self.perf_monitor = None

        # P1-3: 记录哪些面板已经构造过（惰性构造用）
        self._panels_built = set()

        # 设置角落
        self.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.TopRightCorner, Qt.RightDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.RightDockWidgetArea)

        # 构造"开箱即有"的常用面板。
        #
        # 必须在这里（而不是等用户点菜单）完成，原因有二：
        #   1. 会话恢复 `_restore_session` 在 200ms 后执行，它按
        #      `findChildren(QDockWidget)` 恢复可见性 —— 面板必须已存在；
        #   2. 会话**保存**会采集已存在的面板；若一个都没有，就会把
        #      用户布局覆盖成空（见 app/session.py 的 _capture_docks）。
        #
        # 注意：各构造器末尾保留了旧版的 `hide()`（面板默认不显示）。
        # 因此这里构造后需要**显式显示**，否则界面依旧是空的。
        for name in self._DEFAULT_PANELS:
            try:
                if self._ensure_panel(name):
                    self._show_panel(name)
            except Exception as e:
                print(f"[MainWindow] 默认面板 {name} 构造失败: {e}")

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
        'outline', 'outline_enhanced',
        'dir_tree', 'minimap', 'gsearch',
        'console', 'plugins_panel', 'perf_monitor', 'search_bar',
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
        'dir_tree',        # 左侧：项目目录树
        'gsearch',         # 底部：全局搜索
        'plugins_panel',   # 右侧：插件
        'perf_monitor',    # 底部：性能监控
    )

    def _show_panel(self, name: str) -> bool:
        """显示指定面板（按属性名，兼容"面板本身是 dock"与"面板包在 dock 里"两种形式）

        为什么要单独一个方法：各面板的封装形式不统一 ——
        `outline`/`gsearch`/`console`/`plugins_panel`/`perf_monitor`
        本身就是 QDockWidget，而 `dir_tree`/`minimap` 是
        `QDockWidget` 包住一个内容控件（`dir_tree_dock`/`minimap_dock`）。
        """
        target = getattr(self, name, None)
        if target is None:
            return False
        if name in ("dir_tree", "minimap"):
            target = getattr(self, name + "_dock", None) or target
        try:
            target.setVisible(True)
            # 折叠状态下 setVisible 不会真正展开，这里确保还原
            if hasattr(target, "show"):
                target.show()
            return True
        except Exception as e:
            print(f"[MainWindow] 显示面板 {name} 失败: {e}")
            return False

    def _ensure_panel(self, name: str) -> bool:
        """确保指定面板已构造。

        参数:
            name: 面板属性名（见 _LAZY_PANELS）

        返回:
            面板当前是否可用（构造失败或名称非法时为 False）
        """
        if name not in self._LAZY_PANELS:
            print(f"[MainWindow] 未知面板: {name}")
            return False
        # 已构造过（可能构造失败留下 None）
        if name in self._panels_built:
            return getattr(self, name, None) is not None

        self._panels_built.add(name)
        builder = getattr(self, f'_build_panel_{name}', None)
        if builder is None:
            return False
        try:
            builder()
        except Exception as e:
            print(f"[MainWindow] 面板 {name} 构造失败: {e}")
            setattr(self, name, None)
            return False
        return getattr(self, name, None) is not None

    def _build_panel_outline(self):
        """构造基础版大纲面板"""
        try:
            from ui.outline_panel import OutlinePanel
            self.outline = OutlinePanel(self)
            self.outline.setObjectName("OutlinePanel")
            self.outline.symbol_clicked.connect(self._on_symbol_clicked)
            self.addDockWidget(Qt.LeftDockWidgetArea, self.outline)
        except Exception as e:
            print(f"[MainWindow] OutlinePanel 加载失败: {e}")
            self.outline = None

    def _build_panel_outline_enhanced(self):
        """构造增强版大纲面板

        P3-8 重构后 outline_panel_enhanced.py 已合并到
        outline_panel.py，通过 OutlinePanel(enhanced=True) 启用
        增强功能（面包屑、类型筛选、排序切换、跟随光标、3 列树）。
        """
        try:
            from ui.outline_panel import OutlinePanel
            self.outline_enhanced = OutlinePanel(self, enhanced=True)
            self.outline_enhanced.setObjectName("OutlineEnhancedDock")
            self.outline_enhanced.symbol_clicked.connect(
                self._on_symbol_clicked
            )
            self.addDockWidget(
                Qt.LeftDockWidgetArea, self.outline_enhanced
            )
            # 默认隐藏（避免与基础版重叠）
            self.outline_enhanced.hide()
        except Exception as e:
            print(f"[MainWindow] 增强大纲加载失败: {e}")
            self.outline_enhanced = None

    def _build_panel_dir_tree(self):
        """构造目录树面板"""
        try:
            from ui.directory_tree import DirectoryTree
            self.dir_tree = DirectoryTree()
            self.dir_tree.file_double_clicked.connect(
                self._on_file_from_tree
            )
            self.dir_tree.file_opened.connect(self._on_file_from_tree)

            self.dir_tree_dock = QDockWidget("项目", self)
            self.dir_tree_dock.setObjectName("DirectoryTreeDock")
            self.dir_tree_dock.setWidget(self.dir_tree)
            self.addDockWidget(Qt.LeftDockWidgetArea, self.dir_tree_dock)
        except Exception as e:
            print(f"[MainWindow] DirectoryTree 加载失败: {e}")
            self.dir_tree = None
            self.dir_tree_dock = None

    def _build_panel_minimap(self):
        """构造 Minimap 面板（安全模式，失败不影响启动）"""
        try:
            from ui.minimap import Minimap
            self.minimap = Minimap()

            self.minimap_dock = QDockWidget("Minimap", self)
            self.minimap_dock.setObjectName("MinimapDock")
            self.minimap_dock.setWidget(self.minimap)
            self.minimap_dock.setMinimumWidth(80)
            self.minimap_dock.setMaximumWidth(200)
            self.addDockWidget(Qt.RightDockWidgetArea, self.minimap_dock)
        except Exception as e:
            print(f"[MainWindow] Minimap 加载失败: {e}")
            self.minimap = None
            self.minimap_dock = None

    def _build_panel_gsearch(self):
        """构造全局搜索面板"""
        try:
            from ui.global_search_panel import GlobalSearchPanel
            self.gsearch = GlobalSearchPanel(self)
            self.gsearch.setObjectName("GlobalSearchPanel")
            self.gsearch.match_activated.connect(
                self._on_search_match_activated
            )
            # P2-C5: 连接 replace_requested
            # 原实现只连 match_activated，"全部替换"按钮点了没反应。
            self.gsearch.replace_requested.connect(
                self._on_global_replace
            )
            self.addDockWidget(Qt.BottomDockWidgetArea, self.gsearch)
            self.gsearch.hide()
        except Exception as e:
            print(f"[MainWindow] GlobalSearchPanel 加载失败: {e}")
            self.gsearch = None

    def _build_panel_console(self):
        """构造 Python 控制台面板"""
        try:
            from ui.python_console import PythonConsole
            self.console = PythonConsole(self)
            self.console.setObjectName("PythonConsole")
            self.addDockWidget(Qt.BottomDockWidgetArea, self.console)
            self.console.hide()
        except Exception as e:
            print(f"[MainWindow] PythonConsole 加载失败: {e}")
            self.console = None

    def _build_panel_plugins_panel(self):
        """构造插件面板"""
        try:
            from ui.plugins_panel import PluginsPanel
            # plugin_manager 稍后才创建，先创建面板，之后设置
            self.plugins_panel = PluginsPanel(
                main_window=self,
                plugin_manager=None,
            )
            self.plugins_panel.setObjectName("PluginsPanel")
            self.addDockWidget(
                Qt.RightDockWidgetArea, self.plugins_panel
            )
            self.plugins_panel.hide()
        except Exception as e:
            print(f"[MainWindow] PluginsPanel 加载失败: {e}")
            self.plugins_panel = None

    def _build_panel_perf_monitor(self):
        """构造性能监控面板"""
        try:
            from ui.perf_monitor import PerfMonitor
            self.perf_monitor = PerfMonitor(self)
            self.perf_monitor.setObjectName("PerfMonitor")
            self.addDockWidget(
                Qt.BottomDockWidgetArea, self.perf_monitor
            )
            self.perf_monitor.hide()
        except Exception as e:
            print(f"[MainWindow] PerfMonitor 加载失败: {e}")
            self.perf_monitor = None

    def _build_panel_search_bar(self):
        """构造搜索栏"""
        try:
            from ui.panels import SearchBar
            self.search_bar = SearchBar(self)
            self.search_bar.setObjectName("SearchBar")
            self.addToolBar(Qt.BottomToolBarArea, self.search_bar)
            self.search_bar.hide()
        except Exception as e:
            print(f"[MainWindow] SearchBar 加载失败: {e}")
            self.search_bar = None

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

    # ========================================================
    # 查找
    # ========================================================
    def _show_search(self):
        """显示搜索栏"""
        try:
            # P1-3: 惰性构造
            self._ensure_panel('search_bar')
            if self.search_bar:
                self.search_bar.show()
                if hasattr(self.search_bar, 'show_and_focus'):
                    self.search_bar.show_and_focus()
        except Exception as e:
            print(f"[MainWindow] 显示搜索栏失败: {e}")

    def _show_global_search(self):
        """显示全局搜索"""
        try:
            # P1-3: 惰性构造
            self._ensure_panel('gsearch')
            if self.gsearch:
                self.gsearch.show()
                if hasattr(self.gsearch, 'focus_search'):
                    self.gsearch.focus_search()
        except Exception as e:
            print(f"[MainWindow] 显示全局搜索失败: {e}")

    def _goto_line_dialog(self):
        """跳转到行（对话框形式，P3-2 由 _show_line_palette 改名）"""
        try:
            proxy = self.tabs.current_proxy()
            if not proxy or not proxy.sc:
                return

            total = proxy.sc.SendScintilla(
                proxy.sc.SCI_GETLINECOUNT
            )
            if total <= 0:
                total = 1
            line, ok = QInputDialog.getInt(
                self, "跳转到行", "行号:",
                1, 1, total
            )
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
            if hasattr(self, 'column_mode_action'):
                # 修复 P0-C4: 忽略 triggered 的 checked 参数，
                # 始终基于工具栏 action 的当前状态翻转
                enabled = not self.column_mode_action.isChecked()
                self.column_mode_action.blockSignals(True)
                self.column_mode_action.setChecked(enabled)
                self.column_mode_action.blockSignals(False)
            else:
                # 无工具栏按钮时，退回到 checked 参数
                enabled = not (checked if isinstance(checked, bool)
                               else False)

            proxy = self.tabs.current_proxy()
            if proxy and hasattr(proxy, 'set_column_mode'):
                proxy.set_column_mode(enabled)

            self.status_bar.showMessage(
                "列模式" if enabled else "流模式", 2000
            )
        except Exception as e:
            print(f"[MainWindow] 切换列模式失败: {e}")

    def toggle_distraction_free(self):
        """切换无干扰模式"""
        if self._distraction_free:
            self._exit_distraction_free()
        else:
            self._enter_distraction_free()

    def _enter_distraction_free(self):
        """进入无干扰模式"""
        try:
            self._distraction_free = True
            self._hidden_widgets = []

            # 隐藏菜单栏
            self.menuBar().hide()

            # 隐藏工具栏
            for tb in self.findChildren(QToolBar):
                if tb.isVisible():
                    tb.hide()
                    self._hidden_widgets.append(tb)

            # 隐藏停靠面板
            for dock in self.findChildren(QDockWidget):
                if dock.isVisible():
                    dock.hide()
                    self._hidden_widgets.append(dock)

            # 隐藏状态栏
            self.status_bar.hide()

            self.status_bar.showMessage("无干扰模式（按 F11 退出）", 3000)
        except Exception as e:
            print(f"[MainWindow] 进入无干扰失败: {e}")

    def _exit_distraction_free(self):
        """退出无干扰模式"""
        try:
            self._distraction_free = False

            # 恢复菜单栏
            self.menuBar().show()

            # 恢复隐藏的组件
            for widget in self._hidden_widgets:
                try:
                    widget.show()
                except Exception:
                    pass

            self._hidden_widgets.clear()

            # 恢复状态栏
            self.status_bar.show()
        except Exception as e:
            print(f"[MainWindow] 退出无干扰失败: {e}")

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
    # 面板切换
    # ========================================================
    def _toggle_outline(self, checked):
        """切换大纲面板（基础版）"""
        if self._ensure_panel('outline') and self.outline:
            self.outline.setVisible(checked)

    def _toggle_outline_enhanced(self, checked):
        """切换增强版大纲面板"""
        if self._ensure_panel('outline_enhanced') and self.outline_enhanced:
            self.outline_enhanced.setVisible(checked)

    def _toggle_directory(self, checked):
        """切换目录树面板"""
        if self._ensure_panel('dir_tree') and self.dir_tree_dock:
            self.dir_tree_dock.setVisible(checked)

    def _toggle_minimap(self, checked):
        """切换 Minimap"""
        if self._ensure_panel('minimap') and self.minimap_dock:
            self.minimap_dock.setVisible(checked)

    def _toggle_global_search(self, checked):
        """切换全局搜索"""
        if self._ensure_panel('gsearch') and self.gsearch:
            self.gsearch.setVisible(checked)

    def _toggle_console(self):
        """切换控制台"""
        try:
            if self._ensure_panel('console') and self.console:
                self.console.setVisible(not self.console.isVisible())
        except Exception as e:
            print(f"[MainWindow] 控制台切换失败: {e}")

    def _toggle_plugins_panel(self, checked):
        """切换插件面板"""
        if self._ensure_panel('plugins_panel') and self.plugins_panel:
            self.plugins_panel.setVisible(checked)

    def _toggle_perf_monitor(self, checked):
        """切换性能监控"""
        if self._ensure_panel('perf_monitor') and self.perf_monitor:
            self.perf_monitor.setVisible(checked)

    # ========================================================
    # 工具
    # ========================================================
    def _show_command_palette(self):
        """显示命令面板"""
        try:
            from ui.command_palette import create_command_palette
            palette = create_command_palette(
                self.act_mgr, self,
                tab_mgr=self.tabs,
                outline=self.outline
            )
            if hasattr(palette, 'center_on_parent'):
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
            if hasattr(palette, 'center_on_parent'):
                palette.center_on_parent()
            palette.exec_()
        except Exception as e:
            print(f"[MainWindow] 文件面板失败: {e}")

    def _show_symbol_palette(self):
        """显示符号跳转面板"""
        try:
            from ui.command_palette import create_symbol_palette
            palette = create_symbol_palette(
                self.act_mgr, self.tabs, self.outline, self
            )
            if hasattr(palette, 'center_on_parent'):
                palette.center_on_parent()
            palette.exec_()
        except Exception as e:
            print(f"[MainWindow] 符号面板失败: {e}")

    def _toggle_macro(self):
        """切换宏录制"""
        if not self.macro:
            self.status_bar.showMessage("宏功能不可用", 2000)
            return
        try:
            # 兼容不同版本：使用 recording 属性或 is_recording 方法
            is_recording = False
            if hasattr(self.macro, 'recording'):
                is_recording = bool(self.macro.recording)
            elif hasattr(self.macro, 'is_recording'):
                is_recording = bool(self.macro.is_recording())

            if is_recording:
                self.macro.stop()
                self.rec_label.hide()
                self.status_bar.showMessage("宏录制已停止", 2000)
            else:
                self.macro.start()
                self.rec_label.setText("● REC")
                self.rec_label.show()
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
            if hasattr(self.macro, 'has_commands'):
                has_commands = self.macro.has_commands()
            elif hasattr(self.macro, 'commands'):
                has_commands = bool(self.macro.commands)

            if not has_commands:
                self.status_bar.showMessage("没有可回放的宏", 2000)
                return

            self.macro.replay(proxy, repeat=1)
            self.status_bar.showMessage("宏回放完成", 2000)
        except Exception as e:
            self._show_error("宏回放失败", str(e))

    def _show_plugin_store(self):
        """显示插件市场"""
        try:
            from ui.plugin_store import PluginStoreDialog
            dlg = PluginStoreDialog(self)
            dlg.exec_()
        except Exception as e:
            self._show_error("插件市场失败", str(e))

    def _show_plugins_panel(self):
        """显示插件管理面板"""
        try:
            # P1-3: 惰性构造
            self._ensure_panel('plugins_panel')
            if self.plugins_panel:
                self.plugins_panel.show()
                self.plugins_panel.raise_()
                if hasattr(self.plugins_panel, 'refresh'):
                    self.plugins_panel.refresh()
        except Exception as e:
            self._show_error("插件面板失败", str(e))

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
            self._ensure_panel('perf_monitor')
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
                vim = getattr(editor, '_vim_mode', None)
                if vim is None:
                    vim = VimMode(editor)
                    editor._vim_mode = vim

                # 首次创建时连接信号（状态栏显示模式）
                if not getattr(vim, '_signal_connected', False):
                    try:
                        vim.status_message.connect(
                            lambda msg:
                            self.status_bar.showMessage(msg, 2000)
                            if msg else None
                        )
                        vim.state_changed.connect(
                            lambda st:
                            self.status_bar.showMessage(
                                f"Vim: {st}", 1500
                            )
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
                vim = getattr(editor, '_vim_mode', None)
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
            QDesktopServices.openUrl(
                QUrl("https://qingcao-editor.github.io/docs")
            )
        except Exception:
            pass

    def _show_github(self):
        """打开 GitHub"""
        try:
            QDesktopServices.openUrl(
                QUrl("https://github.com/qingcao-editor/qingcao")
            )
        except Exception:
            pass

    def _about(self):
        """关于对话框"""
        QMessageBox.about(
            self, "关于青草编辑器",
            f"<h2>{APP_NAME} v{APP_VERSION}</h2>"
            "<p>轻量 · 极速 · 可扩展</p>"
            "<p>开发者：hedongwei</p>"
            "<p>联系：1265338136@qq.com</p>"
            "<p><i>青草枯荣，野火重生。</i></p>"
        )

    # ========================================================
    # 状态栏更新
    # ========================================================
    def _on_status_message(self, event):
        """状态消息事件"""
        try:
            msg = getattr(event, 'message', str(event))
            timeout = getattr(event, 'timeout', 3000)
            self.status_bar.showMessage(msg, timeout)
        except Exception:
            pass

    def _on_cursor_moved(self, event):
        """光标移动"""
        try:
            line = getattr(event, 'line', 1)
            col = getattr(event, 'col', 0)
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
                    if hasattr(self.outline, 'update_symbols'):
                        self.outline.update_symbols(editor)
                    elif hasattr(self.outline, 'schedule_update'):
                        self.outline.schedule_update()
                except Exception as e:
                    print(f"[MainWindow] 大纲更新失败: {e}")

            # 大纲（增强版）
            if self.outline_enhanced:
                try:
                    if hasattr(self.outline_enhanced, 'update_symbols'):
                        self.outline_enhanced.update_symbols(editor)
                    elif hasattr(self.outline_enhanced, 'schedule_update'):
                        self.outline_enhanced.schedule_update()
                except Exception as e:
                    print(f"[MainWindow] 增强大纲更新失败: {e}")

            # Minimap（安全调用）
            if self.minimap:
                try:
                    if hasattr(self.minimap, 'set_editor'):
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

        except Exception as e:
            print(f"[MainWindow] 标签切换失败: {e}")

    def _sync_column_mode_state(self):
        """同步工具栏列模式按钮状态（P2-5）"""
        try:
            if not hasattr(self, 'column_mode_action'):
                return

            proxy = self.tabs.current_proxy()
            if not proxy or not hasattr(proxy, 'is_column_mode'):
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

            if self.minimap and hasattr(self.minimap, 'set_editor'):
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

    def _on_search_match_activated(self, filepath: str, start: int,
                                     end: int, line: int, col: int):
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

    def _on_global_replace(self, pattern: str, replace_text: str,
                            file_results: dict):
        """P2-C5: 全局搜索 → 全部替换。

        参数:
            pattern: 搜索模式
            replace_text: 替换文本
            file_results: {filepath: [SearchMatch, ...]}
        """
        if not pattern or not file_results:
            return

        try:
            from core.content_provider import LocalFileProvider
            from core.search import ReplaceEngine, SearchEngine, SearchOptions

            total = 0
            abs_paths = set()

            for filepath in file_results:
                abs_paths.add(os.path.abspath(filepath))
                try:
                    provider = LocalFileProvider()
                    provider.open(filepath)
                    try:
                        options = SearchOptions(pattern=pattern)
                        engine = SearchEngine(provider, options)
                        result = engine.search()
                        if result.is_empty:
                            continue

                        replace_engine = ReplaceEngine(provider)
                        n = replace_engine.replace_all(
                            result, replace_text,
                            is_regex=options.is_regex,
                            pattern=pattern,
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
                if not hasattr(w, 'proxy') or not w.proxy:
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
                            w.proxy.sc.setText(
                                w.proxy.document.get_text()
                            )
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

            count = self.session.restore(
                self.tabs, self, confirm_recovery=False
            )

            if count and count > 0:
                self.central_stack.setCurrentIndex(0)
                self.status_bar.showMessage(
                    f"已恢复 {count} 个文件", 3000
                )
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

    def _load_plugins(self):
        """
        加载插件。

        修复说明:
            - 使用 api_factory 函数为每个插件创建独立的 PluginAPI 实例。
              之前直接把 PluginAPI 实例传给 load_all 会导致
              "PluginAPI object is not callable"。
            - P2-1: self.api 由 _create_main_api 创建（全权限），
              不再取第一个插件的 API，避免权限受限。
        """
        # P2-1: 先创建独立的全权限主 API
        try:
            self.api = self._create_main_api()
            if self.api is not None:
                print("[MainWindow] 已创建主 API（全权限）")
        except Exception as e:
            print(f"[MainWindow] 创建主 API 异常: {e}")
            self.api = None

        try:
            from app.plugins import PluginAPI
            from infrastructure.plugin_loader import (
                PluginLoader,
                resolve_plugin_dir,
            )

            # 插件目录必须用**绝对路径**：相对路径取决于当前工作目录，
            # 从快捷方式/其他目录启动时会解析到错误位置 → 插件发现数为 0
            # → 菜单全部消失（实测：cwd=exe 目录 total=10，cwd=C:\ total=0）
            _plugin_dir = resolve_plugin_dir("plugins")

            # P0-3 修复：先创建 PluginManager（高层 API，包装
            # PluginLoader）。原实现在这里创建，但随后直接调用
            # 裸 loader.load_all()，导致 PluginManager 的
            # 权限确认逻辑永远不会执行。
            if self.plugin_manager is None:
                try:
                    from app.plugin_manager import PluginManager
                    self.plugin_manager = PluginManager(
                        main_window=self,
                        plugin_dir=_plugin_dir,
                    )
                except Exception as e:
                    print(f"[MainWindow] PluginManager 创建失败: {e}")
                    self.plugin_manager = None

            # P0-3 修复：优先通过 PluginManager.load_all() 加载，
            # 因为它会在激活前逐个弹出**权限确认对话框**，并遵守
            # 用户在插件管理里设置的禁用列表。
            #
            # 原实现直接调用裸 loader.load_all(auto_activate=True)，
            # 而 PluginManager.load_all / _check_and_confirm_permissions
            # 全仓无调用者 —— 结果是危险权限确认框在启动路径上
            # 永远不会弹出，plugin.json 的 permissions 形同虚设。
            result = None
            if self.plugin_manager is not None:
                try:
                    result = self.plugin_manager.load_all(
                        auto_activate=True
                    )
                    loader = self.plugin_manager.loader
                except Exception as e:
                    print(f"[MainWindow] PluginManager 加载失败: {e}")
                    result = None
                    loader = None
            else:
                loader = None

            # 回退路径：PluginManager 不可用时仍用裸 loader，
            # 但必须显式打印警告（无权限确认）
            if result is None:
                print(
                    "[MainWindow] 警告：PluginManager 不可用，"
                    "回退到无权限确认的加载路径"
                )
                loader = PluginLoader(plugin_dir=_plugin_dir)

                # 关键：api_factory 是函数，接收 spec，返回 PluginAPI 实例
                def api_factory(spec):
                    try:
                        permissions = list(
                            getattr(spec.meta, 'permissions', []) or []
                        )
                        # 每个插件得到自己权限范围内的 API
                        api = PluginAPI(
                            self,
                            permissions=permissions,
                            plugin_name=spec.name,
                        )
                        # P0-3: 插件不得自行提权，宿主需要显式放行
                        api.grant_permissions_by_host(permissions)
                        return api
                    except Exception as e:
                        print(
                            f"[MainWindow] 创建 API 失败 "
                            f"({spec.name}): {e}"
                        )
                        return None

                result = loader.load_all(
                    plugin_dir=_plugin_dir,
                    api_factory=api_factory,
                    auto_activate=True,
                )

            self.plugin_loader = loader

            # B7 修复：将 loader 的 specs 桥接给 PluginManager
            # 原实现只对独立 loader 调用 load_all()，PluginManager
            # 从未 load_all，其 specs 为空。后续 plugins_panel 绑定
            # 的是空 manager，插件管理面板永远空白。
            if self.plugin_manager is not None and loader is not None:
                try:
                    self.plugin_manager.loader = loader
                    self.plugin_manager.specs = dict(loader.specs)
                except Exception as e:
                    print(f"[MainWindow] 桥接 loader 到 manager 失败: {e}")

            # 收集已激活的插件实例
            activated_specs = []
            try:
                if loader is not None and hasattr(
                    loader, 'get_activated_plugins'
                ):
                    activated_specs = loader.get_activated_plugins()
                elif loader is not None:
                    activated_specs = [
                        s for s in loader.specs.values()
                        if getattr(s, 'is_active', False)
                    ]
            except Exception:
                pass

            self.plugins = [
                getattr(s, 'instance', None)
                for s in activated_specs
                if getattr(s, 'instance', None) is not None
            ]

            # 将 plugin_manager 绑定到 plugins_panel
            if self.plugins_panel and self.plugin_manager:
                try:
                    self.plugins_panel.plugin_manager = self.plugin_manager
                    self.plugins_panel._connect_manager_signals()
                    self.plugins_panel.refresh()
                except Exception as e:
                    print(f"[MainWindow] 绑定 plugin_manager 失败: {e}")

            # 输出结果
            if result:
                print(
                    f"[MainWindow] 已加载 {result.activated} 个插件 "
                    f"(共 {result.total} 个)"
                )
            else:
                print("[MainWindow] 已加载 0 个插件")

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[MainWindow] 加载插件失败: {e}")

    def load_plugins(self):
        """公开接口：重新加载插件"""
        self._load_plugins()

    def reload_plugins(self):
        """重新加载插件"""
        try:
            for plugin in self.plugins:
                try:
                    if hasattr(plugin, 'deactivate'):
                        plugin.deactivate()
                except Exception:
                    pass

            self.plugins = []
            self._load_plugins()
            self.status_bar.showMessage("插件已重新加载", 2000)
        except Exception as e:
            print(f"[MainWindow] 重载插件失败: {e}")

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
        """
        关闭事件。

        修复说明（P0）：
            - 原实现仅调用 event.accept()，依赖 main.py 中的
              setQuitOnLastWindowClosed(True) 退出事件循环。
            - 这里额外显式调用 QApplication.quit()（双保险），
              以覆盖"关闭主窗口时仍有其他 QDialog/子窗口存活"的
              边缘场景，确保事件循环一定能退出。
        """
        if getattr(self, '_closing', False):
            event.accept()
            return

        self._closing = True

        try:
            # 检查未保存文件
            modified = []
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if not hasattr(w, 'proxy'):
                    continue
                proxy = w.proxy
                if proxy and hasattr(proxy, 'is_modified') and proxy.is_modified:
                    fp = None
                    if proxy.document:
                        fp = proxy.document.filepath
                    modified.append(fp or "(未命名)")

            if modified:
                msg = ("以下文件有未保存的修改：\n\n"
                       + "\n".join(f"• {os.path.basename(f)}"
                                    for f in modified[:10]))
                if len(modified) > 10:
                    msg += f"\n... 及其他 {len(modified) - 10} 个文件"
                msg += "\n\n是否放弃所有修改并退出？"

                reply = QMessageBox.question(
                    self, "未保存的修改", msg,
                    QMessageBox.Discard | QMessageBox.Cancel,
                    QMessageBox.Cancel
                )

                if reply == QMessageBox.Cancel:
                    event.ignore()
                    return

            # 保存会话
            try:
                if self.session and (not self.prefs or
                                      self.prefs.get("restore_session", True)):
                    self.session.save(self.tabs, self)
            except Exception:
                pass

            # 停止定时器
            if hasattr(self, '_status_timer'):
                self._status_timer.stop()
            if hasattr(self, '_session_timer'):
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
            pm = getattr(self, 'plugin_manager', None)
            loader = getattr(pm, 'loader', None) if pm is not None else None
            specs = getattr(loader, 'specs', None) or {}
            for spec in specs.values():
                inst = getattr(spec, 'instance', None)
                if inst is None:
                    continue
                # 面板的线程收尾
                panel = getattr(inst, 'ollama_panel', None)
                if panel is not None:
                    try:
                        panel._stop_threads(timeout_ms)
                    except Exception:
                        pass
                # 插件自定义的线程收尾钩子（若实现）
                hook = getattr(inst, 'shutdown_background', None)
                if callable(hook):
                    try:
                        hook()
                    except Exception:
                        pass
        except Exception:
            pass

        # 2. 插件热重载目录监控
        try:
            pm = getattr(self, 'plugin_manager', None)
            loader = getattr(pm, 'loader', None) if pm is not None else None
            if loader is not None and hasattr(loader, 'stop_watching'):
                loader.stop_watching()
        except Exception:
            pass

        # 3. 各标签的编辑器资源（停 LSP 子进程、停草稿定时器、摘文件监听）
        #    注意：这里不弹"未保存"对话框 —— closeEvent 已经在前面问过了。
        try:
            tabs = getattr(self, 'tabs', None)
            if tabs is not None and hasattr(tabs, 'count'):
                for i in range(tabs.count()):
                    try:
                        widget = tabs.widget(i)
                        proxy = getattr(widget, 'proxy', None)
                        if proxy is not None and hasattr(proxy, 'close'):
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
        return (f"<MainWindow tabs={self.tabs.count()} "
                f"current={self.tabs.currentIndex()}>")