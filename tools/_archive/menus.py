#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为菜单构建模块，包含：
- MenuBuilder：完整的菜单栏构建器
- 文件菜单（新建/打开/保存/另存为/最近文件/项目/退出）
- 编辑菜单（撤销/重做/剪切/复制/粘贴/查找/替换/全局搜索）
- 视图菜单（列模式/无干扰/分屏/Minimap/大纲/面板切换/主题）
- 工具菜单（宏/插件市场/配置导入导出/编码转换/文件关联）
- 帮助菜单（使用指南/快捷键/每日技巧/关于/检查更新）
- 最近文件管理
- 动态菜单项更新
- 右键上下文菜单

修复记录:
- _apply_system_theme: 使用 QPalette 而非 Qt 6.5+ 的 styleHints
- _save_file_as: 通过 document.save(path) 而非直接改 _path
- _toggle_directory / _toggle_minimap: 使用具名 dock 引用
- _execute_theme_item (在 command_palette.py) 修复 theme 属性访问
"""

import os
import sys
import json
import subprocess
from typing import Optional, List, Dict, Callable

from PyQt5.QtWidgets import (
    QFileDialog, QAction, QMenu, QMessageBox, QInputDialog,
    QDialog, QVBoxLayout, QLabel, QPushButton, QTextBrowser,
    QStyle, QApplication, QWidget, QHBoxLayout, QCheckBox,
    QDialogButtonBox, QComboBox, QLineEdit, QDockWidget
)
from PyQt5.QtGui import QKeySequence, QDesktopServices, QIcon, QPalette
from PyQt5.QtCore import QSettings, Qt, QUrl, QTimer

from app.actions import create_action, get_standard_icon
from app.event_bus import (
    bus, FileOpenedEvent, StatusMessageEvent, NotificationEvent,
    FileSavedEvent, FileClosedEvent
)


# ============================================================
# 常量
# ============================================================
RECENT_FILES_KEY = "recent_files"
RECENT_PROJECTS_KEY = "recent_projects"
MAX_RECENT_FILES = 15
MAX_RECENT_PROJECTS = 10

GITHUB_URL = "https://github.com/qingcao-editor/qingcao"
DOCS_URL = "https://qingcao-editor.github.io/docs"
ISSUES_URL = "https://github.com/qingcao-editor/qingcao/issues"
DONATE_URL = "https://afdian.net/@qingcao"


# ============================================================
# 菜单构建器
# ============================================================
class MenuBuilder:
    """
    菜单构建器。

    负责构建主窗口的完整菜单栏，并管理所有菜单动作。
    支持：
    - 标准菜单（文件/编辑/视图/工具/帮助）
    - 动态最近文件/最近项目列表
    - 主题切换子菜单
    - 编码切换子菜单
    - 面板显示切换
    """

    def __init__(self, win, act_mgr):
        """
        参数:
            win: 主窗口实例（MainWindow）
            act_mgr: ActionManager 实例
        """
        self.win = win
        self.act_mgr = act_mgr
        self.settings = QSettings("QingCao", "Editor")

        # 最近文件列表
        self.recent_files: List[str] = []
        # 最近项目列表
        self.recent_projects: List[str] = []
        # 最近文件的动态动作列表（用于清理旧项）
        self._recent_file_actions: List[QAction] = []
        self._recent_project_actions: List[QAction] = []

        # 主题动作列表
        self._theme_actions: List[QAction] = []
        # 编码动作列表
        self._encoding_actions: List[QAction] = []
        # 面板切换动作列表
        self._panel_actions: List[QAction] = []

        # 菜单引用
        self.file_menu: Optional[QMenu] = None
        self.edit_menu: Optional[QMenu] = None
        self.view_menu: Optional[QMenu] = None
        self.tools_menu: Optional[QMenu] = None
        self.help_menu: Optional[QMenu] = None

        # 子菜单引用
        self.recent_menu: Optional[QMenu] = None
        self.recent_project_menu: Optional[QMenu] = None
        self.theme_menu: Optional[QMenu] = None
        self.encoding_menu: Optional[QMenu] = None
        self.panel_menu: Optional[QMenu] = None
        self.macro_menu: Optional[QMenu] = None

        # 构建菜单
        self._build()

        # 加载持久化的最近列表
        self._load_recent()

        # 更新最近文件菜单
        self._update_recent_menu()
        self._update_recent_project_menu()

        # 连接事件总线
        self._connect_events()

    # --------------------------------------------------------
    # 主构建方法
    # --------------------------------------------------------
    def _build(self):
        """构建整个菜单栏"""
        menubar = self.win.menuBar()

        # 构建各菜单
        self._build_file_menu(menubar)
        self._build_edit_menu(menubar)
        self._build_view_menu(menubar)
        self._build_tools_menu(menubar)
        self._build_help_menu(menubar)

    # --------------------------------------------------------
    # 文件菜单
    # --------------------------------------------------------
    def _build_file_menu(self, menubar):
        """构建文件菜单"""
        f = menubar.addMenu("文件(&F)")
        self.file_menu = f

        # 新建
        act = create_action(
            self.win, "file.new", "📄 新建(&N)", "Ctrl+N",
            self._new_file, self.act_mgr,
            icon="file-plus"
        )
        f.addAction(act)

        # 新窗口
        act = create_action(
            self.win, "file.new_window", "🗔 新窗口", "Ctrl+Shift+N",
            self._new_window, self.act_mgr,
            icon="window"
        )
        f.addAction(act)

        f.addSeparator()

        # 打开
        act = create_action(
            self.win, "file.open", "📂 打开(&O)...", "Ctrl+O",
            self._open_file, self.act_mgr,
            icon="folder-open"
        )
        f.addAction(act)

        # 打开项目
        act = create_action(
            self.win, "file.open_project", "📁 打开项目...", "Ctrl+Shift+O",
            self._open_project, self.act_mgr,
            icon="folder"
        )
        f.addAction(act)

        # 最近文件子菜单
        self.recent_menu = f.addMenu("🕐 最近文件")
        self.recent_menu.setObjectName("recent_files_menu")

        # 最近项目子菜单
        self.recent_project_menu = f.addMenu("📁 最近项目")
        self.recent_project_menu.setObjectName("recent_projects_menu")

        f.addSeparator()

        # 保存
        act = create_action(
            self.win, "file.save", "💾 保存(&S)", "Ctrl+S",
            self._save_file, self.act_mgr,
            icon="save"
        )
        f.addAction(act)

        # 另存为
        act = create_action(
            self.win, "file.save_as", "💾 另存为(&A)...", "Ctrl+Shift+S",
            self._save_file_as, self.act_mgr,
            icon="save"
        )
        f.addAction(act)

        # 保存全部
        act = create_action(
            self.win, "file.save_all", "💾 全部保存", "Ctrl+Alt+S",
            self._save_all, self.act_mgr,
            icon="save-all"
        )
        f.addAction(act)

        f.addSeparator()

        # 重新加载
        act = create_action(
            self.win, "file.reload", "🔄 重新加载", "Ctrl+R",
            self._reload_file, self.act_mgr,
            icon="refresh"
        )
        f.addAction(act)

        # 关闭标签
        act = create_action(
            self.win, "file.close_tab", "❌ 关闭标签", "Ctrl+W",
            self._close_tab, self.act_mgr,
            icon="close"
        )
        f.addAction(act)

        # 关闭所有标签
        act = create_action(
            self.win, "file.close_all", "❌ 关闭所有标签", "Ctrl+Shift+W",
            self._close_all, self.act_mgr
        )
        f.addAction(act)

        # 恢复关闭的标签
        act = create_action(
            self.win, "file.restore_closed", "↩ 恢复关闭的标签", "Ctrl+Shift+T",
            self._restore_closed_tab, self.act_mgr
        )
        f.addAction(act)

        f.addSeparator()

        # 项目相关
        act = create_action(
            self.win, "file.save_project", "💼 保存项目", "Ctrl+Alt+P",
            self._save_project, self.act_mgr
        )
        f.addAction(act)

        act = create_action(
            self.win, "file.close_project", "📁 关闭项目",
            None, self._close_project, self.act_mgr
        )
        f.addAction(act)

        f.addSeparator()

        # 打印
        act = create_action(
            self.win, "file.print", "🖨 打印...", "Ctrl+P",
            self._print, self.act_mgr,
            icon="print"
        )
        f.addAction(act)

        f.addSeparator()

        # 退出
        act = create_action(
            self.win, "file.exit", "🚪 退出(&X)", "Ctrl+Q",
            self.win.close, self.act_mgr,
            icon="exit"
        )
        f.addAction(act)

    # --------------------------------------------------------
    # 编辑菜单
    # --------------------------------------------------------
    def _build_edit_menu(self, menubar):
        """构建编辑菜单"""
        e = menubar.addMenu("编辑(&E)")
        self.edit_menu = e

        # 撤销
        act = create_action(
            self.win, "edit.undo", "↩ 撤销(&U)", "Ctrl+Z",
            self._undo, self.act_mgr,
            icon="undo"
        )
        e.addAction(act)

        # 重做
        act = create_action(
            self.win, "edit.redo", "↪ 重做(&R)", "Ctrl+Y",
            self._redo, self.act_mgr,
            icon="redo"
        )
        e.addAction(act)

        e.addSeparator()

        # 剪切
        act = create_action(
            self.win, "edit.cut", "✂ 剪切(&T)", "Ctrl+X",
            self._cut, self.act_mgr,
            icon="cut"
        )
        e.addAction(act)

        # 复制
        act = create_action(
            self.win, "edit.copy", "📋 复制(&C)", "Ctrl+C",
            self._copy, self.act_mgr,
            icon="copy"
        )
        e.addAction(act)

        # 粘贴
        act = create_action(
            self.win, "edit.paste", "📋 粘贴(&P)", "Ctrl+V",
            self._paste, self.act_mgr,
            icon="paste"
        )
        e.addAction(act)

        # 删除
        act = create_action(
            self.win, "edit.delete", "🗑 删除", "Del",
            self._delete, self.act_mgr,
            icon="trash"
        )
        e.addAction(act)

        e.addSeparator()

        # 全选
        act = create_action(
            self.win, "edit.select_all", "全选(&A)", "Ctrl+A",
            self._select_all, self.act_mgr
        )
        e.addAction(act)

        # 复制整行
        act = create_action(
            self.win, "edit.duplicate_line", "📋 复制整行", "Ctrl+Shift+D",
            self._duplicate_line, self.act_mgr
        )
        e.addAction(act)

        # 移动行
        act = create_action(
            self.win, "edit.move_line_up", "⬆ 上移行", "Ctrl+Shift+Up",
            self._move_line_up, self.act_mgr
        )
        e.addAction(act)

        act = create_action(
            self.win, "edit.move_line_down", "⬇ 下移行", "Ctrl+Shift+Down",
            self._move_line_down, self.act_mgr
        )
        e.addAction(act)

        e.addSeparator()

        # 多光标
        act = create_action(
            self.win, "edit.select_next", "🔷 选中下一个相同项", "Ctrl+D",
            self._select_next, self.act_mgr
        )
        e.addAction(act)

        act = create_action(
            self.win, "edit.select_all_occurrences", "🔷 选中所有相同项", "Ctrl+Shift+L",
            self._select_all_occurrences, self.act_mgr
        )
        e.addAction(act)

        act = create_action(
            self.win, "edit.clear_cursors", "🔷 清除多光标", "Esc",
            self._clear_cursors, self.act_mgr
        )
        e.addAction(act)

        e.addSeparator()

        # 注释
        act = create_action(
            self.win, "edit.toggle_comment", "💬 注释/取消注释", "Ctrl+/",
            self._toggle_comment, self.act_mgr
        )
        e.addAction(act)

        # 缩进
        act = create_action(
            self.win, "edit.indent", "➡ 增加缩进", "Tab",
            self._indent, self.act_mgr
        )
        e.addAction(act)

        act = create_action(
            self.win, "edit.unindent", "⬅ 减少缩进", "Shift+Tab",
            self._unindent, self.act_mgr
        )
        e.addAction(act)

        e.addSeparator()

        # 查找
        act = create_action(
            self.win, "edit.find", "🔍 查找(&F)", "Ctrl+F",
            self._show_search, self.act_mgr,
            icon="search"
        )
        e.addAction(act)

        # 替换
        act = create_action(
            self.win, "edit.replace", "🔁 替换(&H)", "Ctrl+H",
            self._show_replace, self.act_mgr
        )
        e.addAction(act)

        # 全局搜索
        act = create_action(
            self.win, "edit.global_find", "🔎 全局搜索", "Ctrl+Shift+F",
            self._show_global_search, self.act_mgr,
            icon="search"
        )
        e.addAction(act)

        # 跳转到行
        act = create_action(
            self.win, "edit.goto_line", "📍 跳转到行...", "Ctrl+G",
            self._goto_line, self.act_mgr
        )
        e.addAction(act)

        # 跳转到符号
        act = create_action(
            self.win, "edit.goto_symbol", "🔣 跳转到符号...", "Ctrl+R",
            self._goto_symbol, self.act_mgr
        )
        e.addAction(act)

        e.addSeparator()

        # 智能操作
        act = create_action(
            self.win, "edit.calc_expression", "🧮 计算表达式", "Ctrl+Shift+E",
            self._calc_expression, self.act_mgr
        )
        e.addAction(act)

        act = create_action(
            self.win, "edit.insert_datetime", "📅 插入日期时间", "F5",
            self._insert_datetime, self.act_mgr
        )
        e.addAction(act)

        act = create_action(
            self.win, "edit.to_upper", "🔠 转为大写", "Ctrl+Shift+U",
            self._to_upper, self.act_mgr
        )
        e.addAction(act)

        act = create_action(
            self.win, "edit.to_lower", "🔡 转为小写", "Ctrl+Shift+L",
            self._to_lower, self.act_mgr
        )
        e.addAction(act)

        act = create_action(
            self.win, "edit.toggle_case", "🔤 大小写切换", None,
            self._toggle_case, self.act_mgr
        )
        e.addAction(act)

        e.addSeparator()

        # 行尾空白
        act = create_action(
            self.win, "edit.trim_whitespace", "🧹 清除行尾空白", None,
            self._trim_whitespace, self.act_mgr
        )
        e.addAction(act)

        act = create_action(
            self.win, "edit.remove_blank_lines", "🧹 删除空行", None,
            self._remove_blank_lines, self.act_mgr
        )
        e.addAction(act)

        e.addSeparator()

        # 书签
        act = create_action(
            self.win, "edit.toggle_bookmark", "🔖 切换书签", "Ctrl+F2",
            self._toggle_bookmark, self.act_mgr
        )
        e.addAction(act)

        act = create_action(
            self.win, "edit.next_bookmark", "🔖 下一书签", "F2",
            self._next_bookmark, self.act_mgr
        )
        e.addAction(act)

        act = create_action(
            self.win, "edit.prev_bookmark", "🔖 上一书签", "Shift+F2",
            self._prev_bookmark, self.act_mgr
        )
        e.addAction(act)

        act = create_action(
            self.win, "edit.clear_bookmarks", "🔖 清除所有书签", None,
            self._clear_bookmarks, self.act_mgr
        )
        e.addAction(act)

    # --------------------------------------------------------
    # 视图菜单
    # --------------------------------------------------------
    def _build_view_menu(self, menubar):
        """构建视图菜单"""
        v = menubar.addMenu("视图(&V)")
        self.view_menu = v

        # 列模式
        act = create_action(
            self.win, "view.column_mode", "▦ 列模式", "Alt+C",
            self._toggle_column_mode, self.act_mgr,
            checkable=True
        )
        v.addAction(act)

        v.addSeparator()

        # 无干扰模式
        act = create_action(
            self.win, "view.distraction_free", "🖥 无干扰模式", "F11",
            self._toggle_distraction_free, self.act_mgr,
            checkable=True
        )
        v.addAction(act)

        # 全屏
        act = create_action(
            self.win, "view.fullscreen", "⛶ 全屏", "Shift+F11",
            self._toggle_fullscreen, self.act_mgr,
            checkable=True
        )
        v.addAction(act)

        v.addSeparator()

        # 分屏
        act = create_action(
            self.win, "view.split_horizontal", "⬌ 左右分屏", "Ctrl+\\",
            self._split_horizontal, self.act_mgr
        )
        v.addAction(act)

        act = create_action(
            self.win, "view.split_vertical", "⬍ 上下分屏", "Ctrl+Shift+\\",
            self._split_vertical, self.act_mgr
        )
        v.addAction(act)

        act = create_action(
            self.win, "view.close_split", "❌ 关闭分屏", None,
            self._close_split, self.act_mgr
        )
        v.addAction(act)

        v.addSeparator()

        # 缩放
        act = create_action(
            self.win, "view.zoom_in", "🔍 放大字体", "Ctrl+=",
            self._zoom_in, self.act_mgr
        )
        v.addAction(act)

        act = create_action(
            self.win, "view.zoom_out", "🔍 缩小字体", "Ctrl+-",
            self._zoom_out, self.act_mgr
        )
        v.addAction(act)

        act = create_action(
            self.win, "view.zoom_reset", "🔍 重置字体", "Ctrl+0",
            self._zoom_reset, self.act_mgr
        )
        v.addAction(act)

        v.addSeparator()

        # 显示空白字符
        act = create_action(
            self.win, "view.show_whitespace", "显示空白字符", None,
            self._toggle_whitespace, self.act_mgr,
            checkable=True
        )
        v.addAction(act)

        # 显示行尾
        act = create_action(
            self.win, "view.show_eol", "显示行尾符", None,
            self._toggle_eol, self.act_mgr,
            checkable=True
        )
        v.addAction(act)

        # 缩进彩虹线
        act = create_action(
            self.win, "view.rainbow_indent", "缩进彩虹线", None,
            self._toggle_rainbow, self.act_mgr,
            checkable=True
        )
        v.addAction(act)

        # 自动换行
        act = create_action(
            self.win, "view.word_wrap", "自动换行", "Alt+Z",
            self._toggle_word_wrap, self.act_mgr,
            checkable=True
        )
        v.addAction(act)

        v.addSeparator()

        # 面板切换子菜单
        self.panel_menu = v.addMenu("📊 面板")
        self._build_panel_menu()

        v.addSeparator()

        # 主题子菜单
        self.theme_menu = v.addMenu("🎨 主题")
        self._build_theme_menu()

        # 编码子菜单
        self.encoding_menu = v.addMenu("🔤 编码")
        self._build_encoding_menu()

        v.addSeparator()

        # 语言子菜单
        self._build_language_menu(v)

    def _build_panel_menu(self):
        """构建面板切换子菜单"""
        panels = [
            ("大纲", "panel.outline", self._toggle_outline),
            ("目录树", "panel.directory", self._toggle_directory),
            ("Minimap", "panel.minimap", self._toggle_minimap),
            ("搜索栏", "panel.search", self._toggle_search_panel),
            ("全局搜索", "panel.global_search", self._toggle_global_search),
            ("Python 控制台", "panel.console", self._toggle_console),
            ("符号大纲", "panel.symbols", self._toggle_symbols),
            ("问题面板", "panel.problems", self._toggle_problems),
        ]
        for name, action_name, slot in panels:
            act = create_action(
                self.win, action_name, name, None, slot, self.act_mgr,
                checkable=True
            )
            self.panel_menu.addAction(act)
            self._panel_actions.append(act)

    def _build_theme_menu(self):
        """构建主题切换子菜单"""
        # 跟随系统
        act = create_action(
            self.win, "theme.system", "跟随系统", None,
            lambda: self._apply_theme("__system__"), self.act_mgr,
            checkable=True
        )
        self.theme_menu.addAction(act)
        self._theme_actions.append(act)

        self.theme_menu.addSeparator()

        # 扫描主题目录
        themes_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "themes"
        )
        if os.path.isdir(themes_dir):
            for f in sorted(os.listdir(themes_dir)):
                if f.endswith(".json"):
                    theme_name = os.path.splitext(f)[0]
                    theme_path = os.path.join(themes_dir, f)
                    act = create_action(
                        self.win, f"theme.{theme_name}", theme_name, None,
                        lambda checked=False, p=theme_path:
                        self._apply_theme(p),
                        self.act_mgr, checkable=True
                    )
                    self.theme_menu.addAction(act)
                    self._theme_actions.append(act)

        self.theme_menu.addSeparator()

        # 打开主题目录
        act = create_action(
            self.win, "theme.open_dir", "📁 打开主题目录", None,
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(themes_dir)
            ),
            self.act_mgr
        )
        self.theme_menu.addAction(act)

    def _build_encoding_menu(self):
        """构建编码切换子菜单"""
        encodings = [
            "UTF-8", "UTF-8 with BOM", "GBK", "GB2312", "GB18030",
            "Big5", "Shift-JIS", "EUC-KR", "ISO-8859-1", "Windows-1252",
            "UTF-16 LE", "UTF-16 BE", "ASCII"
        ]
        for enc in encodings:
            act = create_action(
                self.win, f"encoding.{enc}", enc, None,
                lambda checked=False, e=enc: self._change_encoding(e),
                self.act_mgr, checkable=True
            )
            self.encoding_menu.addAction(act)
            self._encoding_actions.append(act)

        self.encoding_menu.addSeparator()

        act = create_action(
            self.win, "encoding.detect", "🔍 自动检测编码", None,
            self._detect_encoding, self.act_mgr
        )
        self.encoding_menu.addAction(act)

        act = create_action(
            self.win, "encoding.convert", "🔄 转换编码...", None,
            self._convert_encoding, self.act_mgr
        )
        self.encoding_menu.addAction(act)

    def _build_language_menu(self, parent_menu):
        """构建语言切换子菜单"""
        lang_menu = parent_menu.addMenu("🌍 语言")
        languages = [
            ("简体中文", "zh_CN"),
            ("English", "en_US"),
            ("日本語", "ja_JP"),
            ("한국어", "ko_KR"),
            ("Español", "es_ES"),
        ]
        for name, code in languages:
            act = create_action(
                self.win, f"lang.{code}", name, None,
                lambda checked=False, c=code: self._change_language(c),
                self.act_mgr, checkable=True
            )
            lang_menu.addAction(act)

    # --------------------------------------------------------
    # 工具菜单
    # --------------------------------------------------------
    def _build_tools_menu(self, menubar):
        """构建工具菜单"""
        t = menubar.addMenu("工具(&T)")
        self.tools_menu = t

        # 命令面板
        act = create_action(
            self.win, "tools.command_palette", "⌨ 命令面板", "Ctrl+Shift+P",
            self._show_command_palette, self.act_mgr,
            icon="terminal"
        )
        t.addAction(act)

        # 快速打开文件
        act = create_action(
            self.win, "tools.quick_open", "📂 快速打开文件", "Ctrl+P",
            self._quick_open_file, self.act_mgr
        )
        t.addAction(act)

        t.addSeparator()

        # 宏子菜单
        self.macro_menu = t.addMenu("⏺ 宏")
        self._build_macro_menu()

        t.addSeparator()

        # 插件市场
        act = create_action(
            self.win, "tools.plugin_store", "🧩 插件市场", None,
            self._show_plugin_store, self.act_mgr,
            icon="package"
        )
        t.addAction(act)

        # 插件管理
        act = create_action(
            self.win, "tools.plugin_manager", "🔌 插件管理", None,
            self._show_plugin_manager, self.act_mgr
        )
        t.addAction(act)

        t.addSeparator()

        # 快捷键编辑器
        act = create_action(
            self.win, "tools.keymap_editor", "⌨ 快捷键编辑", None,
            self._show_keymap_editor, self.act_mgr
        )
        t.addAction(act)

        # 宏编辑器
        act = create_action(
            self.win, "tools.macro_editor", "📝 宏编辑器", None,
            self._show_macro_editor, self.act_mgr
        )
        t.addAction(act)

        t.addSeparator()

        # 配置管理
        act = create_action(
            self.win, "tools.export_config", "📤 导出配置...", None,
            self._export_config, self.act_mgr
        )
        t.addAction(act)

        act = create_action(
            self.win, "tools.import_config", "📥 导入配置...", None,
            self._import_config, self.act_mgr
        )
        t.addAction(act)

        t.addSeparator()

        # 文件关联
        act = create_action(
            self.win, "tools.file_association", "🔗 文件关联设置...", None,
            self._show_file_association, self.act_mgr
        )
        t.addAction(act)

        # 系统右键菜单
        act = create_action(
            self.win, "tools.context_menu", "🖱 添加系统右键菜单", None,
            self._install_context_menu, self.act_mgr
        )
        t.addAction(act)

        t.addSeparator()

        # 高级工具
        advanced = t.addMenu("🔧 高级工具")

        act = create_action(
            self.win, "tools.hex_editor", "🔢 十六进制视图", None,
            self._show_hex_view, self.act_mgr
        )
        advanced.addAction(act)

        act = create_action(
            self.win, "tools.terminal", "💻 集成终端", None,
            self._show_terminal, self.act_mgr
        )
        advanced.addAction(act)

        act = create_action(
            self.win, "tools.debugger", "🐞 Python 调试器", None,
            self._show_debugger, self.act_mgr
        )
        advanced.addAction(act)

        act = create_action(
            self.win, "tools.code_formatter", "✨ 代码格式化", "Ctrl+Alt+F",
            self._format_code, self.act_mgr
        )
        advanced.addAction(act)

        act = create_action(
            self.win, "tools.code_metrics", "📊 代码度量", None,
            self._show_code_metrics, self.act_mgr
        )
        advanced.addAction(act)

        act = create_action(
            self.win, "tools.inspiration_canvas", "💡 灵感画布", None,
            self._show_inspiration_canvas, self.act_mgr
        )
        advanced.addAction(act)

        t.addSeparator()

        # 开发者工具
        dev = t.addMenu("🛠 开发者")

        act = create_action(
            self.win, "tools.python_console", "🐍 Python 控制台", "Ctrl+`",
            self._show_python_console, self.act_mgr
        )
        dev.addAction(act)

        act = create_action(
            self.win, "tools.event_history", "📜 事件历史", None,
            self._show_event_history, self.act_mgr
        )
        dev.addAction(act)

        act = create_action(
            self.win, "tools.memory_stats", "💾 内存统计", None,
            self._show_memory_stats, self.act_mgr
        )
        dev.addAction(act)

        act = create_action(
            self.win, "tools.reload_plugins", "🔄 重新加载插件", None,
            self._reload_plugins, self.act_mgr
        )
        dev.addAction(act)

    def _build_macro_menu(self):
        """构建宏子菜单"""
        # 录制宏
        act = create_action(
            self.win, "macro.record", "⏺ 开始/停止录制", "Ctrl+Shift+R",
            self._toggle_macro_record, self.act_mgr,
            checkable=True
        )
        self.macro_menu.addAction(act)

        # 回放宏
        act = create_action(
            self.win, "macro.play", "▶ 回放宏", "Ctrl+Shift+P",
            self._play_macro, self.act_mgr
        )
        self.macro_menu.addAction(act)

        self.macro_menu.addSeparator()

        # 保存宏
        act = create_action(
            self.win, "macro.save", "💾 保存宏...", None,
            self._save_macro, self.act_mgr
        )
        self.macro_menu.addAction(act)

        # 加载宏
        act = create_action(
            self.win, "macro.load", "📂 加载宏...", None,
            self._load_macro, self.act_mgr
        )
        self.macro_menu.addAction(act)

        self.macro_menu.addSeparator()

        # 编辑宏
        act = create_action(
            self.win, "macro.edit", "📝 编辑宏...", None,
            self._show_macro_editor, self.act_mgr
        )
        self.macro_menu.addAction(act)

    # --------------------------------------------------------
    # 帮助菜单
    # --------------------------------------------------------
    def _build_help_menu(self, menubar):
        """构建帮助菜单"""
        h = menubar.addMenu("帮助(&H)")
        self.help_menu = h

        # 使用指南
        act = create_action(
            self.win, "help.guide", "📖 使用指南", "F1",
            self._show_help, self.act_mgr,
            icon="help"
        )
        h.addAction(act)

        # 快速入门
        act = create_action(
            self.win, "help.quickstart", "🚀 快速入门", None,
            self._show_quickstart, self.act_mgr
        )
        h.addAction(act)

        # 每日技巧
        act = create_action(
            self.win, "help.daily_tip", "💡 每日技巧", None,
            self._show_daily_tip, self.act_mgr
        )
        h.addAction(act)

        h.addSeparator()

        # 快捷键参考
        act = create_action(
            self.win, "help.shortcuts", "⌨ 快捷键参考", None,
            self._show_shortcut_reference, self.act_mgr
        )
        h.addAction(act)

        # 常见问题
        act = create_action(
            self.win, "help.faq", "❓ 常见问题", None,
            self._show_faq, self.act_mgr
        )
        h.addAction(act)

        h.addSeparator()

        # 查看日志
        act = create_action(
            self.win, "help.view_log", "📜 查看运行日志", None,
            self._view_runtime_log, self.act_mgr
        )
        h.addAction(act)

        # 查看崩溃日志
        act = create_action(
            self.win, "help.view_crash_log", "💥 查看崩溃日志", None,
            self._view_crash_log, self.act_mgr
        )
        h.addAction(act)

        h.addSeparator()

        # 在线资源
        act = create_action(
            self.win, "help.docs", "🌐 在线文档", None,
            lambda: QDesktopServices.openUrl(QUrl(DOCS_URL)), self.act_mgr
        )
        h.addAction(act)

        act = create_action(
            self.win, "help.github", "🐙 GitHub 仓库", None,
            lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)), self.act_mgr
        )
        h.addAction(act)

        act = create_action(
            self.win, "help.report_issue", "🐞 报告问题", None,
            lambda: QDesktopServices.openUrl(QUrl(ISSUES_URL)), self.act_mgr
        )
        h.addAction(act)

        h.addSeparator()

        # 检查更新
        act = create_action(
            self.win, "help.check_update", "🔄 检查更新", None,
            self._check_update, self.act_mgr
        )
        h.addAction(act)

        # 捐赠支持
        act = create_action(
            self.win, "help.donate", "❤ 捐赠支持", None,
            lambda: QDesktopServices.openUrl(QUrl(DONATE_URL)), self.act_mgr
        )
        h.addAction(act)

        h.addSeparator()

        # 成就
        act = create_action(
            self.win, "help.achievements", "🏆 我的成就", None,
            self._show_achievements, self.act_mgr
        )
        h.addAction(act)

        # 关于
        act = create_action(
            self.win, "help.about", "ℹ 关于青草", None,
            self._about, self.act_mgr
        )
        h.addAction(act)

        # 关于 Qt
        act = create_action(
            self.win, "help.about_qt", "ℹ 关于 Qt", None,
            lambda: QMessageBox.aboutQt(self.win, "关于 Qt"), self.act_mgr
        )
        h.addAction(act)

    # ========================================================
    # 文件菜单槽函数
    # ========================================================
    def _new_file(self):
        """新建文件"""
        try:
            self.win.tabs.add_tab()
        except Exception as e:
            self._show_error("新建文件失败", str(e))

    def _new_window(self):
        """打开新窗口"""
        try:
            from ui.main_window import MainWindow
            new_win = MainWindow()
            new_win.show()
        except Exception as e:
            self._show_error("新建窗口失败", str(e))

    def _open_file(self):
        """打开文件对话框"""
        try:
            paths, _ = QFileDialog.getOpenFileNames(
                self.win,
                "打开文件",
                "",
                "所有文件 (*.*);;文本文件 (*.txt);;Python (*.py);;"
                "Markdown (*.md);;JSON (*.json);;日志 (*.log)"
            )
            for path in paths:
                self.win.tabs.open_file(path)
                self._add_recent_file(path)
        except Exception as e:
            self._show_error("打开文件失败", str(e))

    def _open_project(self):
        """打开项目"""
        try:
            path, _ = QFileDialog.getOpenFileName(
                self.win, "打开项目", "",
                "青草项目 (*.qingcao-project);;所有文件 (*.*)"
            )
            if path and hasattr(self.win, 'open_project'):
                self.win.open_project(path)
                self._add_recent_project(path)
        except Exception as e:
            self._show_error("打开项目失败", str(e))

    def _save_file(self):
        """保存当前文件"""
        try:
            proxy = self.win.tabs.current_proxy()
            if proxy:
                if not proxy.document.filepath:
                    self._save_file_as()
                else:
                    proxy.save_file()
        except Exception as e:
            self._show_error("保存失败", str(e))

    def _save_file_as(self):
        """另存为"""
        try:
            proxy = self.win.tabs.current_proxy()
            if not proxy:
                return
            path, _ = QFileDialog.getSaveFileName(
                self.win, "另存为",
                proxy.document.filepath or "",
                "所有文件 (*.*)"
            )
            if path:
                # 修复：通过 document.save(path) 保存到新路径，
                # 由 Document 内部处理 meta.filepath 更新
                proxy.document.save(path)
                # 更新标签标题
                idx = self.win.tabs.currentIndex()
                self.win.tabs.setTabText(idx, os.path.basename(path))
        except Exception as e:
            self._show_error("另存为失败", str(e))

    def _save_all(self):
        """保存所有文件"""
        try:
            for i in range(self.win.tabs.count()):
                w = self.win.tabs.widget(i)
                if w.proxy.is_modified:
                    w.proxy.save_file()
        except Exception as e:
            self._show_error("保存全部失败", str(e))

    def _reload_file(self):
        """重新加载当前文件"""
        try:
            proxy = self.win.tabs.current_proxy()
            if not proxy or not proxy.document.filepath:
                return
            ret = QMessageBox.question(
                self.win, "重新加载",
                "确定放弃当前修改并重新加载文件吗？",
                QMessageBox.Yes | QMessageBox.No
            )
            if ret == QMessageBox.Yes:
                path = proxy.document.filepath
                cursor_pos = proxy.get_current_pos()
                proxy.close()
                proxy.open_file(path)
                max_pos = proxy.sc.SendScintilla(proxy.sc.SCI_GETLENGTH)
                proxy.sc.SendScintilla(
                    proxy.sc.SCI_GOTOPOS, min(cursor_pos, max_pos)
                )
        except Exception as e:
            self._show_error("重新加载失败", str(e))

    def _close_tab(self):
        """关闭当前标签"""
        try:
            idx = self.win.tabs.currentIndex()
            if idx >= 0:
                self.win.tabs.close_tab(idx)
        except Exception as e:
            self._show_error("关闭失败", str(e))

    def _close_all(self):
        """关闭所有标签"""
        try:
            for i in range(self.win.tabs.count() - 1, -1, -1):
                self.win.tabs.close_tab(i)
        except Exception as e:
            self._show_error("关闭全部失败", str(e))

    def _restore_closed_tab(self):
        """恢复最近关闭的标签"""
        try:
            if hasattr(self.win.tabs, 'restore_closed_tab'):
                self.win.tabs.restore_closed_tab()
        except Exception as e:
            self._show_error("恢复失败", str(e))

    def _save_project(self):
        """保存当前项目"""
        try:
            if hasattr(self.win, 'save_project'):
                self.win.save_project()
        except Exception as e:
            self._show_error("保存项目失败", str(e))

    def _close_project(self):
        """关闭当前项目"""
        try:
            if hasattr(self.win, 'close_project'):
                self.win.close_project()
        except Exception as e:
            self._show_error("关闭项目失败", str(e))

    def _print(self):
        """打印当前文件"""
        try:
            from PyQt5.QtPrintSupport import QPrintDialog, QPrinter
            proxy = self.win.tabs.current_proxy()
            if not proxy:
                return
            printer = QPrinter()
            dlg = QPrintDialog(printer, self.win)
            if dlg.exec() == QDialog.Accepted:
                proxy.sc.print_(printer)
        except Exception as e:
            self._show_error("打印失败", str(e))

    # ========================================================
    # 编辑菜单槽函数
    # ========================================================
    def _undo(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            proxy.undo()

    def _redo(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            proxy.redo()

    def _cut(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            proxy.sc.cut()

    def _copy(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            proxy.sc.copy()

    def _paste(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            proxy.sc.paste()

    def _delete(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            proxy.sc.SendScintilla(proxy.sc.SCI_CLEAR)

    def _select_all(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            proxy.sc.selectAll()

    def _duplicate_line(self):
        proxy = self.win.tabs.current_proxy()
        if proxy and hasattr(proxy, 'duplicate_line'):
            proxy.duplicate_line()

    def _move_line_up(self):
        proxy = self.win.tabs.current_proxy()
        if proxy and hasattr(proxy, 'move_line_up'):
            proxy.move_line_up()

    def _move_line_down(self):
        proxy = self.win.tabs.current_proxy()
        if proxy and hasattr(proxy, 'move_line_down'):
            proxy.move_line_down()

    def _select_next(self):
        proxy = self.win.tabs.current_proxy()
        if proxy and hasattr(proxy, 'select_next_occurrence'):
            proxy.select_next_occurrence()

    def _select_all_occurrences(self):
        proxy = self.win.tabs.current_proxy()
        if not proxy:
            return
        # 选中当前单词的所有出现
        word = proxy.sc.selectedText()
        if word:
            proxy.highlight_all(word)

    def _clear_cursors(self):
        proxy = self.win.tabs.current_proxy()
        if proxy and hasattr(proxy, 'clear_cursors'):
            proxy.clear_cursors()

    def _toggle_comment(self):
        proxy = self.win.tabs.current_proxy()
        if proxy and hasattr(proxy, 'toggle_line_comment'):
            proxy.toggle_line_comment()

    def _indent(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            proxy.sc.SendScintilla(proxy.sc.SCI_TAB)

    def _unindent(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            proxy.sc.SendScintilla(proxy.sc.SCI_BACKTAB)

    def _show_search(self):
        if hasattr(self.win, 'show_search'):
            self.win.show_search()

    def _show_replace(self):
        if hasattr(self.win, 'show_search'):
            self.win.show_search()
            if hasattr(self.win, 'search_bar'):
                self.win.search_bar.show()

    def _show_global_search(self):
        if hasattr(self.win, 'show_gsearch'):
            self.win.show_gsearch()

    def _goto_line(self):
        proxy = self.win.tabs.current_proxy()
        if not proxy:
            return
        max_line = proxy.sc.SendScintilla(proxy.sc.SCI_GETLINECOUNT)
        line, ok = QInputDialog.getInt(
            self.win, "跳转到行", "行号:", 1, 1, max_line
        )
        if ok:
            proxy.sc.SendScintilla(proxy.sc.SCI_GOTOLINE, line - 1)

    def _goto_symbol(self):
        try:
            from ui.command_palette import CommandPalette
            palette = CommandPalette(
                self.act_mgr, self.win,
                mode='symbol',
                tab_mgr=self.win.tabs,
                outline=getattr(self.win, 'outline', None)
            )
            palette.exec()
        except Exception as e:
            self._show_error("符号跳转失败", str(e))

    def _calc_expression(self):
        proxy = self.win.tabs.current_proxy()
        if proxy and hasattr(proxy, 'eval_expression'):
            proxy.eval_expression()

    def _insert_datetime(self):
        proxy = self.win.tabs.current_proxy()
        if proxy and hasattr(proxy, 'insert_datetime'):
            proxy.insert_datetime()

    def _to_upper(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            text = proxy.sc.selectedText()
            if text:
                proxy.sc.replaceSelectedText(text.upper())

    def _to_lower(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            text = proxy.sc.selectedText()
            if text:
                proxy.sc.replaceSelectedText(text.lower())

    def _toggle_case(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            text = proxy.sc.selectedText()
            if text:
                proxy.sc.replaceSelectedText(text.swapcase())

    def _trim_whitespace(self):
        proxy = self.win.tabs.current_proxy()
        if not proxy:
            return
        text = proxy.sc.text()
        lines = [l.rstrip() for l in text.splitlines()]
        proxy.sc.setText('\n'.join(lines))

    def _remove_blank_lines(self):
        proxy = self.win.tabs.current_proxy()
        if not proxy:
            return
        text = proxy.sc.text()
        lines = [l for l in text.splitlines() if l.strip()]
        proxy.sc.setText('\n'.join(lines))

    def _toggle_bookmark(self):
        proxy = self.win.tabs.current_proxy()
        if not proxy:
            return
        line, _ = proxy.sc.getCursorPosition()
        if proxy.sc.markersAtLine(line) & 1:
            proxy.sc.markerDelete(line, 0)
        else:
            proxy.sc.markerAdd(line, 0)

    def _next_bookmark(self):
        proxy = self.win.tabs.current_proxy()
        if not proxy:
            return
        line, _ = proxy.sc.getCursorPosition()
        next_line = proxy.sc.markerFindNext(line + 1, 1)
        if next_line >= 0:
            proxy.sc.setCursorPosition(next_line, 0)

    def _prev_bookmark(self):
        proxy = self.win.tabs.current_proxy()
        if not proxy:
            return
        line, _ = proxy.sc.getCursorPosition()
        prev_line = proxy.sc.markerFindPrevious(line - 1, 1)
        if prev_line >= 0:
            proxy.sc.setCursorPosition(prev_line, 0)

    def _clear_bookmarks(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            proxy.sc.markerDeleteAll(0)

    # ========================================================
    # 视图菜单槽函数
    # ========================================================
    def _toggle_column_mode(self, checked):
        proxy = self.win.tabs.current_proxy()
        if proxy and hasattr(proxy, 'set_column_mode'):
            proxy.set_column_mode(checked)

    def _toggle_distraction_free(self, checked):
        if hasattr(self.win, 'toggle_distraction_free'):
            self.win.toggle_distraction_free()

    def _toggle_fullscreen(self, checked):
        if checked:
            self.win.showFullScreen()
        else:
            self.win.showNormal()

    def _split_horizontal(self):
        if hasattr(self.win, 'split_view'):
            self.win.split_view(Qt.Horizontal)

    def _split_vertical(self):
        if hasattr(self.win, 'split_view'):
            self.win.split_view(Qt.Vertical)

    def _close_split(self):
        if hasattr(self.win, 'close_split'):
            self.win.close_split()

    def _zoom_in(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            proxy.sc.zoomIn()

    def _zoom_out(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            proxy.sc.zoomOut()

    def _zoom_reset(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            # 重置字体大小
            from PyQt5.QtGui import QFont
            f = proxy.sc.font()
            f.setPointSize(12)
            proxy.sc.setFont(f)

    def _toggle_whitespace(self, checked):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            if checked:
                proxy.sc.SendScintilla(proxy.sc.SCI_SETVIEWWS, 1)
            else:
                proxy.sc.SendScintilla(proxy.sc.SCI_SETVIEWWS, 0)

    def _toggle_eol(self, checked):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            if checked:
                proxy.sc.SendScintilla(proxy.sc.SCI_SETVIEWEOL, 1)
            else:
                proxy.sc.SendScintilla(proxy.sc.SCI_SETVIEWEOL, 0)

    def _toggle_rainbow(self, checked):
        proxy = self.win.tabs.current_proxy()
        if proxy and hasattr(proxy.sc, '_rainbow'):
            proxy.sc._rainbow = checked
            proxy.sc.viewport().update()

    def _toggle_word_wrap(self, checked):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            if checked:
                proxy.sc.setWrapMode(proxy.sc.WrapWord)
            else:
                proxy.sc.setWrapMode(proxy.sc.WrapNone)

    # --------------------------------------------------------
    # 修复：使用具名 dock 引用而非 __mro__ 探测
    # --------------------------------------------------------
    def _toggle_outline(self, checked):
        """切换大纲面板"""
        if hasattr(self.win, 'outline') and self.win.outline:
            self.win.outline.setVisible(checked)

    def _toggle_directory(self, checked):
        """
        切换目录树面板。

        修复：使用具名 dock 引用 self.win.dir_tree_dock
        """
        dock = getattr(self.win, 'dir_tree_dock', None)
        if dock:
            dock.setVisible(checked)

    def _toggle_minimap(self, checked):
        """
        切换 Minimap。

        修复：使用具名 dock 引用 self.win.minimap_dock
        """
        dock = getattr(self.win, 'minimap_dock', None)
        if dock:
            dock.setVisible(checked)

    def _toggle_search_panel(self, checked):
        """切换搜索栏"""
        if hasattr(self.win, 'search_bar') and self.win.search_bar:
            self.win.search_bar.setVisible(checked)

    def _toggle_global_search(self, checked):
        """切换全局搜索"""
        if hasattr(self.win, 'gsearch') and self.win.gsearch:
            self.win.gsearch.setVisible(checked)

    def _toggle_console(self, checked):
        """切换控制台"""
        if hasattr(self.win, 'console') and self.win.console:
            self.win.console.setVisible(checked)

    def _toggle_symbols(self, checked):
        """切换符号大纲"""
        self._toggle_outline(checked)

    def _toggle_problems(self, checked):
        """切换问题面板"""
        # 问题面板由 LSP 插件管理
        pass

    # --------------------------------------------------------
    # 修复：_apply_system_theme 使用 PyQt5 兼容的调色板判断
    # --------------------------------------------------------
    def _apply_theme(self, theme_path):
        """应用主题"""
        try:
            if theme_path == "__system__":
                # 跟随系统
                self._apply_system_theme()
                return
            from infrastructure.theme_loader import ThemeLoader
            loader = ThemeLoader()
            theme = loader.load(theme_path)
            if theme is None:
                return
            for i in range(self.win.tabs.count()):
                try:
                    loader.apply(self.win.tabs.widget(i), theme)
                except Exception:
                    pass
            # 修复：Theme 对象用属性访问
            qss = getattr(theme, 'qss', '')
            if qss:
                self.win.setStyleSheet(qss)
            # 保存偏好
            self.settings.setValue("theme_path", theme_path)
        except Exception as e:
            self._show_error("应用主题失败", str(e))

    def _apply_system_theme(self):
        """
        跟随系统主题（PyQt5 兼容版）。

        修复：使用 QPalette 判断明暗，而非 Qt 6.5+ 的 styleHints。
        """
        try:
            palette = QApplication.palette()
            bg = palette.color(QPalette.Window)
            is_dark = bg.lightness() < 128

            theme_file = "dark_night.json" if is_dark else "light_clean.json"
            theme_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "themes", theme_file
            )

            # 主题文件不存在时回退
            if not os.path.exists(theme_path):
                fallback = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    "themes",
                    "light_clean.json" if not is_dark else "dark_night.json"
                )
                if os.path.exists(fallback):
                    theme_path = fallback
                else:
                    print(
                        f"[MenuBuilder] 主题文件不存在: {theme_path}"
                    )
                    return

            # 用文件路径调用 _apply_theme
            from infrastructure.theme_loader import ThemeLoader
            loader = ThemeLoader()
            theme = loader.load(theme_path)
            if theme is None:
                return

            for i in range(self.win.tabs.count()):
                try:
                    loader.apply(self.win.tabs.widget(i), theme)
                except Exception:
                    pass

            # 修复：Theme 对象用属性访问
            qss = getattr(theme, 'qss', '')
            if qss:
                self.win.setStyleSheet(qss)

        except Exception as e:
            print(f"[MenuBuilder] 应用系统主题失败: {e}")

    def _change_encoding(self, encoding):
        proxy = self.win.tabs.current_proxy()
        if not proxy:
            return
        try:
            old_enc = proxy.document.encoding
            proxy.document.change_encoding(encoding)
            bus.emit_status(f"编码已切换: {old_enc} → {encoding}")
        except Exception as e:
            self._show_error("切换编码失败", str(e))

    def _detect_encoding(self):
        proxy = self.win.tabs.current_proxy()
        if proxy:
            bus.emit_status(f"当前编码: {proxy.document.encoding}")

    def _convert_encoding(self):
        proxy = self.win.tabs.current_proxy()
        if not proxy:
            return
        encodings = ["UTF-8", "GBK", "GB18030", "Big5", "Shift-JIS"]
        enc, ok = QInputDialog.getItem(
            self.win, "转换编码", "选择目标编码:", encodings, 0, False
        )
        if ok and enc:
            try:
                proxy.document.change_encoding(enc)
                proxy.save_file()
                bus.emit_success(f"已转换为 {enc}")
            except Exception as e:
                self._show_error("转换失败", str(e))

    def _change_language(self, lang_code):
        try:
            self.settings.setValue("language", lang_code)
            QMessageBox.information(
                self.win, "语言切换",
                f"语言已切换为 {lang_code}，重启编辑器后生效。"
            )
        except Exception as e:
            self._show_error("切换语言失败", str(e))

    # ========================================================
    # 工具菜单槽函数
    # ========================================================
    def _show_command_palette(self):
        try:
            from ui.command_palette import CommandPalette
            palette = CommandPalette(
                self.act_mgr, self.win,
                mode='command',
                tab_mgr=self.win.tabs,
                outline=getattr(self.win, 'outline', None)
            )
            palette.exec()
        except Exception as e:
            self._show_error("命令面板失败", str(e))

    def _quick_open_file(self):
        try:
            from ui.command_palette import CommandPalette
            palette = CommandPalette(
                self.act_mgr, self.win,
                mode='file',
                tab_mgr=self.win.tabs
            )
            palette.exec()
        except Exception as e:
            self._show_error("快速打开失败", str(e))

    def _toggle_macro_record(self, checked):
        try:
            if checked:
                self.win.macro.start()
                bus.emit_status("宏录制已开始", 2000, "info")
            else:
                self.win.macro.stop()
                bus.emit_status("宏录制已停止", 2000, "info")
        except Exception as e:
            self._show_error("宏操作失败", str(e))

    def _play_macro(self):
        try:
            proxy = self.win.tabs.current_proxy()
            if proxy and self.win.macro.commands:
                self.win.macro.replay(proxy)
            else:
                bus.emit_status("没有可回放的宏", 2000, "warning")
        except Exception as e:
            self._show_error("宏回放失败", str(e))

    def _save_macro(self):
        try:
            path, _ = QFileDialog.getSaveFileName(
                self.win, "保存宏", "", "宏文件 (*.json)"
            )
            if path:
                self.win.macro.save(path)
                bus.emit_success(f"宏已保存: {os.path.basename(path)}")
        except Exception as e:
            self._show_error("保存宏失败", str(e))

    def _load_macro(self):
        try:
            path, _ = QFileDialog.getOpenFileName(
                self.win, "加载宏", "", "宏文件 (*.json)"
            )
            if path:
                self.win.macro.load(path)
                bus.emit_success(f"宏已加载: {os.path.basename(path)}")
        except Exception as e:
            self._show_error("加载宏失败", str(e))

    def _show_macro_editor(self):
        try:
            from ui.macro_editor import MacroEditor
            dlg = MacroEditor(self.win.macro, self.act_mgr, self.win)
            dlg.exec()
        except Exception as e:
            self._show_error("宏编辑器失败", str(e))

    def _show_plugin_store(self):
        try:
            from ui.plugin_store import PluginStoreDialog
            dlg = PluginStoreDialog(self.win)
            dlg.exec()
        except Exception as e:
            self._show_error("插件市场失败", str(e))

    def _show_plugin_manager(self):
        try:
            from ui.plugin_store import PluginStoreDialog
            dlg = PluginStoreDialog(self.win)
            dlg.exec()
        except Exception as e:
            self._show_error("插件管理失败", str(e))

    def _show_keymap_editor(self):
        try:
            from ui.keymap_editor import KeymapEditor
            dlg = KeymapEditor(self.act_mgr, self.win)
            dlg.exec()
        except Exception as e:
            self._show_error("快捷键编辑器失败", str(e))

    def _export_config(self):
        try:
            path, _ = QFileDialog.getSaveFileName(
                self.win, "导出配置", "qingcao_config.zip", "ZIP (*.zip)"
            )
            if not path:
                return
            from app.config_manager import ConfigManager
            cm = ConfigManager()
            cm.export_config(self.win, path)
        except Exception as e:
            self._show_error("导出配置失败", str(e))

    def _import_config(self):
        try:
            path, _ = QFileDialog.getOpenFileName(
                self.win, "导入配置", "", "ZIP (*.zip)"
            )
            if not path:
                return
            from app.config_manager import ConfigManager
            cm = ConfigManager()
            cm.import_config(self.win, path)
        except Exception as e:
            self._show_error("导入配置失败", str(e))

    def _show_file_association(self):
        try:
            from ui.file_association import FileAssociationDialog
            dlg = FileAssociationDialog(self.win)
            dlg.exec()
        except Exception as e:
            self._show_error("文件关联失败", str(e))

    def _install_context_menu(self):
        """安装系统右键菜单"""
        try:
            if sys.platform == 'win32':
                self._install_windows_context_menu()
            elif sys.platform == 'darwin':
                bus.emit_status(
                    "macOS 暂不支持自动安装右键菜单", 3000, "warning"
                )
            else:
                self._install_linux_context_menu()
        except Exception as e:
            self._show_error("安装右键菜单失败", str(e))

    def _install_windows_context_menu(self):
        """Windows 下安装右键菜单"""
        import winreg
        exe_path = sys.executable
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
        try:
            key_path = r"*\shell\QingCao"
            key = winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, key_path)
            winreg.SetValue(key, "", winreg.REG_SZ, "通过青草编辑器打开")
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ,
                              f"{exe_path},0")
            winreg.CloseKey(key)

            cmd_path = r"*\shell\QingCao\command"
            cmd_key = winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, cmd_path)
            winreg.SetValue(cmd_key, "", winreg.REG_SZ,
                            f'"{exe_path}" "%1"')
            winreg.CloseKey(cmd_key)
            bus.emit_success("系统右键菜单已添加")
        except PermissionError:
            self._show_error("权限不足", "请以管理员身份运行后再试")

    def _install_linux_context_menu(self):
        """Linux 下安装右键菜单（需手动配置）"""
        bus.emit_status(
            "请参考文档手动配置 Linux 右键菜单", 5000, "info"
        )

    def _show_hex_view(self):
        try:
            proxy = self.win.tabs.current_proxy()
            if proxy and hasattr(proxy, 'toggle_hex'):
                proxy.toggle_hex()
        except Exception as e:
            self._show_error("十六进制视图失败", str(e))

    def _show_terminal(self):
        try:
            if hasattr(self.win, 'terminal'):
                self.win.terminal.setVisible(True)
        except Exception as e:
            self._show_error("终端失败", str(e))

    def _show_debugger(self):
        try:
            from ui.debug_panel import DebugPanel
            panel = DebugPanel(self.win)
            self.win.addDockWidget(Qt.BottomDockWidgetArea, panel)
            panel.show()
        except ImportError:
            bus.emit_status("调试器插件未安装", 3000, "warning")
        except Exception as e:
            self._show_error("调试器失败", str(e))

    def _format_code(self):
        """格式化代码"""
        try:
            proxy = self.win.tabs.current_proxy()
            if not proxy:
                return
            # 尝试通过插件格式化
            for plugin in getattr(self.win, 'plugins', []):
                if hasattr(plugin, 'format_code'):
                    plugin.format_code()
                    return
            bus.emit_status("未找到可用的格式化插件", 3000, "warning")
        except Exception as e:
            self._show_error("格式化失败", str(e))

    def _show_code_metrics(self):
        try:
            from plugins.code_metrics import CodeMetricsPlugin
            plugin = CodeMetricsPlugin()
            plugin.api = self.win.api
            plugin.show_metrics()
        except Exception as e:
            self._show_error("代码度量失败", str(e))

    def _show_inspiration_canvas(self):
        try:
            from plugins.inspiration_canvas import CanvasPlugin
            plugin = CanvasPlugin()
            plugin.api = self.win.api
            plugin.activate(self.win.api)
        except Exception as e:
            self._show_error("灵感画布失败", str(e))

    def _show_python_console(self):
        try:
            if hasattr(self.win, 'console') and self.win.console:
                self.win.console.setVisible(
                    not self.win.console.isVisible()
                )
        except Exception as e:
            self._show_error("控制台失败", str(e))

    def _show_event_history(self):
        """显示事件历史"""
        try:
            text = bus.dump_history(limit=50)
            dlg = self._create_text_dialog("事件历史", text, 700, 500)
            dlg.exec()
        except Exception as e:
            self._show_error("事件历史失败", str(e))

    def _show_memory_stats(self):
        """显示内存统计"""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem = process.memory_info().rss / 1024 / 1024
            stats = bus.get_stats()

            text = f"""内存统计
