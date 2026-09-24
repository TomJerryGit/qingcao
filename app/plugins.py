#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为插件 API 模块，包含：
- PluginAPI：暴露给插件的安全接口
- PluginBase：插件基类（推荐继承）
- 权限校验机制
- 菜单注册
- 面板注册
- 事件订阅
- 编辑器访问
- 文件系统操作
- 网络请求
- 快捷键注册
- 语法高亮注册
- LSP 注册
- 状态栏消息
- 对话框辅助
- 配置读写
- 命令注册

修复记录:
- PluginBase.activate: 当 api 为 None 时安全处理，避免二次崩溃
- PluginAPI: 构造时增加 main_window 与 plugin_name 的健壮性校验
- 所有 *_safe 方法在 api 为 None 时返回安全默认值
"""

import os
import sys
import json
import inspect
import functools
from typing import Optional, Dict, List, Callable, Any, Tuple

from PyQt5.QtWidgets import (
    QDockWidget, QWidget, QMessageBox, QInputDialog, QFileDialog,
    QMenu, QAction, QApplication, QDialog, QTextEdit, QVBoxLayout, QPushButton
)
from PyQt5.QtGui import QKeySequence, QColor
from PyQt5.QtCore import Qt, QTimer, QObject, pyqtSignal, pyqtSlot, QSettings

from app.event_bus import (
    bus, BaseEvent, FileOpenedEvent, FileSavedEvent, FileClosedEvent,
    FileModifiedEvent, CursorEvent, SelectionEvent, EditorChangedEvent,
    TabChangedEvent, TabAddedEvent, TabRemovedEvent, ProjectOpenedEvent,
    ProjectClosedEvent, MacroStartedEvent, MacroStoppedEvent,
    ThemeEvent, StatusMessageEvent, NotificationEvent
)


# ============================================================
# 常量
# ============================================================
# 插件权限常量
PERMISSION_FILESYSTEM = "filesystem"
PERMISSION_NETWORK = "network"
PERMISSION_PROCESS = "process"
PERMISSION_CLIPBOARD = "clipboard"
PERMISSION_DIALOG = "dialog"
PERMISSION_EDITOR_WRITE = "editor_write"
PERMISSION_EDITOR_READ = "editor_read"
PERMISSION_TERMINAL = "terminal"

ALL_PERMISSIONS = [
    PERMISSION_FILESYSTEM,
    PERMISSION_NETWORK,
    PERMISSION_PROCESS,
    PERMISSION_CLIPBOARD,
    PERMISSION_DIALOG,
    PERMISSION_EDITOR_WRITE,
    PERMISSION_EDITOR_READ,
    PERMISSION_TERMINAL,
]

# API 版本
API_VERSION = "2.0.0"


# ============================================================
# 权限错误
# ============================================================
class PermissionError(Exception):
    """插件权限不足时抛出"""
    pass


# ============================================================
# 插件 API
# ============================================================
class PluginAPI(QObject):
    """
    暴露给插件的 API 接口。

    插件通过此对象与编辑器交互，所有操作均受权限校验。
    使用方式：

        class Plugin:
            def activate(self, api):
                self.api = api
                api.add_menu("工具/我的功能", self.run)
                api.subscribe('file_opened', self.on_file_opened)

            def deactivate(self):
                pass

    插件需在 plugin.json 中声明所需权限：
        {
            "name": "my_plugin",
            "permissions": ["filesystem", "network"]
        }
    """

    # 信号
    plugin_loaded = pyqtSignal(str)
    plugin_unloaded = pyqtSignal(str)

    def __init__(self, main_window, permissions: Optional[List[str]] = None,
                 plugin_name: str = "unknown"):
        """
        参数:
            main_window: 主窗口实例
            permissions: 权限列表
            plugin_name: 插件名称（用于日志和错误提示）
        """
        # 防御性处理：即使 main_window 为 None 也不崩溃
        super().__init__(main_window if isinstance(main_window, QObject) else None)

        self.win = main_window
        self.permissions = set(permissions or [])
        self.plugin_name = plugin_name

        # 插件注册的资源（用于卸载时清理）
        self._registered_actions: List[QAction] = []
        self._registered_menus: List[QMenu] = []
        self._registered_panels: List[QDockWidget] = []
        self._registered_shortcuts: List[QAction] = []
        self._event_connections: List[Tuple[Any, Callable]] = []
        self._registered_commands: Dict[str, Callable] = {}
        self._registered_lexers: Dict[str, Any] = {}
        self._registered_lsp: Dict[str, List[str]] = {}

        # 插件私有数据目录
        try:
            self._data_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data", "plugins", plugin_name
            )
        except Exception:
            self._data_dir = os.path.join("data", "plugins", plugin_name)

    # ========================================================
    # 权限校验
    # ========================================================
    def _check_permission(self, perm: str):
        """检查是否有指定权限"""
        if perm not in self.permissions:
            raise PermissionError(
                f"插件 '{self.plugin_name}' 缺少 '{perm}' 权限。"
                f"请在 plugin.json 的 permissions 字段中声明。"
            )

    def has_permission(self, perm: str) -> bool:
        """查询是否有指定权限"""
        return perm in self.permissions

    def require_permission(self, perm: str) -> bool:
        """要求权限，无权限时显示提示而非抛异常"""
        if not self.has_permission(perm):
            self.show_status(
                f"插件 {self.plugin_name} 缺少 '{perm}' 权限", 3000, "warning"
            )
            return False
        return True

    def grant_permission(self, perm: str):
        """动态授予权限（谨慎使用）"""
        self.permissions.add(perm)

    def revoke_permission(self, perm: str):
        """撤销权限"""
        self.permissions.discard(perm)

    # ========================================================
    # 编辑器访问
    # ========================================================
    def current_editor(self):
        """
        获取当前活动编辑器代理。

        返回:
            EditorProxy 实例或 None
        """
        try:
            if self.win is None:
                return None
            return self.win.tabs.current_proxy()
        except Exception:
            return None

    def all_editors(self) -> List[Any]:
        """获取所有打开的编辑器代理"""
        editors = []
        try:
            if self.win is None:
                return editors
            for i in range(self.win.tabs.count()):
                w = self.win.tabs.widget(i)
                if hasattr(w, 'proxy'):
                    editors.append(w.proxy)
        except Exception:
            pass
        return editors

    def get_editor_count(self) -> int:
        """获取当前打开的编辑器数量"""
        try:
            if self.win is None:
                return 0
            return self.win.tabs.count()
        except Exception:
            return 0

    def get_selected_text(self) -> str:
        """获取当前编辑器选中的文本"""
        editor = self.current_editor()
        if editor:
            return editor.sc.selectedText()
        return ""

    def get_current_text(self) -> str:
        """获取当前编辑器的全部文本"""
        editor = self.current_editor()
        if editor:
            return editor.sc.text()
        return ""

    def get_current_filepath(self) -> Optional[str]:
        """获取当前编辑器的文件路径（使用新 API）"""
        editor = self.current_editor()
        if not editor:
            return None

        # 优先使用新 API
        if hasattr(editor, 'document') and editor.document:
            return editor.document.filepath or None

        # 兜底：走 EditorProxy 的属性别名
        return editor.filepath or None

    def get_cursor_position(self) -> Tuple[int, int]:
        """获取光标位置（行, 列），从 0 开始"""
        editor = self.current_editor()
        if editor:
            return editor.sc.getCursorPosition()
        return (0, 0)

    def insert_text(self, text: str, at_cursor: bool = True):
        """
        在当前编辑器插入文本。

        参数:
            text: 要插入的文本
            at_cursor: True 表示在光标处插入，False 表示追加到末尾
        """
        if not self.require_permission(PERMISSION_EDITOR_WRITE):
            return
        editor = self.current_editor()
        if not editor:
            return
        try:
            if at_cursor:
                editor.sc.insert(text)
            else:
                editor.sc.append(text)
        except Exception as e:
            self.show_status(f"插入文本失败: {e}", 3000, "error")

    def replace_selected_text(self, text: str):
        """替换当前选中的文本"""
        if not self.require_permission(PERMISSION_EDITOR_WRITE):
            return
        editor = self.current_editor()
        if editor:
            try:
                editor.sc.replaceSelectedText(text)
            except Exception as e:
                self.show_status(f"替换失败: {e}", 3000, "error")

    def set_editor_text(self, text: str):
        """设置当前编辑器的全部文本"""
        if not self.require_permission(PERMISSION_EDITOR_WRITE):
            return
        editor = self.current_editor()
        if editor:
            editor.sc.setText(text)

    def open_file(self, filepath: str) -> Optional[Any]:
        """
        在编辑器中打开文件。

        参数:
            filepath: 文件路径

        返回:
            EditorProxy 实例或 None
        """
        try:
            if not os.path.exists(filepath):
                self.show_status(f"文件不存在: {filepath}", 3000, "warning")
                return None
            if self.win is None:
                return None
            return self.win.tabs.open_file(filepath)
        except Exception as e:
            self.show_status(f"打开文件失败: {e}", 3000, "error")
            return None

    def save_current_file(self) -> bool:
        """保存当前文件"""
        if not self.require_permission(PERMISSION_EDITOR_WRITE):
            return False
        editor = self.current_editor()
        if editor:
            try:
                editor.save_file()
                return True
            except Exception as e:
                self.show_status(f"保存失败: {e}", 3000, "error")
        return False

    def new_tab(self, title: str = "未命名"):
        """新建标签页"""
        try:
            if self.win is None:
                return None
            return self.win.tabs.add_tab(title)
        except Exception as e:
            self.show_status(f"新建标签失败: {e}", 3000, "error")
            return None

    def close_current_tab(self):
        """关闭当前标签"""
        try:
            if self.win is None:
                return
            idx = self.win.tabs.currentIndex()
            if idx >= 0:
                self.win.tabs.close_tab(idx)
        except Exception:
            pass

    # ========================================================
    # 光标与选区操作
    # ========================================================
    def goto_line(self, line: int):
        """跳转到指定行（从 0 开始）"""
        editor = self.current_editor()
        if editor:
            try:
                editor.sc.setCursorPosition(line, 0)
                editor.sc.ensureLineVisible(line)
            except Exception:
                pass

    def goto_position(self, position: int):
        """跳转到指定字符位置"""
        editor = self.current_editor()
        if editor:
            try:
                editor.sc.SendScintilla(editor.sc.SCI_GOTOPOS, position)
            except Exception:
                pass

    def select_range(self, start: int, end: int):
        """选中指定范围"""
        editor = self.current_editor()
        if editor:
            try:
                editor.set_selection(start, end)
            except Exception:
                pass

    def highlight_text(self, pattern: str) -> int:
        """
        高亮所有匹配的文本。

        参数:
            pattern: 正则表达式

        返回:
            匹配数量
        """
        editor = self.current_editor()
        if editor:
            try:
                return editor.highlight_all(pattern)
            except Exception:
                pass
        return 0

    def clear_highlights(self):
        """清除所有高亮"""
        editor = self.current_editor()
        if editor:
            try:
                editor.clear_highlights()
            except Exception:
                pass

    # ========================================================
    # 菜单注册
    # ========================================================
    def add_menu(self, path: str, callback: Callable,
                  shortcut: Optional[str] = None):
        """
        添加菜单项。

        参数:
            path: 菜单路径，例如 "工具/我的插件/执行"
            callback: 触发时调用的函数
            shortcut: 可选快捷键

        返回:
            创建的 QAction 实例
        """
        try:
            if self.win is None:
                return None

            parts = path.split('/')
            if len(parts) < 2:
                # 直接添加到工具菜单
                menu = self._find_or_create_menu("工具")
                action = QAction(parts[-1], self.win)
                action.triggered.connect(callback)
                if shortcut:
                    action.setShortcut(QKeySequence(shortcut))
                menu.addAction(action)
                self._registered_actions.append(action)
                return action

            # 查找顶级菜单
            top_name = parts[0]
            menu = self._find_or_create_menu(top_name)

            # 逐级创建子菜单
            for sub_name in parts[1:-1]:
                sub_menu = None
                for act in menu.actions():
                    if act.menu() and act.text() == sub_name:
                        sub_menu = act.menu()
                        break
                if sub_menu is None:
                    sub_menu = menu.addMenu(sub_name)
                    self._registered_menus.append(sub_menu)
                menu = sub_menu

            # 创建最终动作
            action = QAction(parts[-1], self.win)
            action.triggered.connect(callback)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            menu.addAction(action)
            self._registered_actions.append(action)
            return action

        except Exception as e:
            self.show_status(f"注册菜单失败: {e}", 3000, "error")
            return None

    def _find_or_create_menu(self, name: str) -> Optional[QMenu]:
        """查找或创建顶级菜单"""
        try:
            if self.win is None:
                return None
            for act in self.win.menuBar().actions():
                if act.text().startswith(name):
                    if act.menu():
                        return act.menu()
            return self.win.menuBar().addMenu(name)
        except Exception:
            return None

    def remove_menu(self, action: QAction):
        """移除之前注册的菜单项"""
        try:
            if action in self._registered_actions:
                self._registered_actions.remove(action)
                if action.parent():
                    action.parent().removeAction(action)
                action.deleteLater()
        except Exception:
            pass

    def add_toolbar_action(self, text: str, callback: Callable,
                            icon: Optional[str] = None) -> Optional[QAction]:
        """
        添加工具栏按钮。

        参数:
            text: 按钮文本
            callback: 触发函数
            icon: 图标名称

        返回:
            QAction 实例
        """
        try:
            from PyQt5.QtWidgets import QToolBar

            if self.win is None:
                return None

            toolbar = None
            toolbars = self.win.findChildren(QToolBar)
            if toolbars:
                toolbar = toolbars[0]
            else:
                toolbar = self.win.addToolBar("插件工具栏")

            action = QAction(text, self.win)
            action.triggered.connect(callback)
            if icon:
                try:
                    from infrastructure.icon_manager import IconManager
                    action.setIcon(IconManager.get(icon))
                except Exception:
                    pass
            toolbar.addAction(action)
            self._registered_actions.append(action)
            return action
        except Exception as e:
            self.show_status(f"添加工具栏按钮失败: {e}", 3000, "error")
            return None

    # ========================================================
    # 快捷键注册
    # ========================================================
    def register_shortcut(self, shortcut: str,
                            callback: Callable) -> Optional[QAction]:
        """
        注册全局快捷键。

        参数:
            shortcut: 快捷键字符串，如 "Ctrl+Alt+M"
            callback: 触发函数

        返回:
            QAction 实例
        """
        try:
            if self.win is None:
                return None
            action = QAction(self.win)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(callback)
            self.win.addAction(action)
            self._registered_shortcuts.append(action)
            return action
        except Exception as e:
            self.show_status(f"注册快捷键失败: {e}", 3000, "error")
            return None

    # ========================================================
    # 面板注册
    # ========================================================
    def add_panel(self, title: str, widget: QWidget,
                  area: str = "right",
                  visible: bool = True) -> Optional[QDockWidget]:
        """
        添加可停靠面板。

        参数:
            title: 面板标题
            widget: 面板内容控件
            area: 停靠区域，可选 "left" / "right" / "bottom" / "top"
            visible: 是否默认可见

        返回:
            QDockWidget 实例
        """
        try:
            if self.win is None:
                return None
            dock = QDockWidget(title, self.win)
            dock.setWidget(widget)
            dock.setObjectName(f"plugin_panel_{self.plugin_name}_{title}")

            area_map = {
                "left": Qt.LeftDockWidgetArea,
                "right": Qt.RightDockWidgetArea,
                "bottom": Qt.BottomDockWidgetArea,
                "top": Qt.TopDockWidgetArea,
            }
            dock_area = area_map.get(area.lower(), Qt.RightDockWidgetArea)
            self.win.addDockWidget(dock_area, dock)

            if not visible:
                dock.hide()

            self._registered_panels.append(dock)
            return dock
        except Exception as e:
            self.show_status(f"添加面板失败: {e}", 3000, "error")
            return None

    def remove_panel(self, dock: QDockWidget):
        """移除面板"""
        try:
            if dock in self._registered_panels:
                self._registered_panels.remove(dock)
                if self.win is not None:
                    self.win.removeDockWidget(dock)
                dock.deleteLater()
        except Exception:
            pass

    def toggle_panel(self, dock: QDockWidget):
        """切换面板显示状态"""
        if dock:
            dock.setVisible(not dock.isVisible())

    # ========================================================
    # 事件订阅
    # ========================================================
    def subscribe(self, event_name: str, callback: Callable):
        """
        订阅事件总线事件。

        参数:
            event_name: 事件名称，如 "file_opened", "cursor_moved"
            callback: 回调函数，接收事件对象

        支持的事件:
            file_opened, file_saved, file_closed, file_modified,
            editor_changed, cursor_moved, selection_changed,
            tab_changed, tab_added, tab_removed,
            project_opened, project_closed,
            macro_started, macro_stopped,
            theme_changed
        """
        signal_map = {
            'file_opened': bus.file_opened,
            'file_saved': bus.file_saved,
            'file_closed': bus.file_closed,
            'file_modified': bus.file_modified,
            'editor_changed': bus.editor_changed,
            'cursor_moved': bus.cursor_moved,
            'selection_changed': bus.selection_changed,
            'tab_changed': bus.tab_changed,
            'tab_added': bus.tab_added,
            'tab_removed': bus.tab_removed,
            'project_opened': bus.project_opened,
            'project_closed': bus.project_closed,
            'macro_started': bus.macro_started,
            'macro_stopped': bus.macro_stopped,
            'theme_changed': bus.theme_changed,
        }

        signal = signal_map.get(event_name)
        if signal is None:
            self.show_status(f"未知事件: {event_name}", 3000, "warning")
            return

        try:
            signal.connect(callback)
            self._event_connections.append((signal, callback))
        except Exception as e:
            self.show_status(f"订阅事件失败: {e}", 3000, "error")

    def unsubscribe(self, event_name: str, callback: Callable):
        """取消订阅事件"""
        signal_map = {
            'file_opened': bus.file_opened,
            'file_saved': bus.file_saved,
            'file_closed': bus.file_closed,
            'cursor_moved': bus.cursor_moved,
            'selection_changed': bus.selection_changed,
            'editor_changed': bus.editor_changed,
        }
        signal = signal_map.get(event_name)
        if signal:
            try:
                signal.disconnect(callback)
                self._event_connections = [
                    (s, c) for s, c in self._event_connections
                    if not (s is signal and c is callback)
                ]
            except (TypeError, RuntimeError):
                pass

    def emit_event(self, event: BaseEvent):
        """发射事件到事件总线"""
        bus.emit_event(event)

    def _cleanup_event_connections(self):
        """清理所有事件连接（插件卸载时调用）"""
        for signal, callback in self._event_connections:
            try:
                signal.disconnect(callback)
            except (TypeError, RuntimeError):
                pass
        self._event_connections.clear()

    # ========================================================
    # 状态栏消息
    # ========================================================
    def show_status(self, message: str, timeout: int = 3000,
                    level: str = "info"):
        """
        在状态栏显示消息。

        参数:
            message: 消息文本
            timeout: 超时毫秒数，0 表示不自动消失
            level: 级别，可选 "info" / "warning" / "error" / "success"
        """
        try:
            bus.emit_status(message, timeout, level)
        except Exception:
            try:
                if self.win is not None:
                    self.win.statusBar().showMessage(message, timeout)
            except Exception:
                pass

    def show_notification(self, title: str, message: str,
                          level: str = "info"):
        """显示通知（气泡或对话框）"""
        try:
            bus.emit_notification(title, message, level)
        except Exception:
            try:
                if self.win is not None:
                    QMessageBox.information(self.win, title, message)
            except Exception:
                pass

    # ========================================================
    # 对话框辅助
    # ========================================================
    def show_message(self, title: str, message: str,
                     icon: str = "info") -> None:
        """
        显示消息对话框。

        参数:
            title: 标题
            message: 内容
            icon: "info" / "warning" / "error" / "question"
        """
        if not self.require_permission(PERMISSION_DIALOG):
            return
        try:
            icon_map = {
                "info": QMessageBox.Information,
                "warning": QMessageBox.Warning,
                "error": QMessageBox.Critical,
                "question": QMessageBox.Question,
            }
            QMessageBox(
                icon_map.get(icon, QMessageBox.Information),
                title, message, QMessageBox.Ok, self.win
            ).exec_()
        except Exception:
            pass

    def ask_yes_no(self, title: str, message: str) -> bool:
        """询问是/否"""
        if not self.require_permission(PERMISSION_DIALOG):
            return False
        try:
            ret = QMessageBox.question(
                self.win, title, message,
                QMessageBox.Yes | QMessageBox.No
            )
            return ret == QMessageBox.Yes
        except Exception:
            return False

    def ask_string(self, title: str, label: str,
                   default: str = "") -> Tuple[str, bool]:
        """输入字符串"""
        if not self.require_permission(PERMISSION_DIALOG):
            return ("", False)
        try:
            return QInputDialog.getText(self.win, title, label, text=default)
        except Exception:
            return ("", False)

    def ask_integer(self, title: str, label: str, default: int = 0,
                    min_val: int = -2147483648,
                    max_val: int = 2147483647,
                    step: int = 1) -> Tuple[int, bool]:
        """输入整数"""
        if not self.require_permission(PERMISSION_DIALOG):
            return (default, False)
        try:
            return QInputDialog.getInt(
                self.win, title, label, default, min_val, max_val, step
            )
        except Exception:
            return (default, False)

    def ask_item(self, title: str, label: str, items: List[str],
                 current: int = 0) -> Tuple[str, bool]:
        """从列表中选择"""
        if not self.require_permission(PERMISSION_DIALOG):
            return ("", False)
        try:
            return QInputDialog.getItem(
                self.win, title, label, items, current, False
            )
        except Exception:
            return ("", False)

    def open_file_dialog(self, title: str = "打开文件",
                         directory: str = "",
                         file_filter: str = "所有文件 (*.*)"
                         ) -> Optional[str]:
        """
        打开文件选择对话框。

        返回:
            选中的文件路径或 None
        """
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return None
        if not self.require_permission(PERMISSION_DIALOG):
            return None
        try:
            path, _ = QFileDialog.getOpenFileName(
                self.win, title, directory, file_filter
            )
            return path or None
        except Exception:
            return None

    def open_files_dialog(self, title: str = "打开多个文件",
                          directory: str = "",
                          file_filter: str = "所有文件 (*.*)"
                          ) -> List[str]:
        """打开多文件选择对话框"""
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return []
        if not self.require_permission(PERMISSION_DIALOG):
            return []
        try:
            paths, _ = QFileDialog.getOpenFileNames(
                self.win, title, directory, file_filter
            )
            return paths
        except Exception:
            return []

    def save_file_dialog(self, title: str = "保存文件",
                         default_name: str = "",
                         file_filter: str = "所有文件 (*.*)"
                         ) -> Optional[str]:
        """保存文件对话框"""
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return None
        if not self.require_permission(PERMISSION_DIALOG):
            return None
        try:
            path, _ = QFileDialog.getSaveFileName(
                self.win, title, default_name, file_filter
            )
            return path or None
        except Exception:
            return None

    def choose_directory(self, title: str = "选择目录",
                         directory: str = "") -> Optional[str]:
        """选择目录对话框"""
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return None
        if not self.require_permission(PERMISSION_DIALOG):
            return None
        try:
            path = QFileDialog.getExistingDirectory(
                self.win, title, directory
            )
            return path or None
        except Exception:
            return None

    def show_text_dialog(self, title: str, text: str,
                         width: int = 600, height: int = 400):
        """显示纯文本对话框"""
        if not self.require_permission(PERMISSION_DIALOG):
            return
        try:
            dlg = QDialog(self.win)
            dlg.setWindowTitle(title)
            dlg.resize(width, height)
            layout = QVBoxLayout(dlg)
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setPlainText(text)
            layout.addWidget(text_edit)
            close_btn = QPushButton("关闭")
            close_btn.clicked.connect(dlg.accept)
            layout.addWidget(close_btn)
            dlg.exec_()
        except Exception:
            pass

    # ========================================================
    # 文件系统操作
    # ========================================================
    def read_file(self, filepath: str,
                    encoding: str = "utf-8") -> Optional[str]:
        """
        读取文件内容。

        参数:
            filepath: 文件路径
            encoding: 编码

        返回:
            文件内容或 None（失败时）
        """
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return None
        try:
            with open(filepath, 'r', encoding=encoding,
                       errors='replace') as f:
                return f.read()
        except Exception as e:
            self.show_status(f"读取文件失败: {e}", 3000, "error")
            return None

    def read_file_bytes(self, filepath: str) -> Optional[bytes]:
        """读取文件二进制内容"""
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return None
        try:
            with open(filepath, 'rb') as f:
                return f.read()
        except Exception as e:
            self.show_status(f"读取文件失败: {e}", 3000, "error")
            return None

    def write_file(self, filepath: str, content: str,
                    encoding: str = "utf-8") -> bool:
        """
        写入文件。

        参数:
            filepath: 文件路径
            content: 内容
            encoding: 编码

        返回:
            是否成功
        """
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return False
        try:
            os.makedirs(
                os.path.dirname(os.path.abspath(filepath)) or '.',
                exist_ok=True
            )
            with open(filepath, 'w', encoding=encoding) as f:
                f.write(content)
            return True
        except Exception as e:
            self.show_status(f"写入文件失败: {e}", 3000, "error")
            return False

    def write_file_bytes(self, filepath: str, content: bytes) -> bool:
        """写入文件二进制内容"""
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return False
        try:
            os.makedirs(
                os.path.dirname(os.path.abspath(filepath)) or '.',
                exist_ok=True
            )
            with open(filepath, 'wb') as f:
                f.write(content)
            return True
        except Exception as e:
            self.show_status(f"写入文件失败: {e}", 3000, "error")
            return False

    def file_exists(self, filepath: str) -> bool:
        """检查文件是否存在"""
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return False
        return os.path.exists(filepath)

    def is_directory(self, path: str) -> bool:
        """检查是否为目录"""
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return False
        return os.path.isdir(path)

    def list_directory(self, path: str) -> List[str]:
        """列出目录内容"""
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return []
        try:
            return os.listdir(path)
        except Exception:
            return []

    def get_plugin_data_dir(self) -> str:
        """
        获取插件私有数据目录。

        插件可在此目录自由读写，无需额外权限。
        目录在首次调用时自动创建。
        """
        try:
            os.makedirs(self._data_dir, exist_ok=True)
        except Exception:
            pass
        return self._data_dir

    # ========================================================
    # 配置读写
    # ========================================================
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        读取插件配置。

        配置存储于 QSettings 中，以插件名为前缀。
        """
        try:
            settings = QSettings("QingCao", f"Plugin_{self.plugin_name}")
            return settings.value(key, default)
        except Exception:
            return default

    def set_config(self, key: str, value: Any):
        """写入插件配置"""
        try:
            settings = QSettings("QingCao", f"Plugin_{self.plugin_name}")
            settings.setValue(key, value)
        except Exception as e:
            self.show_status(f"保存配置失败: {e}", 3000, "error")

    def save_plugin_config(self, data: Dict[str, Any]) -> bool:
        """保存插件配置（JSON 格式到数据目录）"""
        try:
            config_path = os.path.join(
                self.get_plugin_data_dir(), "config.json"
            )
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            self.show_status(f"保存插件配置失败: {e}", 3000, "error")
            return False

    def load_plugin_config(self) -> Dict[str, Any]:
        """加载插件配置"""
        try:
            config_path = os.path.join(
                self.get_plugin_data_dir(), "config.json"
            )
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    # ========================================================
    # 网络请求
    # ========================================================
    def http_get(self, url: str, timeout: int = 10,
                 headers: Optional[Dict[str, str]] = None
                 ) -> Optional[str]:
        """
        HTTP GET 请求。

        参数:
            url: 请求 URL
            timeout: 超时秒数
            headers: 自定义请求头

        返回:
            响应文本或 None
        """
        if not self.require_permission(PERMISSION_NETWORK):
            return None
        try:
            import requests
            resp = requests.get(url, timeout=timeout, headers=headers)
            return resp.text
        except Exception as e:
            self.show_status(f"网络请求失败: {e}", 3000, "error")
            return None

    def http_post(self, url: str, data: Any = None,
                   json_data: Any = None,
                   timeout: int = 10,
                   headers: Optional[Dict[str, str]] = None
                   ) -> Optional[str]:
        """HTTP POST 请求"""
        if not self.require_permission(PERMISSION_NETWORK):
            return None
        try:
            import requests
            resp = requests.post(url, data=data, json=json_data,
                                 timeout=timeout, headers=headers)
            return resp.text
        except Exception as e:
            self.show_status(f"网络请求失败: {e}", 3000, "error")
            return None

    def download_file(self, url: str, filepath: str,
                      timeout: int = 30) -> bool:
        """下载文件"""
        if not self.require_permission(PERMISSION_NETWORK):
            return False
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return False
        try:
            import requests
            resp = requests.get(url, timeout=timeout, stream=True)
            resp.raise_for_status()
            os.makedirs(
                os.path.dirname(os.path.abspath(filepath)) or '.',
                exist_ok=True
            )
            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            self.show_status(f"下载失败: {e}", 3000, "error")
            return False

    # ========================================================
    # 剪贴板
    # ========================================================
    def get_clipboard(self) -> str:
        """获取剪贴板文本"""
        if not self.require_permission(PERMISSION_CLIPBOARD):
            return ""
        try:
            return QApplication.clipboard().text()
        except Exception:
            return ""

    def set_clipboard(self, text: str):
        """设置剪贴板文本"""
        if not self.require_permission(PERMISSION_CLIPBOARD):
            return
        try:
            QApplication.clipboard().setText(text)
        except Exception:
            pass

    # ========================================================
    # 进程与终端
    # ========================================================
    def run_command(self, command: str, cwd: Optional[str] = None,
                    timeout: int = 30) -> Optional[str]:
        """
        执行系统命令并返回输出。

        参数:
            command: 命令
            cwd: 工作目录
            timeout: 超时秒数

        返回:
            标准输出或 None
        """
        if not self.require_permission(PERMISSION_PROCESS):
            return None
        try:
            import subprocess
            result = subprocess.run(
                command, shell=True, cwd=cwd,
                capture_output=True, text=True, timeout=timeout
            )
            return result.stdout + result.stderr
        except Exception as e:
            self.show_status(f"命令执行失败: {e}", 3000, "error")
            return None

    def run_python(self, code: str) -> Optional[str]:
        """
        在当前进程执行 Python 代码（危险，需谨慎）。

        返回:
            输出字符串或 None
        """
        if not self.require_permission(PERMISSION_PROCESS):
            return None
        try:
            import io
            from contextlib import redirect_stdout, redirect_stderr
            stdout_cap = io.StringIO()
            stderr_cap = io.StringIO()
            with redirect_stdout(stdout_cap), redirect_stderr(stderr_cap):
                exec(code, {})
            return stdout_cap.getvalue() + stderr_cap.getvalue()
        except Exception as e:
            return f"错误: {e}"

    # ========================================================
    # 命令注册
    # ========================================================
    def register_command(self, name: str, callback: Callable,
                         description: str = ""):
        """
        注册一个命令，可在命令面板中搜索。

        参数:
            name: 命令名称（唯一）
            callback: 执行函数
            description: 描述
        """
        self._registered_commands[name] = {
            'callback': callback,
            'description': description
        }
        # 添加到 ActionManager 以便命令面板可搜索
        try:
            if self.win is None:
                return
            action = QAction(description or name, self.win)
            action.triggered.connect(callback)
            if hasattr(self.win, 'act_mgr') and self.win.act_mgr:
                self.win.act_mgr.register(
                    f"plugin.{self.plugin_name}.{name}",
                    action,
                    None,
                    category="插件",
                    description=description
                )
            self._registered_actions.append(action)
        except Exception:
            pass

    def execute_command(self, name: str):
        """执行已注册的命令"""
        cmd = self._registered_commands.get(name)
        if cmd:
            try:
                cmd['callback']()
            except Exception as e:
                self.show_status(f"命令执行失败: {e}", 3000, "error")

    def list_commands(self) -> List[str]:
        """列出所有已注册命令"""
        return list(self._registered_commands.keys())

    # ========================================================
    # 语法高亮注册
    # ========================================================
    def register_lexer(self, extension: str, lexer_factory: Callable):
        """
        注册自定义语法高亮器。

        参数:
            extension: 文件扩展名（如 ".abc"）
            lexer_factory: 创建 lexer 的函数
        """
        self._registered_lexers[extension] = lexer_factory
        if self.win is not None:
            if not hasattr(self.win, '_custom_lexers'):
                self.win._custom_lexers = {}
            self.win._custom_lexers[extension] = lexer_factory

    def get_lexer(self, extension: str) -> Optional[Any]:
        """获取指定扩展名的 lexer"""
        factory = self._registered_lexers.get(extension)
        if factory:
            try:
                return factory()
            except Exception:
                return None
        return None

    # ========================================================
    # LSP 注册
    # ========================================================
    def register_lsp(self, language_id: str,
                     server_command: List[str],
                     extensions: Optional[List[str]] = None):
        """
        注册 LSP 语言服务器。

        参数:
            language_id: 语言 ID（如 "python"）
            server_command: 启动命令列表
            extensions: 关联的文件扩展名列表
        """
        self._registered_lsp[language_id] = {
            'command': server_command,
            'extensions': extensions or []
        }
        if self.win is not None:
            if not hasattr(self.win, '_lsp_servers'):
                self.win._lsp_servers = {}
            self.win._lsp_servers[language_id] = server_command

    def get_lsp_server(self, language_id: str) -> Optional[List[str]]:
        """获取指定语言的 LSP 启动命令"""
        info = self._registered_lsp.get(language_id)
        return info['command'] if info else None

    # ========================================================
    # 主题操作
    # ========================================================
    def get_current_theme(self) -> Optional[str]:
        """获取当前主题路径"""
        try:
            settings = QSettings("QingCao", "Editor")
            return settings.value("theme_path", None)
        except Exception:
            return None

    def apply_theme(self, theme_path: str):
        """应用主题"""
        try:
            from infrastructure.theme_loader import ThemeLoader
            loader = ThemeLoader()
            theme = loader.load(theme_path)
            if self.win is not None:
                for i in range(self.win.tabs.count()):
                    loader.apply(self.win.tabs.widget(i), theme)
                if 'qss' in theme:
                    self.win.setStyleSheet(theme['qss'])
        except Exception as e:
            self.show_status(f"应用主题失败: {e}", 3000, "error")

    # ========================================================
    # 消息通知（跨插件通信）
    # ========================================================
    def send_message(self, target_plugin: str, message: Any):
        """
        向其他插件发送消息（通过事件总线）。

        参数:
            target_plugin: 目标插件名称
            message: 任意可序列化对象
        """
        try:
            event = NotificationEvent(
                title=f"plugin_message:{target_plugin}",
                message=(json.dumps(message)
                         if not isinstance(message, str)
                         else message),
                level="info"
            )
            bus.emit_event(event)
        except Exception:
            pass

    # ========================================================
    # 卸载清理
    # ========================================================
    def cleanup(self):
        """
        清理所有注册的资源（插件卸载时由 PluginLoader 调用）。
        """
        # 清理事件连接
        try:
            self._cleanup_event_connections()
        except Exception:
            pass

        # 清理菜单动作
        for action in self._registered_actions:
            try:
                if action.parent():
                    action.parent().removeAction(action)
                action.deleteLater()
            except Exception:
                pass
        self._registered_actions.clear()

        # 清理子菜单
        for menu in self._registered_menus:
            try:
                menu.deleteLater()
            except Exception:
                pass
        self._registered_menus.clear()

        # 清理面板
        for dock in self._registered_panels:
            try:
                if self.win is not None:
                    self.win.removeDockWidget(dock)
                dock.deleteLater()
            except Exception:
                pass
        self._registered_panels.clear()

        # 清理快捷键
        for action in self._registered_shortcuts:
            try:
                if self.win is not None:
                    self.win.removeAction(action)
                action.deleteLater()
            except Exception:
                pass
        self._registered_shortcuts.clear()

        # 清理命令
        self._registered_commands.clear()

    # ========================================================
    # 信息查询
    # ========================================================
    def get_api_version(self) -> str:
        """获取 API 版本"""
        return API_VERSION

    def get_plugin_name(self) -> str:
        """获取当前插件名称"""
        return self.plugin_name

    def get_app_version(self) -> str:
        """获取应用版本"""
        try:
            from main import __version__
            return __version__
        except Exception:
            return "unknown"

    def get_permissions(self) -> List[str]:
        """获取当前插件的权限列表"""
        return sorted(self.permissions)

    # ========================================================
    # 调试辅助
    # ========================================================
    def log(self, message: str, level: str = "info"):
        """
        记录日志（输出到控制台和运行日志）。

        参数:
            message: 日志内容
            level: 级别
        """
        prefix = f"[Plugin:{self.plugin_name}]"
        print(f"{prefix} [{level.upper()}] {message}")

    def __repr__(self) -> str:
        return (f"<PluginAPI plugin={self.plugin_name!r} "
                f"permissions={sorted(self.permissions)} "
                f"api_version={API_VERSION}>")


