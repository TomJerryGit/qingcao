# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
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