==============================
进程内存: {mem:.2f} MB
线程数: {process.num_threads()}
CPU 使用率: {process.cpu_percent(interval=0.1):.1f}%

事件总线统计
==============================
总事件数: {stats['total_events']}
过滤器数量: {stats['filter_count']}
暂停状态: {stats['paused']}
待处理事件: {stats['pending_count']}

事件计数
==============================
"""
            for name, count in sorted(
                stats['event_counts'].items(),
                key=lambda x: x[1], reverse=True
            ):
                text += f"{name}: {count}\n"

            dlg = self._create_text_dialog("内存统计", text, 500, 500)
            dlg.exec()
        except Exception as e:
            self._show_error("内存统计失败", str(e))

    def _reload_plugins(self):
        """重新加载所有插件"""
        try:
            if hasattr(self.win, 'load_plugins'):
                self.win.load_plugins()
                bus.emit_success("插件已重新加载")
        except Exception as e:
            self._show_error("重新加载插件失败", str(e))

    # ========================================================
    # 帮助菜单槽函数
    # ========================================================
    def _show_help(self):
        """显示使用指南"""
        try:
            help_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "docs", "HELP.md"
            )
            if os.path.exists(help_path):
                with open(help_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            else:
                content = self._default_help_text()
            dlg = self._create_html_dialog("使用指南", content, 800, 600)
            dlg.exec()
        except Exception as e:
            self._show_error("显示帮助失败", str(e))

    def _show_quickstart(self):
        """显示快速入门"""
        text = """快速入门