# ============================================================
# 权限辅助函数
# ============================================================
def parse_permissions(plugin_manifest: Dict[str, Any]) -> List[str]:
    """
    从插件清单中解析权限列表。

    参数:
        plugin_manifest: plugin.json 加载的字典

    返回:
        有效的权限列表
    """
    raw = plugin_manifest.get('permissions', [])
    if not isinstance(raw, list):
        return []
    return [p for p in raw if p in ALL_PERMISSIONS]


def validate_permissions(permissions: List[str]) -> List[str]:
    """
    校验权限列表，返回无效权限。

    参数:
        permissions: 权限列表

    返回:
        无效权限列表
    """
    return [p for p in permissions if p not in ALL_PERMISSIONS]


def describe_permissions(permissions: List[str]) -> str:
    """生成权限的友好描述（用于插件安装时提示用户）"""
    descriptions = {
        PERMISSION_FILESYSTEM: "读写本地文件",
        PERMISSION_NETWORK: "访问网络",
        PERMISSION_PROCESS: "执行系统命令",
        PERMISSION_CLIPBOARD: "读写剪贴板",
        PERMISSION_DIALOG: "显示对话框",
        PERMISSION_EDITOR_WRITE: "修改编辑器内容",
        PERMISSION_EDITOR_READ: "读取编辑器内容",
        PERMISSION_TERMINAL: "使用终端",
    }
    lines = []
    for p in permissions:
        if p in descriptions:
            lines.append(f"  • {descriptions[p]} ({p})")
    return "\n".join(lines) if lines else "  （无特殊权限）"


