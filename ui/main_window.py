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
from ui.mixins.project_mixin import ProjectMixin
from ui.mixins.status_bar_mixin import StatusBarMixin


class MainWindow(CapabilityWiringMixin, ProjectMixin, FileOpsMixin,
                 EditOpsMixin, StatusBarMixin, QMainWindow):
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

        # 外部文件变更 → 在正常事件层级询问用户是否重新加载
        #
        # 为什么不在这里之外的地方弹框：信号由 `QFileSystemWatcher` 回调
        # 发出，在回调里直接弹模态对话框会重入事件循环，并在窗口销毁阶段
        # 崩溃（实测段错误 0xC0000005）。见 `TabManager._handle_file_change`。
        try:
            self.tabs.file_changed_externally.connect(
                self._on_file_changed_externally
            )
        except Exception:
            pass

    def _on_file_changed_externally(self, filepath: str):
        """外部文件变更：询问用户是否重新加载"""
        if getattr(self, '_closing', False):
            return
        try:
            editor = None
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                proxy = getattr(w, 'proxy', None)
                doc = getattr(proxy, 'document', None) if proxy else None
                fp = getattr(doc, 'filepath', None) if doc else None
                if fp and os.path.normcase(os.path.abspath(fp)) == \
                        os.path.normcase(os.path.abspath(filepath)):
                    editor = w
                    break
            if editor is None:
                return

            ret = QMessageBox.question(
                self, "文件已修改",
                f"文件已被外部程序修改：\n"
                f"{os.path.basename(filepath)}\n\n是否重新加载？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
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
        # 从模板新建：接线 core/code_templates.py（此前零引用）
        self._add_action(self.file_menu, "🧩 从模板新建…", None,
                          self._new_from_template)
        self._add_action(self.file_menu, "📂 打开(&O)", "Ctrl+O",
                          self._open_file)
        self._add_action(self.file_menu, "📁 打开文件夹", None,
                          self._open_folder)
        self.file_menu.addSeparator()
        # 会话快照：接线 core/snapshot.py + ui/snapshot_manager_dialog.py（此前零引用）
        self._add_action(self.file_menu, "📸 会话快照…", None,
                          self._show_snapshot_dialog)
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

        # ---- 列编辑器（P0 核心功能）----
        #
        # 此前 `ui/column_editor_dialog.py` 的能力只能从编辑器右键菜单进入，
        # 而 Notepad++ 用户习惯在「编辑」菜单里找它（Edit → Column Editor…）。
        self.edit_menu.addSeparator()
        self._add_action(self.edit_menu, "📊 列编辑器…", "Alt+Shift+I",
                          self._column_editor)

        # ---- 书签（引擎早已实现、会话也已持久化，但此前无菜单无快捷键）----
        #
        # `core/editor.py` 的 next/prev/clear 三个方法此前**零入口**，
        # 用户设了书签却跳不过去。这里补全导航入口（Toggle 已在
        # 编辑器右键菜单，快捷键 Ctrl+F2 保持与主流编辑器一致）。
        self.bookmark_menu = self.edit_menu.addMenu("🔖 书签")
        self._add_action(self.bookmark_menu, "切换书签", "Ctrl+F2",
                          self._toggle_bookmark)
        self._add_action(self.bookmark_menu, "下一个书签", "F2",
                          self._bookmark_next)
        self._add_action(self.bookmark_menu, "上一个书签", "Shift+F2",
                          self._bookmark_prev)
        self._add_action(self.bookmark_menu, "清除所有书签", None,
                          self._bookmark_clear)

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
        # 手工创建的 QAction 也要注册进 ActionManager，否则快捷键编辑器里
        # 看不到"列模式"，且 `view.column_mode` 方案的 overrides 会失效
        # （`set_shortcut()` 对不存在的名字静默返回 False）。
        if self.act_mgr is not None:
            try:
                self.act_mgr.register(
                    "view.column_mode",
                    self.column_mode_action,
                    default_shortcut="Alt+C",
                    description="列模式",
                )
            except Exception as e:
                print(f"[MainWindow] 注册列模式动作失败: {e}")
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

        # 大文件强制高亮（性能开关）
        #
        # 背景：为把 2MB/50 万行文件的打开从 2.1s 降到 ~0.5s，
        # `ui/editor_view.py` 对大文档默认关闭语法高亮与缩略图渲染
        # （见 LARGE_DOC_LINES 的实测注释）。此开关给需要彩色显示的用户
        # 一个显式覆盖入口；切换后对当前标签重新应用词法器。
        self.force_highlight_large_files_action = QAction(
            "🎨 大文件强制高亮", self)
        self.force_highlight_large_files_action.setCheckable(True)
        self.force_highlight_large_files_action.setChecked(False)
        self.force_highlight_large_files_action.toggled.connect(
            self._toggle_force_highlight_large_files)
        self.view_menu.addAction(self.force_highlight_large_files_action)
        self._force_highlight_large_files = False

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

        # B 阶段：LSP 其余能力的用户入口
        #
        # 这些请求方法（hover/references/rename/document_symbols/
        # code_actions/formatting/signature_help）早就实现了，但**结果信号
        # 零 connect、也没有任何 UI 入口** —— 属于"写好了没接线"。
        # 这里补上入口（统一走 `EditorProxy` 的同名方法）。
        self.lsp_menu = self.tools_menu.addMenu("🧠 LSP（智能）")
        # 备注：Ctrl+Alt+R 已被"符号跳转"占用、F12 已被"转到定义"占用，
        # 因此这里刻意避开；新增键均已通过 tests/test_shortcuts.py 的
        # "无重复快捷键"严格扫描。
        self._add_action(self.lsp_menu, "💡 悬停信息", "Ctrl+Alt+H",
                          self._lsp_hover)
        self._add_action(self.lsp_menu, "🔗 查找引用", "Shift+F12",
                          self._lsp_find_references)
        self._add_action(self.lsp_menu, "✏ 重命名符号", "Ctrl+Alt+N",
                          self._lsp_rename)
        self._add_action(self.lsp_menu, "🧾 文档符号", "Ctrl+Alt+K",
                          self._lsp_document_symbols)
        self._add_action(self.lsp_menu, "💡 代码操作", "Ctrl+Alt+O",
                          self._lsp_code_actions)
        self._add_action(self.lsp_menu, "🪄 格式化文档",
                          "Ctrl+Alt+L", self._lsp_format)
        self._add_action(self.lsp_menu, "📝 签名帮助", "Ctrl+Shift+Space",
                          self._lsp_signature)

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

        # ---- 对比合并（P0 核心功能）----
        #
        # 算法引擎 `core/file_merge.py` 早已可用（本轮还修了"末尾追加被
        # 静默丢弃"与"末尾换行丢失"），但 UI 对话框此前被删除、零入口。
        # 注意：**不绑快捷键** —— `Ctrl+Alt+D` 已被"插入日期时间"占用
        # （且有 tests/test_shortcuts.py 的重复扫描保护）。
        self._add_action(self.tools_menu, "🔀 对比文件…", None,
                          self._show_file_diff)

        # ---- 格式化 / 导出 / 崩溃统计（接线零引用的孤立能力）----
        self._setup_format_menu()
        self._setup_export_menu()

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
        # 性能剖析：`core/profiler.py` + `ui/profiler_panel.py` 此前零引用。
        # **不绑快捷键**（全仓快捷键已很拥挤，且 tests/test_shortcuts.py
        # 会扫描重复绑定）。
        _profiler_action = self._add_action(
            self.tools_menu, "⏱ 性能剖析…", None, self._show_profiler)
        try:
            _profiler_action.setToolTip(
                "用 cProfile 统计 **Python 帧** 的耗时。\n"
                "注意：Qt 事件循环与 Scintilla 的绘制/排版耗时不在报告里 ——\n"
                "适合排查插件回调 / 搜索 / 解析慢；\n"
                "要看整体流畅度请用上面的「📊 性能监控」。"
            )
        except Exception:
            pass
        # 代码片段库（本地片段包导入）
        #
        # 原 `ui/snippet_market_dialog.py` 是"网络片段市场"，指向一个
        # **实测返回 404 的 GitHub 仓库**；已改造为本地片段包库
        # （见 core/snippet_market.py 的模块说明）。
        self._add_action(self.tools_menu, "📚 代码片段库…", None,
                         self._show_snippet_library)
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
        # 崩溃统计：`core/crash_stats.py` 早就有 get_top_exceptions /
        # get_recent_count / should_notify / cleanup_old，但**零引用** ——
        # 用户完全看不到"这个版本是不是经常崩"。
        self._add_action(self.help_menu, "📉 崩溃统计", None,
                          self._show_crash_stats)
        self._add_action(self.help_menu, "ℹ 关于", None, self._about)

        # ============ 特色功能菜单（P1-7 入口重排）============
        #
        # AI / Git / 调试这三条**差异化主线**原先分散在插件注册路径里
        # （`工具/Git/...`、AI 助手自己的菜单），试用者很容易以为
        # "这编辑器没有这些能力" —— **用户找不到 = 差异化不存在**。
        #
        # 这里做一级可见的聚合入口，并**直接列出插件真实注册的命令**
        # （与命令面板同源：`act_mgr.actions` 里的 `plugin.<插件>.<命令>`），
        # 因此不会出现"菜单里有、点了没反应"。
        #
        # 注意：插件在**窗口构造之后**才加载，所以构造时子菜单可能是空的；
        # `main.py` 在插件加载完成后会调用 `refresh_feature_menu()` 重建。
        self._setup_feature_menu()

        # ============ 多键快捷键序列（VSCode 风格）============
        #
        # 接线 `core/key_sequence_manager.py`（190 行，此前零引用）。
        # 放最后：此时所有动作处理器都已就绪。
        #
        # 安全设计见 `_setup_key_sequences()` 的 docstring：
        # 只处理"带 Ctrl/Alt + 焦点在编辑器 + 无模态窗口"的按键，
        # 因此不会吞掉普通输入。
        self._setup_key_sequences()

        # ============ 项目菜单（项目根 / 项目配置 / 工作区 / 任务）============
        #
        # 接线三个此前零引用的模块：core/workspace.py、
        # core/project_config.py、ui/task_panel.py + core/project_tasks.py。
        # 它们共享同一个「项目根」语义，因此必须一起接（详见
        # ui/mixins/project_mixin.py 的模块说明）。
        #
        # 放最后：需要 `self.file_menu` 已存在（作为插入锚点）。
        self._setup_project_menu()

    def refresh_feature_menu(self):
        """重新填充「特色功能」里的插件命令子菜单

        为什么需要：插件在窗口构造之后加载（`main.py` 的 deferred_init），
        构造时 `act_mgr.actions` 里还没有 `plugin.*` 条目。若只在构造时列
        一次，用户会看到"（该插件未注册命令）"的假象。
        """
        try:
            if getattr(self, 'feature_menu', None) is None:
                return
        except Exception:
            return
        for title, plugin in (
            ("🤖 AI 助手（ai_assistant）", "ai_assistant"),
            ("🔀 Git（git_deep）", "git_deep"),
        ):
            try:
                for act in self.feature_menu.actions():
                    if not (act.menu() and act.text() == title):
                        continue
                    act.menu().clear()
                    cmds = self._plugin_commands(plugin)
                    if not cmds:
                        item = act.menu().addAction(
                            "（该插件未注册命令，或未启用）"
                        )
                        item.setEnabled(False)
                    else:
                        for _name, qa in cmds:
                            act.menu().addAction(qa)
                    break
            except Exception as e:
                if logger is not None:
                    logger.debug("刷新特色功能菜单失败(%s): %s", plugin, e)

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
            # 问题面板：显示 LSP 诊断（生产者在 core/editor.py 的
            # _publish_problems 里写入 ProblemManager）
            ("问题", "panel.problems", self._toggle_problems_panel),
            # 本轮接线：LSP 状态/安装向导 + 撤销历史（此前零实例化）
            ("LSP 状态", "panel.lsp", self._toggle_lsp_panel),
            ("撤销历史", "panel.undo_history",
             self._toggle_undo_history_panel),
            # 项目任务面板（该项目根下的 .qingcao/tasks.json）
            ("任务", "panel.task", self._toggle_task_panel),
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
                     slot, action_name: Optional[str] = None) -> QAction:
        """
        添加菜单项。

        参数:
            menu: 目标菜单
            text: 显示文本
            shortcut: 快捷键字符串（可选）
            slot: 槽函数（None 时该项为禁用的占位）
            action_name: 注册进 `ActionManager` 的名字（不给则按映射表/自动生成）

        返回:
            创建的 QAction

        ★ 为什么这里要注册动作（本轮实测发现的重要缺陷）：

            原先 `_add_action()` **只创建 QAction 挂到菜单上**，
            从不调用 `self.act_mgr.register()` —— 全仓对
            `act_mgr.register(` 的调用处数为 **0**（插件除外）。

            后果是 `ActionManager.actions` 里**一个核心动作都没有**：

            * 「⌨ 快捷键编辑器」列出的是一张**空表**
              （它遍历 `self.act_mgr.actions`）；
            * `core/keymap_profiles.py` 里 VSCode/Sublime/Vim 方案的
              overrides 全部指向不存在的动作名 → `set_shortcut()`
              返回 False 被静默忽略 → **方案套用后毫无效果**；
            * `reset_to_defaults()` 因 `defaults` 为空，会把所有动作的
              快捷键**清成空**（见 app/actions.py:353-358）——
              也就是"套用 VSCode 方案"会先把你的快捷键全抹掉。

            这里在创建动作时**顺带注册**并传入 `defaults`
            （= 当前 shortcut），使 `reset_to_defaults()` 真正"恢复默认"
            而不是"全部清空"。
        """
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
            # P8-5: 运行时重复检测（不抛异常，避免打断启动）
            self._register_action_shortcut(action)
        # slot 允许为 None（禁用占位项）。原实现直接 connect(None)，
        # PyQt 会抛 `TypeError: argument 1 has unexpected type 'NoneType'`
        # —— 一个占位项就能让整个 MainWindow 构造失败。
        if slot is not None and callable(slot):
            action.triggered.connect(slot)
        else:
            action.setEnabled(False)

        # 注册进 ActionManager（快捷键编辑器 / 快捷键方案 / 命令面板都靠它）
        if action_name is None:
            action_name = self._canonical_action_name(text, shortcut)
        if action_name and self.act_mgr is not None:
            try:
                self.act_mgr.register(
                    action_name,
                    action,
                    default_shortcut=shortcut or None,
                    description=text,
                )
            except Exception as e:
                print(f"[MainWindow] 注册动作 {action_name} 失败: {e}")
        menu.addAction(action)
        return action

    def _canonical_action_name(self, text: str,
                              shortcut: Optional[str]) -> Optional[str]:
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
        digest = hashlib.md5(
            ("%s|%s" % (text, shortcut)).encode("utf-8")
        ).hexdigest()[:10]
        return "misc.%s" % digest

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
            for it in (items or []):
                path = it.get('path') or ""
                name = os.path.basename(path) if path else "(未知)"
                lines.append("%s:%d:%d" % (
                    name, int(it.get('line', 0)) + 1,
                    int(it.get('character', 0)) + 1,
                ))
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
            self.status_bar.showMessage(
                "重命名将影响 %d 处（跨文件应用尚未实现）" % count, 8000
            )
        except Exception:
            pass

    def _on_lsp_symbols(self, symbols: list):
        """文档符号 → 列表展示"""
        try:
            lines = []
            for s in (symbols or []):
                indent = "  " * int(s.get('depth', 0) or 0)
                lines.append("%s%s  (行 %d)" % (
                    indent, s.get('name') or "",
                    int(s.get('line', 0)) + 1,
                ))
            if not lines:
                self.status_bar.showMessage("未获取到文档符号", 4000)
                return
            self._show_info(
                "文档符号（%d 项）" % len(lines), "\n".join(lines)
            )
        except Exception as e:
            logger.debug("显示文档符号失败: %s", e)

    def _on_lsp_code_actions(self, actions: list):
        """代码操作 → 选单，选中后报告（应用留待后续）"""
        try:
            titles = [a.get('title') or "" for a in (actions or [])]
            titles = [t for t in titles if t]
            if not titles:
                self.status_bar.showMessage("此处没有可用的代码操作", 4000)
                return
            from PyQt5.QtWidgets import QInputDialog
            choice, ok = QInputDialog.getItem(
                self, "代码操作", "选择要执行的操作:", titles, 0, False
            )
            if ok and choice:
                self.status_bar.showMessage(
                    "已选择代码操作：%s（应用尚未实现）" % choice, 8000
                )
        except Exception as e:
            logger.debug("显示代码操作失败: %s", e)

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

    def _lsp_code_actions(self):
        proxy = self._with_proxy("code_actions", "代码操作")
        if proxy is not None:
            proxy.code_actions()

    def _lsp_format(self):
        proxy = self._with_proxy("format_document", "格式化")
        if proxy is not None:
            proxy.format_document()

    def _lsp_signature(self):
        proxy = self._with_proxy("request_signature", "签名帮助")
        if proxy is not None:
            proxy.request_signature()

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
        for name in self._default_panels_for_screen():
            try:
                if self._ensure_panel(name):
                    self._show_panel(name)
            except Exception as e:
                print(f"[MainWindow] 默认面板 {name} 构造失败: {e}")

    def _default_panels_for_screen(self):
        """按当前屏幕的**逻辑可用区域**决定"开箱面板"数量

        ★ 高 DPI 验证发现（真实桌面 200% 截图）：

            1920x1080 物理屏在 200% 缩放下只有 **960x540 逻辑像素**。
            此时仍默认铺开 4 个面板（左目录树 + 底全局搜索 +
            右插件 + 底性能监控），编辑器区域被挤到**只剩 3 行文本**，
            全局搜索面板的单选项还被裁掉一半 —— 界面基本没法用。

            这是"高 DPI ≈ 小屏"的普遍情况（1080p 笔记本开 150%~200%
            很常见，4K 开 200% 也只有 1920x1080 逻辑）。

        策略（简单、可预期）：
          * 逻辑可用区域 >= 1280x720 → 保持原本的完整默认面板集；
          * 否则 → **只开左侧目录树**，其余面板由用户按需从
            「视图 → 面板」打开（各自记住可见性，会话恢复也会覆盖）。

        注意：会话恢复（`_restore_session`）在此之后执行，会按用户上次
        保存的布局重新显示面板 —— 因此本策略只影响"首次/无会话"的默认。
        """
        try:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            scr = app.primaryScreen() if app is not None else None
            if scr is not None:
                geo = scr.availableGeometry()
                if geo.width() < 1280 or geo.height() < 720:
                    print("[MainWindow] 逻辑屏幕 %dx%d 偏小（高 DPI/小屏），"
                          "仅默认打开目录树" % (geo.width(), geo.height()))
                    return ('dir_tree',)
        except Exception as e:
            print(f"[MainWindow] 检测屏幕尺寸失败: {e}")
        return self._DEFAULT_PANELS

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
        'problems',
        # 本轮接线：两个此前零实例化的孤立面板
        # （`ui/lsp_panel.py` 含语言服务器安装向导；
        #   `ui/undo_history_panel.py` 展示自研撤销栈）
        'lsp', 'undo_history',
        # 项目任务面板（`ui/task_panel.py` + `core/project_tasks.py`
        # 此前零实例化；由 project_mixin 绑定当前项目根）
        'task',
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
            # P0-3: 信号现携带第 4 个参数（SearchOptions）——
            # 面板勾选的"正则/大小写/全词/转义/多行"必须传到替换端，
            # 否则正则搜索会按字面量替换（详见 _on_global_replace）。
            self.gsearch.replace_requested.connect(
                self._on_global_replace
            )
            self.addDockWidget(Qt.BottomDockWidgetArea, self.gsearch)
            self.gsearch.hide()
        except Exception as e:
            print(f"[MainWindow] GlobalSearchPanel 加载失败: {e}")
            self.gsearch = None

    def _build_panel_problems(self):
        """构造问题面板（显示 LSP 诊断）

        背景（消费者/生产者缺口）：
            `ui/problems_panel.py` 实现了完整 UI 且会从
            `core.problems.get_problem_manager()` 读取问题，但
            `set_file_problems()` 原先**全仓零调用** —— 面板挂上去也永远
            空白。生产者已在 `core/editor.py::_publish_problems` 补上
            （`_on_lsp_diagnostics` 尾部），这里把面板接进视图。
        """
        try:
            from ui.problems_panel import ProblemsPanel
            self.problems = ProblemsPanel(self)
            self.problems.setObjectName("ProblemsPanel")
            self.addDockWidget(Qt.BottomDockWidgetArea, self.problems)
            self.problems.hide()
        except Exception as e:
            print(f"[MainWindow] ProblemsPanel 加载失败: {e}")
            self.problems = None

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
        sc = getattr(proxy, 'sc', None) if proxy is not None else None
        if sc is None:
            return
        try:
            # 清掉去重标记，强制重新判定
            sc._last_lexer_filepath = None
            path = ''
            try:
                path = getattr(proxy.document, 'filepath', '') or ''
            except Exception:
                pass
            sc.set_lexer_by_filename(path)
            if self.minimap is not None:
                self.minimap.set_editor(sc)
            self.statusBar().showMessage(
                "大文件强制高亮：%s" % ("已开启" if checked else "已关闭"),
                3000)
        except Exception as e:
            print(f"[MainWindow] 切换大文件高亮失败: {e}")

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

    def _toggle_problems_panel(self, checked):
        """切换问题面板（LSP 诊断列表）"""
        if self._ensure_panel('problems') and self.problems:
            self.problems.setVisible(checked)

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
        return getattr(proxy, 'undo_manager', None)

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
            if hasattr(self.macro, 'recording'):
                is_recording = bool(self.macro.recording)
            elif hasattr(self.macro, 'is_recording'):
                is_recording = bool(self.macro.is_recording())

            if is_recording:
                macro = self.macro.stop()
                self.rec_label.hide()
                # P0-1: 明确回报录到几条 —— "录制中"却不显示数量时，
                # 用户无法察觉"录到 0 条"这种静默失败。
                count = 0
                try:
                    count = len(getattr(macro, 'commands', []) or [])
                except Exception:
                    count = 0
                self.status_bar.showMessage(
                    f"宏录制已停止（{count} 条命令）", 3000
                )
            else:
                # P0-1: 开始录制前先绑定当前标签的 undo_manager
                # （标签可能自上次录制后已切换；start() 内部也会再解析一次）
                if hasattr(self.macro, 'bind_current_undo_manager'):
                    self.macro.bind_current_undo_manager()
                self.macro.start()
                self.rec_label.setText("● REC")
                self.rec_label.show()
                # 没绑上 = 必然录到 0 条：立刻可见地告诉用户，
                # 而不是等他录完、回放时才提示"没有可回放的宏"。
                if (hasattr(self.macro, 'has_hook')
                        and not self.macro.has_hook):
                    self.status_bar.showMessage(
                        "宏录制已开始，但当前没有可录制的编辑器"
                        "（请先打开或新建标签）", 5000
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

            # P0-1: 录制中切换标签 → 录制钩子必须跟着切到新标签的
            # undo_manager（proxy 是每标签一个）。否则用户在录制过程中
            # 切了标签，之后的编辑一条也录不到，而 UI 仍显示"● REC"。
            try:
                macro = getattr(self, 'macro', None)
                if (macro is not None
                        and getattr(macro, 'recording', False)
                        and hasattr(macro, 'bind_current_undo_manager')):
                    macro.bind_current_undo_manager()
            except Exception as e:
                print(f"[MainWindow] 切换标签后重绑宏录制失败: {e}")

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
        gsearch = getattr(self, 'gsearch', None)
        if gsearch is not None and hasattr(gsearch, 'build_options'):
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

    def _on_global_replace(self, pattern: str, replace_text: str,
                            file_results: dict, options=None):
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
                            result, replace_text,
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

            # P1-7：插件加载完成后，重建「特色功能」里的插件命令子菜单
            #
            # `_setup_feature_menu()` 在窗口构造时执行，那时 `act_mgr` 里
            # 还没有 `plugin.*` 条目（插件此刻才加载），因此必须在这里
            # 刷新一次 —— 否则用户看到的是"（该插件未注册命令）"的假象，
            # 等于 P1-7 没做。
            try:
                self.refresh_feature_menu()
            except Exception as e:
                print(f"[MainWindow] 刷新特色功能菜单失败: {e}")

            # 快捷键方案：应用用户上次选择的方案
            #
            # 为什么必须放在启动路径上：方案只写进 QSettings 而不在启动时
            # 重新应用的话，用户重启后快捷键会**悄悄回到默认** ——
            # 这个功能就等于没做（用户的抱怨会是"我设了但没用"）。
            #
            # 时序：必须在所有动作注册完之后（动作在 `_build_menus` 里注册，
            # 早于这里），否则 `set_shortcut()` 找不到目标动作而静默失败。
            try:
                from ui.keymap_editor import apply_saved_scheme
                if apply_saved_scheme(self.act_mgr):
                    from ui.keymap_editor import load_saved_scheme
                    print(f"[MainWindow] 已应用快捷键方案: "
                          f"{load_saved_scheme()}")
            except Exception as e:
                print(f"[MainWindow] 应用快捷键方案失败: {e}")

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
            if hasattr(self.tabs, 'dispose'):
                self.tabs.dispose()
        except Exception as e:
            logger.debug("释放 TabManager 资源失败: %s", e)

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