====================================

1. 打开文件
   按 Ctrl+O 或拖拽文件到窗口

2. 编辑代码
   支持语法高亮、代码折叠、多光标

3. 查找替换
   按 Ctrl+F 查找，Ctrl+H 替换

4. 命令面板
   按 Ctrl+Shift+P 搜索所有功能

5. 列模式
   按 Alt+C 进入列模式，批量编辑

6. 宏录制
   按 Ctrl+Shift+R 开始录制

7. 快捷键
   所有快捷键可在工具→快捷键编辑中查看修改

青草枯荣，野火重生。
"""
        dlg = self._create_text_dialog("快速入门", text, 600, 500)
        dlg.exec()

    def _show_daily_tip(self):
        """显示每日技巧"""
        try:
            from ui.tips import get_tip
            tip = get_tip()
        except ImportError:
            tips = [
                "按 Ctrl+Shift+P 打开命令面板，搜索所有功能。",
                "按 Alt+C 进入列模式，可同时编辑多行。",
                "Ctrl+D 选中当前单词，再按一次选中下一个相同单词。",
                "拖拽标签到窗口外可分离为独立窗口。",
                "按 Ctrl+Shift+R 录制宏，Ctrl+Shift+P 回放。",
                "选中文本后输入括号可自动包裹。",
                "按 F5 插入当前日期时间。",
                "按 Ctrl+/ 注释或取消注释当前行。",
            ]
            import random
            tip = random.choice(tips)

        QMessageBox.information(self.win, "💡 每日技巧", tip)

    def _show_shortcut_reference(self):
        """显示快捷键参考"""
        lines = ["快捷键参考", "=" * 60, ""]
        for category, names in self.act_mgr.get_categories().items():
            lines.append(f"\n【{category}】")
            for name in names:
                action = self.act_mgr.actions[name]
                shortcut = action.shortcut().toString()
                if shortcut:
                    lines.append(f"  {action.text():30s} {shortcut}")
        text = "\n".join(lines)
        dlg = self._create_text_dialog("快捷键参考", text, 700, 600)
        dlg.exec()

    def _show_faq(self):
        """显示常见问题"""
        text = """常见问题