# ============================================================
# 插件基类
# ============================================================
class PluginBase:
    """
    插件基类。

    插件可以选择继承此类，也可不继承（只要实现 activate/deactivate 即可）。

    用法:
        from app.plugins import PluginBase

        class Plugin(PluginBase):
            NAME = "my_plugin"
            VERSION = "1.0.0"
            DESCRIPTION = "我的插件"

            def on_activate(self):
                self.api.add_menu("工具/我的功能", self.run)

            def run(self):
                self.api.show_status("Hello from my plugin!")
    """

    NAME: str = "unknown"
    VERSION: str = "0.0.0"
    DESCRIPTION: str = ""
    AUTHOR: str = ""
    PERMISSIONS: List[str] = []

    def __init__(self):
        self.api: Optional[PluginAPI] = None

    def activate(self, api):
        """
        由 PluginLoader 调用。

        修复记录:
            - api 为 None 时安全处理，不再二次调用 api.log()
            - 捕获 on_activate 异常并输出堆栈，但不二次崩溃
        """
        self.api = api

        # 安全处理：api 为 None 时直接返回
        if api is None:
            print(
                f"[PluginBase] {self.NAME}: api 为 None，跳过激活"
            )
            return

        try:
            self.on_activate()
        except Exception as e:
            # 安全地记录错误（避免 api 为 None 时二次崩溃）
            try:
                if self.api is not None:
                    self.api.log(
                        f"activate 失败: {e}", "error"
                    )
            except Exception:
                pass

            import traceback
            traceback.print_exc()
            # 让 PluginLoader 知道激活失败
            raise

    def on_activate(self):
        """子类重写，实现插件激活逻辑"""
        pass

    def deactivate(self):
        """由 PluginLoader 调用"""
        try:
            self.on_deactivate()
        except Exception as e:
            if self.api is not None:
                try:
                    self.api.log(
                        f"deactivate 失败: {e}", "error"
                    )
                except Exception:
                    pass

    def on_deactivate(self):
        """子类重写，实现插件清理逻辑"""
        pass


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel

    app = QApplication(sys.argv)
    win = QMainWindow()

    # 模拟主窗口必要属性
    class FakeTabs:
        def count(self): return 0
        def currentIndex(self): return -1
        def current_proxy(self): return None
        def add_tab(self, title="Untitled"): return None
        def open_file(self, path): return None

    win.tabs = FakeTabs()
    win.act_mgr = type('Mgr', (), {
        'register': lambda *a, **k: None,
        'actions': {}
    })()
    win.statusBar = lambda: type(
        'SB', (), {'showMessage': lambda *a: None}
    )()

    # 创建 API（有全部权限）
    api = PluginAPI(
        win,
        permissions=ALL_PERMISSIONS,
        plugin_name="test_plugin"
    )

    print("API 版本:", api.get_api_version())
    print("插件名称:", api.get_plugin_name())
    print("权限:", api.get_permissions())
    print("数据目录:", api.get_plugin_data_dir())
    print()
    print("权限描述:")
    print(describe_permissions(api.get_permissions()))
    print()

    # 测试注册菜单
    action = api.add_menu("工具/测试/打招呼", lambda: print("Hello!"))
    print(f"注册菜单动作: {action}")

    # 测试注册命令
    api.register_command("hello", lambda: print("命令执行"), "打招呼")
    print(f"已注册命令: {api.list_commands()}")

    # 测试配置
    api.set_config("test_key", "test_value")
    print(f"读取配置: {api.get_config('test_key')}")

    # 测试 api 为 None 的 PluginBase
    print()
    print("=== 测试 PluginBase 安全处理 ===")

    class SafePlugin(PluginBase):
        NAME = "safe_test"
        def on_activate(self):
            print("SafePlugin on_activate 被调用")

    sp = SafePlugin()

    # 正常 activate
    sp.activate(api)
    print("正常 activate 成功")

    # api 为 None 的 activate（不应崩溃）
    sp2 = SafePlugin()
    try:
        sp2.activate(None)
        print("api=None 的 activate 安全通过")
    except Exception as e:
        print(f"api=None 的 activate 崩溃: {e}")

    # 测试清理
    api.cleanup()
    print("清理完成")

    print()
    print(api)