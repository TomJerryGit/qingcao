# -*- coding: utf-8 -*-
"""菜单构建（从 MainWindow 抽取，v2.18）"""

import hashlib
import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QDateTime, QSettings, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QFont, QIcon, QKeySequence
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

from core.i18n_json import AVAILABLE as _I18N_LANGS
from core.i18n_json import current_language as _i18n_lang
from core.i18n_json import set_language as _i18n_set_language
from core.i18n_json import tr_menu as _tr_menu
from ui.mixins.capability_wiring_mixin import CapabilityWiringMixin
from ui.mixins.edit_ops_mixin import EditOpsMixin
from ui.mixins.file_ops_mixin import FileOpsMixin
from ui.mixins.project_mixin import ProjectMixin
from ui.mixins.status_bar_mixin import StatusBarMixin


logger = logging.getLogger("QingCao")


class MenuBuilderMixin:
    """菜单构建（从 MainWindow 抽取，v2.18）"""

    def _build_menus(self):
        """构建菜单栏"""
        menubar = self.menuBar()

        # ============ 文件菜单 ============
        self.file_menu = menubar.addMenu("文件(&F)")

        self._add_action(self.file_menu, "📄 新建(&N)", "Ctrl+N", self._new_file)
        # 从模板新建：接线 core/code_templates.py（此前零引用）
        self._add_action(self.file_menu, "🧩 从模板新建…", None, self._new_from_template)
        self._add_action(self.file_menu, "📂 打开(&O)", "Ctrl+O", self._open_file)
        self._add_action(self.file_menu, "📁 打开文件夹", None, self._open_folder)
        self.file_menu.addSeparator()
        # 会话快照：接线 core/snapshot.py + ui/snapshot_manager_dialog.py（此前零引用）
        self._add_action(self.file_menu, "📸 会话快照…", None, self._show_snapshot_dialog)
        self.file_menu.addSeparator()
        self._add_action(self.file_menu, "💾 保存(&S)", "Ctrl+S", self._save_file)
        self._add_action(self.file_menu, "💾 另存为(&A)", "Ctrl+Shift+S", self._save_file_as)
        self._add_action(self.file_menu, "💾 全部保存", "Ctrl+Alt+S", self._save_all)
        self.file_menu.addSeparator()
        self._add_action(self.file_menu, "❌ 关闭标签", "Ctrl+W", self._close_current_tab)
        self._add_action(self.file_menu, "❌ 关闭所有标签", "Ctrl+Shift+W", self._close_all_tabs)
        self._add_action(
            self.file_menu, "↩ 恢复关闭的标签", "Ctrl+Shift+T", self._restore_closed_tab
        )
        self.file_menu.addSeparator()
        self._add_action(self.file_menu, "🚪 退出(&X)", "Ctrl+Q", self.close)

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
        self._add_action(self.edit_menu, "📋 粘贴为纯文本", "Ctrl+Alt+Shift+V", self._paste_plain)
        self._add_action(self.edit_menu, "全选(&A)", "Ctrl+A", self._select_all)
        self.edit_menu.addSeparator()
        self._add_action(self.edit_menu, "🔍 查找(&F)", "Ctrl+F", self._show_search)
        self._add_action(self.edit_menu, "🔎 全局搜索", "Ctrl+Shift+F", self._show_global_search)
        self.edit_menu.addSeparator()
        self._add_action(self.edit_menu, "📍 跳转到行", "Ctrl+G", self._goto_line_dialog)
        self._add_action(self.edit_menu, "💬 注释切换", "Ctrl+/", self._toggle_comment)
        self._add_action(self.edit_menu, "🧮 计算表达式", "Ctrl+Shift+E", self._eval_expression)
        # P8-2: F5 从"插入日期时间"改为"运行当前文件"（主流 IDE 语义）。
        #   日期时间改绑 Ctrl+Alt+D，见下面的编辑菜单。
        #   运行入口见 _run_current_file()：调试插件未激活时给出**明确
        #   提示**，不再静默失败。
        self._add_action(self.edit_menu, "📅 插入日期时间", "Ctrl+Alt+D", self._insert_datetime)
        self.edit_menu.addSeparator()
        self._add_action(self.edit_menu, "📋 复制整行", "Ctrl+Shift+D", self._duplicate_line)
        self._add_action(self.edit_menu, "⬆ 上移行", "Ctrl+Shift+Up", self._move_line_up)
        self._add_action(self.edit_menu, "⬇ 下移行", "Ctrl+Shift+Down", self._move_line_down)
        self._add_action(
            self.edit_menu, "🔷 选中下一个相同项", "Ctrl+D", self._select_next_occurrence
        )
        self.edit_menu.addSeparator()
        self._add_action(self.edit_menu, "🔠 转为大写", None, self._to_upper)
        self._add_action(self.edit_menu, "🔡 转为小写", None, self._to_lower)

        # ---- 列编辑器（P0 核心功能）----
        #
        # 此前 `ui/column_editor_dialog.py` 的能力只能从编辑器右键菜单进入，
        # 而 Notepad++ 用户习惯在「编辑」菜单里找它（Edit → Column Editor…）。
        self.edit_menu.addSeparator()
        self._add_action(self.edit_menu, "📊 列编辑器…", "Alt+Shift+I", self._column_editor)

        # ---- 书签（引擎早已实现、会话也已持久化，但此前无菜单无快捷键）----
        #
        # `core/editor.py` 的 next/prev/clear 三个方法此前**零入口**，
        # 用户设了书签却跳不过去。这里补全导航入口（Toggle 已在
        # 编辑器右键菜单，快捷键 Ctrl+F2 保持与主流编辑器一致）。
        self.bookmark_menu = self.edit_menu.addMenu("🔖 书签")
        self._add_action(self.bookmark_menu, "切换书签", "Ctrl+F2", self._toggle_bookmark)
        self._add_action(self.bookmark_menu, "下一个书签", "F2", self._bookmark_next)
        self._add_action(self.bookmark_menu, "上一个书签", "Shift+F2", self._bookmark_prev)
        self._add_action(self.bookmark_menu, "清除所有书签", None, self._bookmark_clear)

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
        self._add_action(self.view_menu, "🖥 无干扰模式", "F11", self.toggle_distraction_free)
        self._add_action(self.view_menu, "⛶ 全屏", "Shift+F11", self.toggle_fullscreen)
        self.view_menu.addSeparator()
        self._add_action(self.view_menu, "🔍 放大字体", "Ctrl+=", self._zoom_in)
        self._add_action(self.view_menu, "🔍 缩小字体", "Ctrl+-", self._zoom_out)
        self._add_action(self.view_menu, "🔍 重置字体", "Ctrl+0", self._zoom_reset)
        self.view_menu.addSeparator()

        # 大文件强制高亮（性能开关）
        #
        # 背景：为把 2MB/50 万行文件的打开从 2.1s 降到 ~0.5s，
        # `ui/editor_view.py` 对大文档默认关闭语法高亮与缩略图渲染
        # （见 LARGE_DOC_LINES 的实测注释）。此开关给需要彩色显示的用户
        # 一个显式覆盖入口；切换后对当前标签重新应用词法器。
        self.force_highlight_large_files_action = QAction("🎨 大文件强制高亮", self)
        self.force_highlight_large_files_action.setCheckable(True)
        self.force_highlight_large_files_action.setChecked(False)
        self.force_highlight_large_files_action.toggled.connect(
            self._toggle_force_highlight_large_files
        )
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
        self._add_action(self.tools_menu, "▶ 运行当前文件", "F5", self._run_current_file)
        # P6: F12 = 转到定义，把 LspClient.request_definition 接进生产路径
        self._add_action(self.tools_menu, "🔎 转到定义", "F12", self._goto_definition)

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
        self._add_action(self.lsp_menu, "💡 悬停信息", "Ctrl+Alt+H", self._lsp_hover)
        self._add_action(self.lsp_menu, "🔗 查找引用", "Shift+F12", self._lsp_find_references)
        self._add_action(self.lsp_menu, "✏ 重命名符号", "Ctrl+Alt+N", self._lsp_rename)
        self._add_action(self.lsp_menu, "🧾 文档符号", "Ctrl+Alt+K", self._lsp_document_symbols)
        self._add_action(self.lsp_menu, "💡 代码操作", "Ctrl+Alt+O", self._lsp_code_actions)
        self._add_action(self.lsp_menu, "🪄 格式化文档", "Ctrl+Alt+L", self._lsp_format)
        self._add_action(self.lsp_menu, "📝 签名帮助", "Ctrl+Shift+Space", self._lsp_signature)

        self.tools_menu.addSeparator()

        self._add_action(self.tools_menu, "⌨ 命令面板", "Ctrl+Shift+P", self._show_command_palette)
        self._add_action(self.tools_menu, "📂 文件切换", "Ctrl+P", self._show_file_palette)
        # P2-4: 符号跳转改为 Ctrl+Alt+R，避免与"重新加载"Ctrl+R 冲突
        self._add_action(self.tools_menu, "🔣 符号跳转", "Ctrl+Alt+R", self._show_symbol_palette)
        self.tools_menu.addSeparator()
        self._add_action(self.tools_menu, "🐍 Python 控制台", "Ctrl+`", self._toggle_console)
        _term_act = self._add_action(
            self.tools_menu,
            "💻 终端",
            "Ctrl+Shift+`",
            self._toggle_terminal,
            action_name="panel.terminal",
        )
        _term_act.setCheckable(True)
        self.tools_menu.addSeparator()
        self._add_action(self.tools_menu, "⏺ 录制/停止宏", "Ctrl+Shift+R", self._toggle_macro)
        self._add_action(self.tools_menu, "▶ 回放宏", "Ctrl+Shift+M", self._play_macro)
        self.tools_menu.addSeparator()

        # ---- 对比合并（P0 核心功能）----
        #
        # 算法引擎 `core/file_merge.py` 早已可用（本轮还修了"末尾追加被
        # 静默丢弃"与"末尾换行丢失"），但 UI 对话框此前被删除、零入口。
        # 注意：**不绑快捷键** —— `Ctrl+Alt+D` 已被"插入日期时间"占用
        # （且有 tests/test_shortcuts.py 的重复扫描保护）。
        self._add_action(self.tools_menu, "🔀 对比文件…", None, self._show_file_diff)

        # ---- 格式化 / 导出 / 崩溃统计（接线零引用的孤立能力）----
        self._setup_format_menu()
        self._setup_export_menu()

        self.tools_menu.addSeparator()
        self._add_action(self.tools_menu, "🧩 插件市场", None, self._show_plugin_store)
        self._add_action(self.tools_menu, "🔌 插件管理", None, self._show_plugins_panel)
        self._add_action(self.tools_menu, "⌨ 快捷键编辑器", None, self._show_keymap_editor)
        self.tools_menu.addSeparator()
        self._add_action(self.tools_menu, "📊 性能监控", None, self._show_perf_monitor)
        # 性能剖析：`core/profiler.py` + `ui/profiler_panel.py` 此前零引用。
        # **不绑快捷键**（全仓快捷键已很拥挤，且 tests/test_shortcuts.py
        # 会扫描重复绑定）。
        _profiler_action = self._add_action(
            self.tools_menu, "⏱ 性能剖析…", None, self._show_profiler
        )
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
        self._add_action(self.tools_menu, "📚 代码片段库…", None, self._show_snippet_library)
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
        self._add_action(self.tools_menu, "⚙ 首选项...", "Ctrl+,", self._show_preferences)

        self.tools_menu.addSeparator()
        self._add_action(self.tools_menu, "📤 导出配置", None, self._export_config)
        self._add_action(self.tools_menu, "📥 导入配置", None, self._import_config)

        # ============ 帮助菜单 ============
        self.help_menu = menubar.addMenu("帮助(&H)")

        self._add_action(self.help_menu, "⌨ 快捷键参考", None, self._show_shortcuts)
        # P2-C4: manual 参数
        self._add_action(
            self.help_menu,
            "💡 每日技巧",
            None,
            lambda checked=False: self._show_daily_tip(manual=True),
        )
        self.help_menu.addSeparator()
        self._add_action(self.help_menu, "📖 在线文档", None, self._show_online_docs)
        self._add_action(self.help_menu, "🐙 GitHub", None, self._show_github)
        self._add_action(self.help_menu, "💬 反馈与建议", None, self._show_feedback)
        self.help_menu.addSeparator()
        # 崩溃统计：`core/crash_stats.py` 早就有 get_top_exceptions /
        # get_recent_count / should_notify / cleanup_old，但**零引用** ——
        # 用户完全看不到"这个版本是不是经常崩"。
        self._add_action(self.help_menu, "📉 崩溃统计", None, self._show_crash_stats)
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
        try:
            self._build_ui_language_menu()
            self._translate_menu_titles()
        except Exception:
            pass

    def refresh_feature_menu(self):
        """重新填充「特色功能」里的插件命令子菜单

        为什么需要：插件在窗口构造之后加载（`main.py` 的 deferred_init），
        构造时 `act_mgr.actions` 里还没有 `plugin.*` 条目。若只在构造时列
        一次，用户会看到"（该插件未注册命令）"的假象。
        """
        try:
            if getattr(self, "feature_menu", None) is None:
                return
        except Exception:
            return
        for title, plugin in (
            ("🤖 AI 助手（ai_assistant）", "ai_assistant"),
            ("🔀 Git（git_deep）", "git_deep"),
        ):
            try:
                sub = None
                try:
                    sub = (getattr(self, "_feature_plugin_menus", {}) or {}).get(title)
                except Exception:
                    sub = None
                if sub is None:
                    for act in self.feature_menu.actions():
                        if act.menu() and act.text() == title:
                            sub = act.menu()
                            break
                if sub is None:
                    continue
                sub.clear()
                cmds = self._plugin_commands(plugin)
                if cmds:
                    for _name, qa in cmds:
                        sub.addAction(qa)
                try:
                    # v2.19 P2：无命令时隐藏整个子菜单，不显示禁用占位项
                    sub.menuAction().setVisible(bool(cmds))
                except Exception:
                    pass
            except Exception as e:
                if logger is not None:
                    logger.debug("刷新特色功能菜单失败(%s): %s", plugin, e)
        try:
            self._sync_feature_plugin_visibility()
        except Exception:
            pass

    def _build_panel_menu(self):
        """构建面板切换子菜单"""
        panels = [
            ("大纲", "panel.outline", self._toggle_outline),
            ("大纲（增强）", "panel.outline_enhanced", self._toggle_outline_enhanced),
            ("目录树", "panel.directory", self._toggle_directory),
            ("Minimap", "panel.minimap", self._toggle_minimap),
            ("全局搜索", "panel.global_search", self._toggle_global_search),
            ("Python 控制台", "panel.console", self._toggle_console),
            # v2.21 P1-1：终端面板（Ctrl+Shift+`，避开 Python 控制台的 Ctrl+`）
            ("终端", "panel.terminal", self._toggle_terminal),
            ("插件", "panel.plugins", self._toggle_plugins_panel),
            ("性能监控", "panel.perf_monitor", self._toggle_perf_monitor),
            # 问题面板：显示 LSP 诊断（生产者在 core/editor.py 的
            # _publish_problems 里写入 ProblemManager）
            ("问题", "panel.problems", self._toggle_problems_panel),
            # 本轮接线：LSP 状态/安装向导 + 撤销历史（此前零实例化）
            ("LSP 状态", "panel.lsp", self._toggle_lsp_panel),
            ("撤销历史", "panel.undo_history", self._toggle_undo_history_panel),
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
            self.theme_menu, "跟随系统", None, lambda: self._apply_theme_by_name("__system__")
        )

        self.theme_menu.addSeparator()

        # 动态扫描 themes/
        # v2.19 修复：本文件位于 ui/mixins/，主题目录在仓库根
        themes_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "themes"
        )
        if os.path.isdir(themes_dir):
            for f in sorted(os.listdir(themes_dir)):
                if f.endswith(".json"):
                    name = os.path.splitext(f)[0]
                    # B(主题): 菜单显示 display_name
                    # 读取 display_name 用于展示，name 保留给回调用
                    display = name
                    try:
                        import json as _json

                        with open(os.path.join(themes_dir, f), encoding="utf-8") as _fp:
                            _data = _json.load(_fp)
                        display = _data.get("display_name", name)
                    except Exception:
                        pass
                    self._add_action(
                        self.theme_menu,
                        display,
                        None,
                        lambda checked=False, n=name: self._apply_theme_by_name(n),
                    )

        self.theme_menu.addSeparator()

        # 编辑 / 市场 / 导入 / 导出 / 删除
        self._add_action(self.theme_menu, "📝 编辑当前主题...", None, self._show_theme_editor)
        self._add_action(self.theme_menu, "🎨 主题市场...", None, self._show_theme_market)
        self.theme_menu.addSeparator()
        self._add_action(self.theme_menu, "📥 导入主题包...", None, self._import_theme_pack)
        self._add_action(self.theme_menu, "📤 导出当前主题...", None, self._export_theme_pack)
        self.theme_menu.addSeparator()
        self._add_action(self.theme_menu, "📁 打开主题目录", None, self._open_theme_dir)

    def _find_settings_menu(self):
        """查找「设置」顶级菜单（兼容标准/NPP 两种布局）"""
        try:
            for act in self.menuBar().actions():
                if act.menu() and ("设置" in act.text() or "Settings" in act.text()):
                    return act.menu()
        except Exception:
            pass
        return None

    def _build_ui_language_menu(self):
        """设置 → 界面语言（v2.19 P1-2 首批 i18n 落地）"""
        if getattr(self, "_ui_language_menu", None) is not None:
            return
        try:
            settings_menu = self._find_settings_menu()
            if settings_menu is None:
                return
            from PyQt5.QtWidgets import QActionGroup

            menu = settings_menu.addMenu(_tr_menu("🌐 界面语言"))
            group = QActionGroup(self)
            group.setExclusive(True)
            current = _i18n_lang()
            for code, label in _I18N_LANGS.items():
                act = menu.addAction(label)
                act.setCheckable(True)
                act.setChecked(code == current)
                act.triggered.connect(lambda checked=False, c=code: self._set_ui_language(c))
                group.addAction(act)
            self._ui_language_group = group
            self._ui_language_menu = menu
        except Exception as e:
            if "logger" in globals():
                logger.debug("构建界面语言菜单失败: %s", e)

    def _set_ui_language(self, code: str):
        """切换界面语言（持久化，重启后生效）"""
        ok = _i18n_set_language(code)
        if ok:
            QMessageBox.information(self, _tr_menu("界面语言"), _tr_menu("重启后生效"))

    def _translate_menu_titles(self):
        """翻译菜单标题与全部菜单动作（加速键/emoji 智能匹配）"""
        try:
            for act in self.menuBar().actions():
                menu = act.menu()
                if menu is not None:
                    menu.setTitle(_tr_menu(menu.title()))
        except Exception:
            pass
        # 很多菜单项是直接 QAction 创建（未走 _add_action），统一翻译一次
        try:
            from PyQt5.QtWidgets import QAction

            for act in self.findChildren(QAction):
                text = act.text()
                if not text:
                    continue
                translated = _tr_menu(text)
                if translated != text:
                    act.setText(translated)
        except Exception:
            pass

    def _add_action(
        self,
        menu: QMenu,
        text: str,
        shortcut: Optional[str],
        slot,
        action_name: Optional[str] = None,
    ) -> QAction:
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
        action = QAction(_tr_menu(text), self)
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
                    key,
                    previous.text(),
                    action.text(),
                )
                return
            owners[key] = action
        except Exception as e:
            logger.warning("快捷键重复检测失败: %s", e)

    def _on_lsp_code_actions(self, actions: list):
        """代码操作 → 选单，选中后报告（应用留待后续）"""
        try:
            titles = [a.get("title") or "" for a in (actions or [])]
            titles = [t for t in titles if t]
            if not titles:
                self.status_bar.showMessage("此处没有可用的代码操作", 4000)
                return
            from PyQt5.QtWidgets import QInputDialog

            choice, ok = QInputDialog.getItem(
                self, "代码操作", "选择要执行的操作:", titles, 0, False
            )
            if ok and choice:
                self.status_bar.showMessage("已选择代码操作：%s（应用尚未实现）" % choice, 8000)
        except Exception as e:
            logger.debug("显示代码操作失败: %s", e)

    def _lsp_code_actions(self):
        proxy = self._with_proxy("code_actions", "代码操作")
        if proxy is not None:
            proxy.code_actions()

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
        toolbar.addAction(self._toolbar_action("全局搜索", self._show_global_search))
        toolbar.addSeparator()

        # 列模式（P8-1: 与"视图 → 列模式"共用同一个 QAction。
        # 全窗口只保留**一处** Alt+C 绑定，避免 Qt 的
        # ambiguous shortcut overload 导致按键完全无响应。）
        if getattr(self, "column_mode_action", None) is None:
            # 兜底：万一 _build_menus 未执行（只需工具栏的场景）
            self.column_mode_action = QAction("列模式", self)
            self.column_mode_action.setCheckable(True)
            self.column_mode_action.setShortcut(QKeySequence("Alt+C"))
            self.column_mode_action.toggled.connect(self._toggle_column_mode)
            self._register_action_shortcut(self.column_mode_action)
        toolbar.addAction(self.column_mode_action)

        # 命令面板
        toolbar.addAction(self._toolbar_action("命令面板", self._show_command_palette))

    def _toolbar_action(self, text: str, slot) -> QAction:
        """创建工具栏动作"""
        action = QAction(text, self)
        action.triggered.connect(slot)
        return action

    def _build_npp_style_menus(self):
        """新增「搜索 / 宏 / 运行 / 窗口」顶级菜单（对齐 Notepad++）

        设计原则（**不破坏**现有快捷键与旧入口）：
        * 新菜单项**不绑定快捷键**（调用 `_add_action(..., None, cb)`），
          原 QAction 仍是唯一快捷键入口 → 不会出现
          "ambiguous shortcut overload"；
        * 旧菜单位置保持不变，命令面板仍可搜索全部动作；
        * 「窗口」菜单复用面板菜单里已有的 QAction（QAction 可同时出现在
          多个菜单，不会夺走原菜单项）；
        * 菜单通过 `insertMenu` 插到「帮助」之前，符合 NPP 习惯顺序。
        """
        try:
            from PyQt5.QtWidgets import QMenu

            menubar = self.menuBar()
            help_menu = getattr(self, "help_menu", None)

            def _insert(menu):
                if help_menu is not None:
                    # QMenuBar.insertMenu 的第一个参数是 QAction
                    menubar.insertMenu(help_menu.menuAction(), menu)
                else:
                    menubar.addMenu(menu)
                return menu

            # ---- 搜索(&S) ----
            m = _insert(QMenu("搜索(&S)", self))
            self.npp_search_menu = m
            self._add_action(m, "🔍 查找(&F)", None, self._show_search)
            self._add_action(m, "🗂 在文件中查找", None, self._show_global_search)
            self._add_action(m, "⌨ 跳转到行…", None, self._show_line_palette)
            m.addSeparator()
            self._add_action(m, "🎛 命令面板", None, self._show_command_palette)
            self._add_action(m, "📄 打开文件（模糊匹配）", None, self._show_file_palette)
            self._add_action(m, "🔣 跳转到符号", None, self._show_symbol_palette)

            # ---- 宏(&M) ----
            m = _insert(QMenu("宏(&M)", self))
            self.npp_macro_menu = m
            self._add_action(m, "⏺ 开始/停止录制宏", None, self._toggle_macro)
            self._add_action(m, "▶ 回放宏", None, self._play_macro)

            # ---- 运行(&R) ----
            m = _insert(QMenu("运行(&R)", self))
            self.npp_run_menu = m
            self._add_action(m, "▶ 运行当前文件", None, self._run_current_file)
            debug_run = getattr(self, "_debug_run", None)
            if callable(debug_run):
                self._add_action(m, "🐞 调试运行", None, debug_run)

            # ---- 窗口(&W) ----
            m = _insert(QMenu("窗口(&W)", self))
            self.npp_window_menu = m
            panel_menu = getattr(self, "panel_menu", None)
            if panel_menu is not None:
                for act in panel_menu.actions():
                    if act.isSeparator() or act.menu() is not None:
                        continue
                    m.addAction(act)
            m.addSeparator()
            self._add_action(m, "🖥 无干扰模式", None, self.toggle_distraction_free)
            self._add_action(m, "⛶ 全屏", None, self.toggle_fullscreen)

            # ---- 编码(&C)（NPP 习惯：编码/换行符集中）----
            m = _insert(QMenu("编码(&C)", self))
            self.npp_encoding_menu = m
            try:
                from ui.status_bar_widgets import ENCODINGS, LINE_ENDINGS

                self._npp_encoding_actions = []
                for name, code in ENCODINGS:
                    act = self._add_action(
                        m, name, None, lambda c=code: self._on_encoding_changed(c)
                    )
                    act.setCheckable(True)
                    self._npp_encoding_actions.append((str(code), act))
                m.aboutToShow.connect(self._sync_encoding_menu_checks)
                m.addSeparator()
                eol_menu = m.addMenu("换行符")
                self._npp_eol_actions = []
                for name, code in LINE_ENDINGS:
                    act = self._add_action(
                        eol_menu, name, None, lambda c=code: self._on_eol_changed(c)
                    )
                    act.setCheckable(True)
                    self._npp_eol_actions.append((code, act))
                eol_menu.aboutToShow.connect(self._sync_encoding_menu_checks)
            except Exception as e:
                print(f"[MainWindow] 构建编码菜单失败: {e}")

            # ---- 语言(&L)（内置映射 + 声明式语言包）----
            m = _insert(QMenu("语言(&L)", self))
            self.npp_language_menu = m
            self._npp_language_actions = []
            self._npp_language_auto_action = self._add_action(
                m, "自动（按扩展名）", None, self._apply_language_by_extension
            )
            self._npp_language_auto_action.setCheckable(True)
            try:
                from core.language_pack import get_packs

                packs = {}
                for _ext, pack in get_packs().items():
                    packs[pack.name] = pack
                if packs:
                    m.addSeparator()
                for name in sorted(packs):
                    act = self._add_action(
                        m, name, None, lambda p=packs[name]: self._apply_language_pack(p)
                    )
                    act.setCheckable(True)
                    self._npp_language_actions.append((name, act))
                m.aboutToShow.connect(self._sync_language_menu_checks)
            except Exception as e:
                print(f"[MainWindow] 构建语言菜单失败: {e}")

            # ---- 设置(&O)：首选项/快捷键/主题/配置/语言包目录 ----
            m = _insert(QMenu("设置(&O)", self))
            self.npp_settings_menu = m
            self._add_action(m, "⚙ 首选项…", None, self._show_preferences)
            self._add_action(m, "⌨ 快捷键一览…", None, self._show_shortcuts)
            self._add_action(m, "⌨ 快捷键编辑器（方案）…", None, self._show_keymap_editor)
            m.addSeparator()
            self._add_action(m, "🎨 主题编辑器…", None, self._show_theme_editor)
            self._add_action(m, "🎨 主题市场…", None, self._show_theme_market)
            self._add_action(m, "📥 导入主题包…", None, self._import_theme_pack)
            self._add_action(m, "📤 导出主题包…", None, self._export_theme_pack)
            self._add_action(m, "📂 打开主题目录", None, self._open_theme_dir)
            m.addSeparator()
            self._add_action(m, "📥 导入配置…", None, self._import_config)
            self._add_action(m, "📤 导出配置…", None, self._export_config)
            self._add_action(m, "📂 打开语言包目录", None, self._open_language_packs_dir)

            # 文件菜单补打印入口（NPP 对齐）
            file_menu = getattr(self, "file_menu", None)
            if file_menu is not None:
                file_menu.addSeparator()
                self._add_action(file_menu, "🖨 打印…", None, self._print_document)
                self._add_action(file_menu, "👁 打印预览…", None, self._print_preview)

            # 视图菜单追加「显示欢迎页」开关（checkable，无快捷键）
            try:
                from PyQt5.QtWidgets import QAction

                view_menu = getattr(self, "view_menu", None)
                if view_menu is not None:
                    act = QAction("🏠 显示欢迎页", self)
                    act.setCheckable(True)
                    act.setChecked(bool(self.prefs.get("show_welcome_page", True)))
                    act.toggled.connect(self._set_welcome_page_enabled)
                    view_menu.addSeparator()
                    view_menu.addAction(act)
                    self.welcome_page_action = act

                    tb_act = QAction("🧰 工具栏图标模式", self)
                    tb_act.setCheckable(True)
                    tb_act.setChecked(bool(self.prefs.get("toolbar_icon_mode", False)))
                    tb_act.toggled.connect(self._set_toolbar_icon_mode)
                    view_menu.addAction(tb_act)
                    self.toolbar_icon_action = tb_act
                    if tb_act.isChecked():
                        self._set_toolbar_icon_mode(True)
            except Exception as e:
                print(f"[MainWindow] 欢迎页开关失败: {e}")

            tools_menu = getattr(self, "tools_menu", None)
            if tools_menu is not None:
                tools_menu.addSeparator()
                self._add_action(
                    tools_menu, "🧪 运行沙箱插件诊断", None, self.run_sandboxed_diagnostics
                )
                self._add_action(
                    tools_menu, "🧹 忽略沙箱诊断中的可疑词", None, self.ignore_sandboxed_diagnostics
                )
                live = QAction("⚡ 实时沙箱诊断（停止输入 500ms）", self)
                live.setCheckable(True)
                live.setChecked(self._sandbox_live_enabled())
                live.toggled.connect(self._set_sandbox_live_diagnostics)
                tools_menu.addAction(live)
                hc_act = QAction("♿ 跟随系统高对比度", self)
                hc_act.setCheckable(True)
                hc_act.setChecked(self._follow_system_high_contrast())
                hc_act.toggled.connect(self._set_follow_system_high_contrast)
                tools_menu.addAction(hc_act)
        except Exception as e:
            print(f"[MainWindow] 构建 NPP 式菜单失败: {e}")
        try:
            self._start_instance_broadcast()
        except Exception:
            pass
        try:
            self._build_ui_language_menu()
            self._translate_menu_titles()
        except Exception:
            pass

    def _sync_encoding_menu_checks(self):
        """编码/EOL 菜单显示当前选中项（NPP 打对号行为）"""
        try:
            proxy = self.tabs.current_proxy()
            enc = "utf-8"
            eol = "\n"
            if proxy is not None and getattr(proxy, "document", None):
                enc = (proxy.document.encoding or "utf-8").lower()
                meta = getattr(proxy.document, "meta", None)
                if meta is not None:
                    eol = getattr(meta, "eol", "\n") or "\n"
            for code, act in getattr(self, "_npp_encoding_actions", []):
                act.setChecked(code.lower() == enc)
            for code, act in getattr(self, "_npp_eol_actions", []):
                act.setChecked(code == eol)
        except Exception:
            pass

    def _sync_language_menu_checks(self):
        """语言菜单显示当前选中项（自动/语言包）"""
        try:
            active = getattr(self, "_active_language_pack_name", None)
            auto = getattr(self, "_npp_language_auto_action", None)
            if auto is not None:
                auto.setChecked(active is None)
            for name, act in getattr(self, "_npp_language_actions", []):
                act.setChecked(name == active)
        except Exception:
            pass

    def _set_toolbar_icon_mode(self, enabled: bool):
        """视图 → 工具栏图标模式（NPP 风格小图标；持久化偏好）"""
        toolbar = getattr(self, "toolbar", None)
        if toolbar is None:
            return
        enabled = bool(enabled)
        try:
            self.prefs.set("toolbar_icon_mode", enabled)
        except Exception:
            pass
        from PyQt5.QtCore import Qt as _Qt

        for act in toolbar.actions():
            if act.isSeparator() or act.menu() is not None:
                continue
            text = act.text()
            if not text and not act.property("qc_orig_text"):
                continue
            orig = act.property("qc_orig_text") or text
            if not act.property("qc_orig_text"):
                act.setProperty("qc_orig_text", orig)
            if enabled:
                if act.icon().isNull():
                    act.setIcon(self._build_emoji_icon(orig))
                act.setToolTip(orig)
                act.setText("")
            else:
                act.setText(orig)
        toolbar.setToolButtonStyle(_Qt.ToolButtonIconOnly if enabled else _Qt.ToolButtonTextOnly)

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