====================================

Q: 如何修改快捷键？
A: 工具 → 快捷键编辑，或直接编辑 keybindings.json

Q: 如何安装插件？
A: 工具 → 插件市场，浏览并安装

Q: 打开大文件很慢？
A: 青草使用 mmap 分块加载，但超大文件（>2GB）建议使用只读模式

Q: 如何自定义主题？
A: 在 themes/ 目录下创建 JSON 主题文件，或在主题市场下载

Q: 插件不生效？
A: 安装后需要重启编辑器

Q: 如何反馈 bug？
A: 帮助 → 报告问题，或在 GitHub 提 Issue

Q: 如何配置便携模式？
A: 在程序目录创建 portable.txt 文件，所有配置将存储于程序目录

Q: 支持哪些语言？
A: 通过 LSP 支持 Python、JavaScript、Rust、Go、C++ 等

青草枯荣，野火重生。
"""
        dlg = self._create_text_dialog("常见问题", text, 600, 500)
        dlg.exec()

    def _view_runtime_log(self):
        """查看运行日志"""
        log_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "logs", "runtime.log"
        )
        if not os.path.exists(log_path):
            bus.emit_status("运行日志不存在", 2000, "info")
            return
        self.win.tabs.open_file(log_path)

    def _view_crash_log(self):
        """查看崩溃日志"""
        log_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "crash.log"
        )
        if not os.path.exists(log_path):
            bus.emit_status("崩溃日志不存在（好消息！）", 2000, "success")
            return
        self.win.tabs.open_file(log_path)

    def _check_update(self):
        """检查更新"""
        try:
            import requests
            resp = requests.get(
                "https://api.github.com/repos/qingcao-editor/qingcao/releases/latest",
                timeout=5
            )
            if resp.status_code == 200:
                latest = resp.json()
                latest_version = latest.get('tag_name', '').lstrip('v')
                from main import __version__
                if latest_version > __version__:
                    ret = QMessageBox.question(
                        self.win, "发现新版本",
                        f"最新版本: v{latest_version}\n"
                        f"当前版本: v{__version__}\n\n"
                        f"是否前往下载？",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if ret == QMessageBox.Yes:
                        QDesktopServices.openUrl(
                            QUrl(latest['html_url'])
                        )
                else:
                    QMessageBox.information(
                        self.win, "检查更新", "已是最新版本"
                    )
            else:
                bus.emit_status("无法获取更新信息", 3000, "warning")
        except Exception as e:
            bus.emit_status(f"检查更新失败: {e}", 3000, "warning")

    def _show_achievements(self):
        """显示成就"""
        try:
            path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data", "onboarding.json"
            )
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    stats = json.load(f)
                text = f"已保存: {stats.get('saves', 0)} 次\n"
                unlocked = stats.get('unlocked', [])
                text += f"已解锁成就: {len(unlocked)}\n\n"
                text += (
                    "\n".join(f"🏆 {name}" for name in unlocked)
                    if unlocked else "暂无成就"
                )
            else:
                text = "暂无成就数据，多使用编辑器解锁吧！"
            QMessageBox.information(self.win, "🏆 我的成就", text)
        except Exception as e:
            self._show_error("获取成就失败", str(e))

    def _about(self):
        """关于对话框"""
        from main import __version__, __author__, __email__
        about_text = f"""
