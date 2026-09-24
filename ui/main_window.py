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

import os
import sys
import time
import subprocess
from typing import Optional, List, Dict, Any, Tuple

# ============================================================
# PyQt5 导入（全部统一）
# ============================================================
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QToolBar, QDockWidget, QStatusBar, QLabel, QMessageBox,
    QMenu, QApplication, QSplitter, QFileDialog, QInputDialog,
    QToolButton, QSizePolicy, QShortcut, QDialog,
    QDialogButtonBox, QListWidget, QListWidgetItem, QTextBrowser,
    QPlainTextEdit, QAction, QPushButton, QFrame
)
from PyQt5.QtCore import (
    Qt, QTimer, QSettings, QSize, QDateTime, QUrl, pyqtSignal
)
from PyQt5.QtGui import (
    QKeySequence, QIcon, QFont, QColor, QDesktopServices
)


# ============================================================
# 常量
# ============================================================
APP_NAME = "青草编辑器"
APP_VERSION = "2.0.0"
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
from ui.mixins.status_bar_mixin import StatusBarMixin

from ui.mixins.file_ops_mixin import FileOpsMixin
from ui.mixins.edit_ops_mixin import EditOpsMixin

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
            from core.macro import MacroRecorder, MacroManager
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
                from ui.editor_view import EditorWidget
                from core.content_provider import LocalFileProvider

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
        self._add_action(self.edit_menu, "📅 插入日期时间", "F5",
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

        self._add_action(self.view_menu, "▦ 列模式", "Alt+C",
                          self._toggle_column_mode)
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
                    self._add_action(
                        self.theme_menu, name, None,
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
            if theme.qss:
                self.setStyleSheet(theme.qss)

            # v3.0: 通知所有面板刷新样式
            loader.notify_widgets(self, theme)

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
            from core.theme_pack import ThemePack
            from PyQt5.QtWidgets import QFileDialog

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
            from core.theme_pack import ThemePack
            from PyQt5.QtCore import QSettings
            from PyQt5.QtWidgets import QFileDialog

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
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtCore import QUrl
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
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

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

        # 列模式
        self.column_mode_action = QAction("列模式", self)
        self.column_mode_action.setCheckable(True)
        self.column_mode_action.setShortcut(QKeySequence("Alt+C"))
        self.column_mode_action.toggled.connect(self._toggle_column_mode)
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

        # ============ 大纲面板（基础版） ============
        try:
            from ui.outline_panel import OutlinePanel
            self.outline = OutlinePanel(self)
            self.outline.symbol_clicked.connect(self._on_symbol_clicked)
            self.addDockWidget(Qt.LeftDockWidgetArea, self.outline)
        except Exception as e:
            print(f"[MainWindow] OutlinePanel 加载失败: {e}")
            self.outline = None

        # ============ 增强版大纲面板 ============
        # P3-8 重构后 outline_panel_enhanced.py 已合并到 outline_panel.py，
        # 通过 OutlinePanel(enhanced=True) 启用增强功能
        # （面包屑、类型筛选、排序切换、跟随光标高亮、3 列树）
        try:
            from ui.outline_panel import OutlinePanel
            self.outline_enhanced = OutlinePanel(self, enhanced=True)
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
            import traceback
            traceback.print_exc()
            self.outline_enhanced = None

        # ============ 目录树 ============
        try:
            from ui.directory_tree import DirectoryTree
            self.dir_tree = DirectoryTree()
            self.dir_tree.file_double_clicked.connect(self._on_file_from_tree)
            self.dir_tree.file_opened.connect(self._on_file_from_tree)

            self.dir_tree_dock = QDockWidget("项目", self)
            self.dir_tree_dock.setObjectName("DirectoryTreeDock")
            self.dir_tree_dock.setWidget(self.dir_tree)
            self.addDockWidget(Qt.LeftDockWidgetArea, self.dir_tree_dock)
        except Exception as e:
            print(f"[MainWindow] DirectoryTree 加载失败: {e}")
            self.dir_tree = None
            self.dir_tree_dock = None

        # ============ Minimap（安全模式，失败不影响启动） ============
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

        # ============ 全局搜索面板 ============
        try:
            from ui.global_search_panel import GlobalSearchPanel
            self.gsearch = GlobalSearchPanel(self)
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

        # ============ Python 控制台 ============
        try:
            from ui.python_console import PythonConsole
            self.console = PythonConsole(self)
            self.addDockWidget(Qt.BottomDockWidgetArea, self.console)
            self.console.hide()
        except Exception as e:
            print(f"[MainWindow] PythonConsole 加载失败: {e}")
            self.console = None

        # ============ 插件面板 ============
        try:
            from ui.plugins_panel import PluginsPanel
            # plugin_manager 稍后才创建，先创建面板，之后设置
            self.plugins_panel = PluginsPanel(
                main_window=self,
                plugin_manager=None,
            )
            self.addDockWidget(
                Qt.RightDockWidgetArea, self.plugins_panel
            )
            self.plugins_panel.hide()
        except Exception as e:
            print(f"[MainWindow] PluginsPanel 加载失败: {e}")
            self.plugins_panel = None

        # ============ 性能监控面板 ============
        try:
            from ui.perf_monitor import PerfMonitor
            self.perf_monitor = PerfMonitor(self)
            self.addDockWidget(
                Qt.BottomDockWidgetArea, self.perf_monitor
            )
            self.perf_monitor.hide()
        except Exception as e:
            print(f"[MainWindow] PerfMonitor 加载失败: {e}")
            self.perf_monitor = None

        # ============ 搜索栏 ============
        try:
            from ui.panels import SearchBar
            self.search_bar = SearchBar(self)
            self.addToolBar(Qt.BottomToolBarArea, self.search_bar)
            self.search_bar.hide()
        except Exception as e:
            print(f"[MainWindow] SearchBar 加载失败: {e}")
            self.search_bar = None

        # 设置角落
        self.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.TopRightCorner, Qt.RightDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.RightDockWidgetArea)

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
            if self.search_bar:
                self.search_bar.show()
                if hasattr(self.search_bar, 'show_and_focus'):
                    self.search_bar.show_and_focus()
        except Exception as e:
            print(f"[MainWindow] 显示搜索栏失败: {e}")

    def _show_global_search(self):
        """显示全局搜索"""
        try:
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
        if self.outline:
            self.outline.setVisible(checked)

    def _toggle_outline_enhanced(self, checked):
        """切换增强版大纲面板"""
        if self.outline_enhanced:
            self.outline_enhanced.setVisible(checked)

    def _toggle_directory(self, checked):
        """切换目录树面板"""
        if self.dir_tree_dock:
            self.dir_tree_dock.setVisible(checked)

    def _toggle_minimap(self, checked):
        """切换 Minimap"""
        if self.minimap_dock:
            self.minimap_dock.setVisible(checked)

    def _toggle_global_search(self, checked):
        """切换全局搜索"""
        if self.gsearch:
            self.gsearch.setVisible(checked)

    def _toggle_console(self):
        """切换控制台"""
        try:
            if self.console:
                self.console.setVisible(not self.console.isVisible())
        except Exception as e:
            print(f"[MainWindow] 控制台切换失败: {e}")

    def _toggle_plugins_panel(self, checked):
        """切换插件面板"""
        if self.plugins_panel:
            self.plugins_panel.setVisible(checked)

    def _toggle_perf_monitor(self, checked):
        """切换性能监控"""
        if self.perf_monitor:
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
            if self.perf_monitor:
                self.perf_monitor.show()
                self.perf_monitor.raise_()
        except Exception as e:
            self._show_error("性能监控失败", str(e))

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
            from core.search import (
                SearchOptions, SearchEngine, ReplaceEngine
            )
            from core.content_provider import LocalFileProvider

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
            from infrastructure.plugin_loader import PluginLoader
            from app.plugins import PluginAPI

            # 创建 PluginManager（高层 API，包装 PluginLoader）
            try:
                from app.plugin_manager import PluginManager
                self.plugin_manager = PluginManager(
                    main_window=self,
                    plugin_dir="plugins",
                )
            except Exception as e:
                print(f"[MainWindow] PluginManager 创建失败: {e}")
                self.plugin_manager = None

            # 创建 PluginLoader
            loader = PluginLoader(plugin_dir="plugins")

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
                    return api
                except Exception as e:
                    print(
                        f"[MainWindow] 创建 API 失败 "
                        f"({spec.name}): {e}"
                    )
                    return None

            # 加载所有插件
            result = loader.load_all(
                plugin_dir="plugins",
                api_factory=api_factory,
                auto_activate=True,
            )

            self.plugin_loader = loader

            # 收集已激活的插件实例
            activated_specs = []
            try:
                if hasattr(loader, 'get_activated_plugins'):
                    activated_specs = loader.get_activated_plugins()
                else:
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