<h2>青草编辑器 v{__version__}</h2>
<p style="color: #888;">QingCao Editor</p>

<p><b>轻量 · 极速 · 可扩展</b></p>

<p>
开发者: {__author__}<br>
邮箱: {__email__}
</p>

<p style="margin-top: 20px; color: #7ec850;">
<i>青草枯荣，野火重生。</i>
</p>

<p style="margin-top: 20px; color: #666; font-size: 11px;">
Copyright © 2024-2025 {__author__}<br>
Licensed under MIT License
</p>
"""
        QMessageBox.about(self.win, "关于青草编辑器", about_text)

    # ========================================================
    # 最近文件管理
    # ========================================================
    def _load_recent(self):
        """从 QSettings 加载最近文件列表"""
        files = self.settings.value(RECENT_FILES_KEY, [])
        if isinstance(files, str):
            files = [files] if files else []
        self.recent_files = [f for f in files if os.path.exists(f)]

        projects = self.settings.value(RECENT_PROJECTS_KEY, [])
        if isinstance(projects, str):
            projects = [projects] if projects else []
        self.recent_projects = [
            p for p in projects if os.path.exists(p)
        ]

    def _save_recent(self):
        """保存最近文件列表"""
        self.settings.setValue(
            RECENT_FILES_KEY, self.recent_files[:MAX_RECENT_FILES]
        )
        self.settings.setValue(
            RECENT_PROJECTS_KEY,
            self.recent_projects[:MAX_RECENT_PROJECTS]
        )

    def _add_recent_file(self, path: str):
        """添加到最近文件列表"""
        path = os.path.abspath(path)
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:MAX_RECENT_FILES]
        self._save_recent()
        self._update_recent_menu()

    def _add_recent_project(self, path: str):
        """添加到最近项目列表"""
        path = os.path.abspath(path)
        if path in self.recent_projects:
            self.recent_projects.remove(path)
        self.recent_projects.insert(0, path)
        self.recent_projects = self.recent_projects[:MAX_RECENT_PROJECTS]
        self._save_recent()
        self._update_recent_project_menu()

    def _update_recent_menu(self):
        """重建最近文件子菜单"""
        if not self.recent_menu:
            return
        self.recent_menu.clear()
        self._recent_file_actions.clear()

        if not self.recent_files:
            empty = self.recent_menu.addAction("（暂无）")
            empty.setEnabled(False)
            return

        for path in self.recent_files:
            display = os.path.basename(path)
            action = QAction(f"📄 {display}", self.win)
            action.setToolTip(path)
            action.setData(path)
            action.triggered.connect(self._open_recent_file)
            self.recent_menu.addAction(action)
            self._recent_file_actions.append(action)

        self.recent_menu.addSeparator()
        clear_action = self.recent_menu.addAction("🗑 清空列表")
        clear_action.triggered.connect(self._clear_recent_files)

    def _update_recent_project_menu(self):
        """重建最近项目子菜单"""
        if not self.recent_project_menu:
            return
        self.recent_project_menu.clear()
        self._recent_project_actions.clear()

        if not self.recent_projects:
            empty = self.recent_project_menu.addAction("（暂无）")
            empty.setEnabled(False)
            return

        for path in self.recent_projects:
            display = os.path.basename(path)
            action = QAction(f"📁 {display}", self.win)
            action.setToolTip(path)
            action.setData(path)
            action.triggered.connect(self._open_recent_project)
            self.recent_project_menu.addAction(action)
            self._recent_project_actions.append(action)

        self.recent_project_menu.addSeparator()
        clear_action = self.recent_project_menu.addAction("🗑 清空列表")
        clear_action.triggered.connect(self._clear_recent_projects)

    def _open_recent_file(self):
        """打开最近文件"""
        action = self.win.sender()
        if action:
            path = action.data()
            if path and os.path.exists(path):
                self.win.tabs.open_file(path)
                self._add_recent_file(path)

    def _open_recent_project(self):
        """打开最近项目"""
        action = self.win.sender()
        if action:
            path = action.data()
            if path and os.path.exists(path):
                if hasattr(self.win, 'open_project'):
                    self.win.open_project(path)
                    self._add_recent_project(path)

    def _clear_recent_files(self):
        """清空最近文件"""
        self.recent_files.clear()
        self._save_recent()
        self._update_recent_menu()

    def _clear_recent_projects(self):
        """清空最近项目"""
        self.recent_projects.clear()
        self._save_recent()
        self._update_recent_project_menu()

    # ========================================================
    # 事件总线连接
    # ========================================================
    def _connect_events(self):
        """连接事件总线信号"""
        bus.file_saved.connect(self._on_file_saved)

    def _on_file_saved(self, event: FileSavedEvent):
        """文件保存后更新最近文件列表"""
        if event.path:
            self._add_recent_file(event.path)

    # ========================================================
    # 辅助方法
    # ========================================================
    def _show_error(self, title: str, message: str):
        """显示错误对话框"""
        QMessageBox.critical(self.win, title, message)

    def _create_text_dialog(self, title: str, text: str,
                            width: int = 600, height: int = 400
                            ) -> QDialog:
        """创建一个显示纯文本的对话框"""
        dlg = QDialog(self.win)
        dlg.setWindowTitle(title)
        dlg.resize(width, height)
        layout = QVBoxLayout(dlg)
        browser = QTextBrowser()
        browser.setPlainText(text)
        layout.addWidget(browser)
        btn = QPushButton("关闭")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        return dlg

    def _create_html_dialog(self, title: str, html: str,
                            width: int = 600, height: int = 400
                            ) -> QDialog:
        """创建一个显示 HTML 的对话框"""
        dlg = QDialog(self.win)
        dlg.setWindowTitle(title)
        dlg.resize(width, height)
        layout = QVBoxLayout(dlg)
        browser = QTextBrowser()
        browser.setHtml(html)
        browser.setOpenExternalLinks(True)
        layout.addWidget(browser)
        btn = QPushButton("关闭")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        return dlg

    def _default_help_text(self):
        """默认帮助文本（当 HELP.md 不存在时）"""
        return """<h2>青草编辑器使用指南</h2>
<p><b>青草枯荣，野火重生。</b></p>
<h3>基础操作</h3>
<ul>
<li>Ctrl+N 新建文件</li>
<li>Ctrl+O 打开文件</li>
<li>Ctrl+S 保存文件</li>
<li>Ctrl+W 关闭标签</li>
</ul>
<h3>编辑技巧</h3>
<ul>
<li>Alt+C 列模式</li>
<li>Ctrl+D 多光标选中</li>
<li>Ctrl+/ 注释切换</li>
<li>Ctrl+Shift+P 命令面板</li>
</ul>
<h3>高级功能</h3>
<ul>
<li>Ctrl+Shift+R 宏录制</li>
<li>Ctrl+Shift+F 全局搜索</li>
<li>Ctrl+` Python 控制台</li>
<li>F11 无干扰模式</li>
</ul>
<h3>插件扩展</h3>
<p>工具 → 插件市场，浏览并安装扩展</p>
<h3>更多帮助</h3>
<p>访问 <a href="https://qingcao-editor.github.io/docs">在线文档</a></p>
"""

    # ========================================================
    # 右键上下文菜单
    # ========================================================
    def create_context_menu(self, parent_widget, position) -> QMenu:
        """
        为编辑器创建右键上下文菜单。

        参数:
            parent_widget: 父控件
            position: 点击位置

        返回:
            构建好的 QMenu
        """
        menu = QMenu(parent_widget)

        # 撤销/重做
        proxy = self.win.tabs.current_proxy()
        if proxy:
            undo_act = menu.addAction("↩ 撤销")
            undo_act.setEnabled(proxy.sc.isUndoAvailable())
            undo_act.triggered.connect(self._undo)

            redo_act = menu.addAction("↪ 重做")
            redo_act.setEnabled(proxy.sc.isRedoAvailable())
            redo_act.triggered.connect(self._redo)

        menu.addSeparator()

        # 剪切/复制/粘贴
        has_selection = proxy and proxy.sc.hasSelectedText()
        cut_act = menu.addAction("✂ 剪切")
        cut_act.setEnabled(has_selection)
        cut_act.triggered.connect(self._cut)

        copy_act = menu.addAction("📋 复制")
        copy_act.setEnabled(has_selection)
        copy_act.triggered.connect(self._copy)

        paste_act = menu.addAction("📋 粘贴")
        paste_act.triggered.connect(self._paste)

        menu.addSeparator()

        # 选区和操作
        if has_selection:
            select_all_act = menu.addAction("🔷 选中所有相同项")
            select_all_act.triggered.connect(self._select_all_occurrences)

            calc_act = menu.addAction("🧮 计算表达式")
            calc_act.triggered.connect(self._calc_expression)

            comment_act = menu.addAction("💬 注释/取消注释")
            comment_act.triggered.connect(self._toggle_comment)

            upper_act = menu.addAction("🔠 转为大写")
            upper_act.triggered.connect(self._to_upper)

            lower_act = menu.addAction("🔡 转为小写")
            lower_act.triggered.connect(self._to_lower)

        menu.addSeparator()

        # 查找
        find_act = menu.addAction("🔍 查找...")
        find_act.triggered.connect(self._show_search)

        goto_line_act = menu.addAction("📍 跳转到行...")
        goto_line_act.triggered.connect(self._goto_line)

        menu.addSeparator()

        # 书签
        bookmark_act = menu.addAction("🔖 切换书签")
        bookmark_act.triggered.connect(self._toggle_bookmark)

        menu.addSeparator()

        # 插入日期
        datetime_act = menu.addAction("📅 插入日期时间")
        datetime_act.triggered.connect(self._insert_datetime)

        return menu


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication, QMainWindow
    from app.actions import ActionManager

    app = QApplication(sys.argv)
    win = QMainWindow()
    mgr = ActionManager()

    # 模拟主窗口的必要属性
    class FakeTabs:
        def count(self): return 0
        def currentIndex(self): return -1
        def current_proxy(self): return None
        def add_tab(self): pass

    win.tabs = FakeTabs()
    win.macro = type('Macro', (), {
        'start': lambda: None, 'stop': lambda: None,
        'commands': [], 'replay': lambda x: None
    })()

    builder = MenuBuilder(win, mgr)
    win.show()

    print("菜单栏已构建，动作数量:", mgr.count())
    print(mgr.dump())

    sys.exit(app.exec())