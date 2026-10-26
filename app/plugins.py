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

import functools
import inspect
import json
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.event_bus import (
    BaseEvent,
    CursorEvent,
    EditorChangedEvent,
    FileClosedEvent,
    FileModifiedEvent,
    FileOpenedEvent,
    FileSavedEvent,
    MacroStartedEvent,
    MacroStoppedEvent,
    NotificationEvent,
    ProjectClosedEvent,
    ProjectOpenedEvent,
    SelectionEvent,
    StatusMessageEvent,
    TabAddedEvent,
    TabChangedEvent,
    TabRemovedEvent,
    ThemeEvent,
    bus,
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
# P1-2 修复：README 文档中列出了 lsp / debugger，但代码里
# 没有这两个常量，parse_permissions 会把它们静默过滤掉，
# 导致插件声明的权限与运行时权限不一致。
PERMISSION_LSP = "lsp"
PERMISSION_DEBUGGER = "debugger"

ALL_PERMISSIONS = [
    PERMISSION_FILESYSTEM,
    PERMISSION_NETWORK,
    PERMISSION_PROCESS,
    PERMISSION_CLIPBOARD,
    PERMISSION_DIALOG,
    PERMISSION_EDITOR_WRITE,
    PERMISSION_EDITOR_READ,
    PERMISSION_TERMINAL,
    PERMISSION_LSP,
    PERMISSION_DEBUGGER,
]

# 权限名称（中文，供 UI 展示；与 app/plugin_manager.PERMISSION_NAMES 对齐）
PERMISSION_LABELS = {
    PERMISSION_FILESYSTEM: "读写本地文件",
    PERMISSION_NETWORK: "访问网络",
    PERMISSION_PROCESS: "执行系统命令",
    PERMISSION_CLIPBOARD: "读写剪贴板",
    PERMISSION_DIALOG: "显示对话框 / 访问主窗口",
    PERMISSION_EDITOR_WRITE: "修改编辑器内容",
    PERMISSION_EDITOR_READ: "读取编辑器内容",
    PERMISSION_TERMINAL: "使用集成终端",
    PERMISSION_LSP: "注册 LSP 服务",
    PERMISSION_DEBUGGER: "调试功能",
}

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
class _BackgroundBridge(QObject):
    """后台任务结果桥（v2.3 `run_background` 用）

    每个后台任务配一个独立桥：`run_background` 可能在同一个 API
    实例上并发多个任务，共享信号无法区分结果归属。
    桥对象在**主线程**创建；工作线程只 emit，Qt 按队列把回调
    投递回主线程执行 —— 这就是"后台执行、主线程回调"的实现方式。

    `cancelled` 由插件卸载路径置位，回调据此跳过，避免在窗口
    销毁后操作 Qt 对象。
    """

    done = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = False


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

    # 说明（P3-1）:
    #   原有两个信号 plugin_loaded / plugin_unloaded 从未在
    #   PluginAPI 内部 emit，属于死代码。PluginLoader /
    #   PluginManager 有各自的 plugin_loaded 信号负责通知，
    #   PluginAPI 层不需要重复。
    #
    #   如果第三方插件引用了 api.plugin_loaded，请在插件里
    #   改用 from app.event_bus import bus 或直接监听
    #   PluginLoader 的信号。

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

        # P0-3: 主窗口引用不放在实例字典里，改为受控属性，
        # 使 __getattr__ 能对直读给出弃用警告。
        # （api.win 旧写法仍可用，但会提示迁移到
        #   get_main_window()；内部代码请统一用 _host_window()。）
        self.__dict__['_win_compat'] = main_window
        self.permissions = set(permissions or [])
        self.plugin_name = plugin_name

        # P0-3: 只有宿主可以动态授权
        self._host_authorized: bool = False
        # P0-3: 兼容旧插件的 api.win 直读，但给出明确警告，
        # 引导改用 get_main_window()（受 dialog 权限门控）
        self._win_warned: bool = False

        # 插件注册的资源（用于卸载时清理）
        self._registered_actions: List[QAction] = []
        self._registered_menus: List[QMenu] = []
        self._registered_panels: List[QDockWidget] = []
        self._registered_shortcuts: List[QAction] = []
        self._event_connections: List[Tuple[Any, Callable]] = []
        self._registered_commands: Dict[str, Callable] = {}
        self._registered_lexers: Dict[str, Any] = {}
        self._registered_lsp: Dict[str, List[str]] = {}

        # v2.3 扩展点：编辑器智能（补全 / 诊断 / 后台任务）
        self._registered_completion_providers: List[Any] = []
        self._published_diagnostics: Dict[str, List[Any]] = {}
        self._background_bridges: List[Any] = []
        self._background_threads: List[Any] = []

        # v2.4 扩展点：hover / 代码操作 / 右键菜单 / 状态栏 / 装饰 / 设置
        self._registered_hover_providers: List[Any] = []
        self._registered_context_actions: List[Any] = []
        self._registered_code_action_providers: List[Any] = []
        self._registered_status_items: List[Any] = []
        self._registered_decorations: List[Any] = []
        self._registered_symbol_providers: List[Any] = []
        self._settings_schema: List[Any] = []
        self._settings_action = None

        # 插件私有数据目录
        try:
            self._data_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data", "plugins", plugin_name
            )
        except Exception:
            # 基于应用根目录，避免相对路径随工作目录变化
            try:
                from infrastructure.plugin_loader import (
                    app_root_dir as _app_root,
                )
                _base = _app_root()
            except Exception:
                _base = "."
            self._data_dir = os.path.join(
                _base, "data", "plugins", plugin_name)

    # ========================================================
    # 权限校验
    # ========================================================
    @property
    def win(self):
        """兼容属性：主窗口（已弃用）

        P0-3: 本编辑器目前**没有进程级沙箱**，插件与编辑器同
        进程运行，权限只在 API 边界上做门控，因此 `api.win`
        这种直通宿主的属性是绕过权限的主要通道。

        该属性为兼容既有插件而保留（会打印一次弃用警告），
        新代码请改用 get_main_window()（受 dialog 权限门控）。
        """
        if not self.__dict__.get('_win_warned', False):
            self.__dict__['_win_warned'] = True
            try:
                print(
                    "[PluginAPI] 警告：api.win 已弃用（绕过权限门控），"
                    "请改用 api.get_main_window()（需要 dialog 权限）"
                )
            except Exception:
                pass
        return self.__dict__.get('_win_compat')

    def _host_window(self):
        """内部/内置插件专用：取主窗口，不打印弃用警告

        P0-3: 内置插件的面板注册需要主窗口。这里提供一个不触发
        api.win 弃用告警的内部通道。第三方插件请使用
        get_main_window()（受 dialog 权限门控）。
        """
        return self.__dict__.get('_win_compat')

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
        """动态授予权限（仅宿主可调用）

        P0-3 修复：原实现是 `self.permissions.add(perm)`，
        插件可以一行代码自我提权：
            self.api.grant_permission('process')
            self.api.run_command('...')
        现在必须由宿主（主窗口/插件管理器）显式授权，
        否则拒绝并提示。
        """
        if not self._host_authorized:
            self.show_status(
                f"插件 {self.plugin_name} 不允许自行授予权限 '{perm}'",
                3000, "warning"
            )
            return False
        self.permissions.add(perm)
        return True

    def grant_permissions_by_host(self, perms) -> int:
        """宿主授予权限（不受 _host_authorized 限制）

        供主窗口/插件管理器在用户确认权限后调用。
        """
        count = 0
        for p in perms or []:
            if p not in self.permissions:
                self.permissions.add(p)
                count += 1
        return count

    def revoke_permission(self, perm: str):
        """撤销权限"""
        self.permissions.discard(perm)

    # ========================================================
    # 宿主窗口访问（P0-3）
    # ========================================================
    def get_main_window(self):
        """获取主窗口（需要 dialog 权限）

        P0-3 修复：原先 `api.win` 是公开属性，插件可由此拿到
        主窗口，进而取到全权限的主 API（widget.api）从而绕过
        所有权限检查。现改为受权限门控的方法访问。
        """
        if not self.win:
            return None
        if PERMISSION_DIALOG not in self.permissions:
            self.show_status(
                f"插件 {self.plugin_name} 缺少 'dialog' 权限，"
                f"无法访问主窗口",
                3000, "warning"
            )
            return None
        return self.win

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

            # 插件面板默认写死深色 QSS；主窗口主题已确定时要立刻套用，
            # 否则浅色主题下插件面板会是一块黑矩形。
            try:
                applier = getattr(self.win, 'apply_theme_to_widget', None)
                if callable(applier):
                    applier(widget)
            except Exception:
                pass

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
    @staticmethod
    def _event_signal_map() -> dict:
        """事件名 → 事件总线信号 的**唯一**映射表

        修复（审计用例 test_unsubscribe_supports_every_subscribable_event）：
            `subscribe()` 与 `unsubscribe()` 各自维护了一份字面量映射，
            而 `unsubscribe` 的那份**只有 6 项**（subscribe 有 15 项）：
            缺少 file_modified、tab_changed、tab_added、tab_removed、
            project_opened、project_closed、macro_started、macro_stopped、
            theme_changed。

            于是这些事件的 `unsubscribe()` **静默失败** —— 插件的回调
            永远留在信号上。插件被禁用/重载后仍会被调用，访已释放的对象
            会崩溃，或造成重复响应。这是"订阅得上、退订不掉"的经典泄漏。

            现在两份共用一个映射表，从结构上杜绝不一致。
        """
        return {
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
        signal_map = self._event_signal_map()

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
        """取消订阅事件（映射与 `subscribe` 完全相同）

        ⚠️ 关键实现细节（实测踩坑）：
            PyQt 的 **bound signal 每次属性访问都会返回新的包装对象**：

                bus.file_opened is bus.file_opened   ->  False
                bus.file_opened == bus.file_opened   ->  True

            因此用 `is` 比较信号对象永远不成立 —— 这正是原实现
            `if not (s is signal and c is callback)` **静默失败**、
            退订后连接依然挂着的原因之一（另一个原因是映射表缺键）。

            现在用 `==` 比较（按底层信号身份），并同时逐个尝试
            `disconnect()`。
        """
        signal_map = self._event_signal_map()
        signal = signal_map.get(event_name)
        if signal is None:
            self.show_status(f"未知事件: {event_name}", 3000, "warning")
            return

        try:
            signal.disconnect(callback)
        except (TypeError, RuntimeError):
            # 未连接 / 已断开 —— 不是错误
            pass

        # 无论 disconnect 是否抛错都清理登记表（用 == 而非 is）
        self._event_connections = [
            (s, c) for s, c in self._event_connections
            if not (c == callback and (s == signal or s is signal))
        ]

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
            with open(filepath, encoding=encoding,
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

        P0-3 修复：原实现"无需额外权限"即可写盘，成为绕过
        filesystem 权限的写文件后门（app/plugins.py 旧版
        1021-1032 行）。现在要求 filesystem 权限。
        """
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return ""
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
        """保存插件配置（JSON 格式到数据目录）

        P0-3: 需要 filesystem 权限（同 get_plugin_data_dir）。
        """
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return False
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
                with open(config_path, encoding='utf-8') as f:
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
            from contextlib import redirect_stderr, redirect_stdout
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
            # ⚠️ 必须是 `is not None` 判定，**不能**用真值判定！
            #
            # 实测缺陷：`ActionManager` 定义了 `__len__`（返回动作数），
            # 因此**空的 ActionManager 是 falsy**。而插件正是在**激活时**
            # 注册命令 —— 那一刻 `act_mgr` 里几乎还是空的（只有极少数
            # 早期动作），于是原来的
            #     `if hasattr(...) and self.win.act_mgr:`
            # 会直接短路，**命令一个都不会注册**：
            #   * 命令面板的「插件」分类永远是空的（它按
            #     `name.startswith("plugin.")` 从 `act_mgr.actions` 取）；
            #   * 「⭐ 特色功能」聚合入口只能显示"未注册命令"。
            # 缓过来之后再启动（actions 已被前一次运行填过）反而正常，
            # 所以这是**首次运行 100% 复现**的隐蔽缺陷。
            mgr = getattr(self.win, 'act_mgr', None)
            if mgr is not None:
                mgr.register(
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
    # 编辑器智能扩展点（v2.3）
    # ========================================================
    def register_completion_provider(self, provider, language_ids=None):
        """注册补全提供者 —— 让插件参与编辑器补全

        这是插件从"挂菜单/面板"升级为"参与编辑智能"的关键扩展点。

        参数:
            provider: 可调用对象，签名
                ``provider(prefix, language=..., filepath=...) -> list``
                返回候选词列表（str 列表，或 dict:
                ``{"label": "foo", "insert_text": "foo()", "detail": "..."}``）。
                在**主线程**调用，应快速返回（重活请用 run_background）。
            language_ids: 生效的语言/扩展名列表（如 ``["python", ".py"]``）；
                None 表示对所有语言生效。

        返回:
            是否注册成功

        权限: editor_read（需要读取当前编辑内容的能力）

        注意:
            * 提供者抛异常不会影响编辑器，异常被捕获并记日志；
            * 插件卸载（cleanup）时自动注销。
        """
        self._check_permission(PERMISSION_EDITOR_READ)
        win = self._host_window()
        if win is None:
            return False
        registrar = getattr(win, 'register_plugin_completion_provider', None)
        if not callable(registrar):
            self.log("宿主不支持补全扩展点", "warning")
            return False
        ok = registrar(provider, language_ids=language_ids,
                       plugin_name=self.plugin_name)
        if ok:
            self._registered_completion_providers.append(
                (provider, language_ids))
        return bool(ok)

    def publish_diagnostics(self, problems, filepath=None):
        """发布诊断信息到「问题」面板

        参数:
            problems: 列表，元素为 dict 或 ``core.problems.Problem``：
                ``{"line": 3, "col": 0, "severity": "error"|"warning"|"info"|"hint",
                   "message": "...", "code": "E001"}``
                line/col 从 0 开始。
            filepath: 目标文件；None 表示当前编辑器文件。

        返回:
            实际发布的条目数

        权限: editor_read

        语义:
            * 只替换**本插件来源**的诊断，不会清掉 LSP / 其它插件的；
            * 重复调用 = 覆盖本插件上一批诊断（适合实时校验）；
            * 用 ``clear_diagnostics()`` 清空。
        """
        self._check_permission(PERMISSION_EDITOR_READ)
        fp = filepath or self.get_current_filepath() or ""
        try:
            from core.problems import Problem, get_problem_manager
        except Exception as e:
            self.log(f"问题管理器不可用: {e}", "error")
            return 0

        normalized = []
        for item in problems or []:
            try:
                if isinstance(item, Problem):
                    normalized.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                normalized.append(Problem(
                    filepath=fp,
                    line=int(item.get("line", 0) or 0),
                    col=int(item.get("col", 0) or 0),
                    severity=str(item.get("severity", "info")),
                    message=str(item.get("message", "")),
                    source=str(item.get("source") or self.plugin_name),
                    code=str(item.get("code", "")),
                    end_line=int(item.get("end_line", 0) or 0),
                    end_col=int(item.get("end_col", 0) or 0),
                ))
            except Exception:
                continue

        try:
            manager = get_problem_manager()
            existing = list(manager.get_for_file(fp) or [])
            # 只清掉"本插件发布过"的旧条目，保留其它来源
            keep = [p for p in existing
                    if getattr(p, 'source', '') != self.plugin_name]
            manager.set_file_problems(fp, keep + normalized)
            self._published_diagnostics[fp] = normalized
            return len(normalized)
        except Exception as e:
            self.log(f"发布诊断失败: {e}", "error")
            return 0

    def clear_diagnostics(self, filepath=None):
        """清除本插件发布的诊断（filepath=None 清全部）"""
        self._check_permission(PERMISSION_EDITOR_READ)
        try:
            from core.problems import get_problem_manager
            manager = get_problem_manager()
        except Exception:
            return 0
        targets = [filepath] if filepath else list(
            self._published_diagnostics.keys())
        removed = 0
        for fp in targets:
            try:
                existing = list(manager.get_for_file(fp) or [])
                keep = [p for p in existing
                        if getattr(p, 'source', '') != self.plugin_name]
                if len(keep) != len(existing):
                    manager.set_file_problems(fp, keep)
                    removed += len(existing) - len(keep)
                self._published_diagnostics.pop(fp, None)
            except Exception:
                continue
        return removed

    def run_background(self, func, on_done=None, on_error=None,
                       name: str = ""):
        """在后台线程执行函数，回调回到**主线程**

        为什么需要（插件生态短板）：
            插件此前只能自己 ``threading.Thread`` + 手工往主线程
            投递，容易在窗口销毁后 emit 导致
            ``RuntimeError: wrapped C/C++ object has been deleted``。
            本方法用 QObject 信号桥把结果排队回主线程，并随插件
            卸载自动失效。

        参数:
            func: 无参可调用对象（在后台线程执行）
            on_done(result): 成功回调（主线程）
            on_error(message): 失败回调（主线程，收到异常文本）
            name: 任务名（仅用于日志/调试）

        返回:
            任务对象（可用 ``is_alive()`` 查询；插件卸载会自动取消）

        权限: 无（但 **func 内不要直接调用 PluginAPI** —— API 只在
        主线程安全；需要读写编辑器请在 on_done 里做）
        """
        import threading

        api = self
        bridge = _BackgroundBridge()

        def _on_done(result):
            if bridge.cancelled:
                return
            try:
                if on_done is not None:
                    on_done(result)
            except Exception as e:
                api.log(f"后台任务 {name} 的 on_done 失败: {e}", "error")

        def _on_error(message):
            if bridge.cancelled:
                return
            try:
                if on_error is not None:
                    on_error(message)
                else:
                    api.log(f"后台任务 {name} 失败: {message}", "error")
            except Exception:
                pass

        bridge.done.connect(_on_done)
        bridge.failed.connect(_on_error)

        def _work():
            try:
                result = func()
            except Exception as e:
                try:
                    bridge.failed.emit(str(e))
                except RuntimeError:
                    pass
                return
            try:
                bridge.done.emit(result)
            except RuntimeError:
                pass

        thread = threading.Thread(target=_work, daemon=True,
                                  name=f"plugin-bg:{name or self.plugin_name}")
        self._background_bridges.append(bridge)
        self._background_threads.append(thread)
        thread.start()
        return thread

    # ========================================================
    # v2.4 扩展点：hover / 代码操作 / 右键菜单 / 状态栏 / 装饰 / 设置
    # ========================================================
    def register_hover_provider(self, provider, language_ids=None):
        """注册悬浮提示提供者

        provider 签名：``provider(line, col, filepath=..., language=...) -> str``
        返回文本作为工具提示（多个提供者用空行分隔）；主线程调用，应快速返回。

        权限：editor_read
        """
        self._check_permission(PERMISSION_EDITOR_READ)
        win = self._host_window()
        registrar = getattr(win, 'register_plugin_hover_provider', None)
        if not callable(registrar):
            return False
        ok = registrar(provider, language_ids=language_ids,
                       plugin_name=self.plugin_name)
        if ok:
            self._registered_hover_providers.append((provider, language_ids))
        return bool(ok)

    def register_code_action_provider(self, provider, language_ids=None):
        """注册代码操作提供者（"快速修复"类）

        provider 签名：``provider(line, col, filepath=..., language=...) -> list``
        每个元素：``{"title": "...", "kind": "quickfix", "callback": fn}``,
        callback 在用户选择该项时执行。

        权限：editor_write（代码操作通常会产生编辑）
        """
        self._check_permission(PERMISSION_EDITOR_WRITE)
        win = self._host_window()
        registrar = getattr(
            win, 'register_plugin_code_action_provider', None)
        if not callable(registrar):
            return False
        ok = registrar(provider, language_ids=language_ids,
                       plugin_name=self.plugin_name)
        if ok:
            self._registered_code_action_providers.append(
                (provider, language_ids))
        return bool(ok)

    def add_editor_context_menu(self, label, callback):
        """向编辑器右键菜单添加一项

        参数:
            label: 显示文本
            callback: 点击时执行（主线程）
        权限：editor_read
        """
        self._check_permission(PERMISSION_EDITOR_READ)
        win = self._host_window()
        adder = getattr(win, 'add_plugin_editor_context_action', None)
        if not callable(adder) or not callable(callback):
            return False
        ok = adder(label, callback, plugin_name=self.plugin_name)
        if ok:
            self._registered_context_actions.append((label, callback))
        return bool(ok)

    def add_status_item(self, widget_or_text, side="right"):
        """在状态栏添加常驻项

        参数:
            widget_or_text: QWidget 或字符串（自动包装成 QLabel）
            side: 目前统一放在右侧常驻区

        返回:
            实际加入的控件（插件可用它更新文本），失败返回 None

        权限：dialog
        """
        self._check_permission(PERMISSION_DIALOG)
        win = self._host_window()
        widget = widget_or_text
        try:
            if isinstance(widget_or_text, str):
                from PyQt5.QtWidgets import QLabel
                widget = QLabel(widget_or_text)
            adder = getattr(win, 'add_plugin_status_item', None)
            if not callable(adder) or widget is None:
                return None
            added = adder(widget)
            if added is not None:
                self._registered_status_items.append(added)
            return added
        except Exception as e:
            self.log(f"添加状态栏项失败: {e}", "error")
            return None

    def add_decoration(self, start_line, end_line, color="#FFCC00"):
        """给当前编辑器行区间加装饰（背景色块，不修改文本）

        返回是否成功。权限：editor_write
        """
        self._check_permission(PERMISSION_EDITOR_WRITE)
        editor = self.current_editor()
        if editor is None:
            return False
        target = getattr(editor, 'sc', editor)
        fn = getattr(target, 'add_plugin_decoration', None)
        if not callable(fn):
            return False
        ok = fn(start_line, end_line, color)
        if ok:
            self._registered_decorations.append((target, start_line, end_line))
        return bool(ok)

    def register_settings_schema(self, schema):
        """注册插件设置项 → 自动生成设置对话框并挂到「工具」菜单

        schema 为列表，每项：
            {"key": "timeout", "label": "超时(秒)", "type": "int",
             "default": 30, "min": 1, "max": 600}
        支持 type: str / int / bool / choice / text；
        choice 需提供 "choices": [(显示文本, 值), ...]。

        值通过 ``get_config(key, default)`` / ``set_config(key, value)``
        读写（已持久化到插件配置）。

        权限：无（这是插件**自有配置**的声明，宿主负责渲染对话框；
        不触碰编辑器/文件/网络，因此不需要 dialog 等权限）。
        """
        if not isinstance(schema, (list, tuple)):
            return False
        norm = []
        for item in schema:
            if not isinstance(item, dict) or not item.get('key'):
                continue
            norm.append(dict(item))
        self._settings_schema = norm
        # 登记到宿主（供设置面板/文档/测试查询）
        try:
            win = self._host_window()
            registrar = getattr(
                win, 'register_plugin_settings_schema', None)
            if callable(registrar):
                registrar(self.plugin_name, norm)
        except Exception:
            pass
        # 未设置过的项写入默认值，便于插件直接 get_config
        for item in norm:
            if 'default' in item:
                try:
                    if self.get_config(item['key'], None) is None:
                        self.set_config(item['key'], item['default'])
                except Exception:
                    pass
        try:
            action = self.add_menu(
                "工具/插件设置/%s…" % self.plugin_name,
                self._open_settings_dialog)
            self._settings_action = action
        except Exception as e:
            self.log(f"注册插件设置菜单失败: {e}", "warning")
        return True

    def _open_settings_dialog(self):
        """根据 schema 生成设置对话框（主线程、模态）"""
        try:
            from PyQt5.QtWidgets import (
                QCheckBox,
                QComboBox,
                QDialog,
                QDialogButtonBox,
                QFormLayout,
                QLineEdit,
                QPlainTextEdit,
                QSpinBox,
            )
            win = self._host_window()
            dlg = QDialog(win)
            dlg.setWindowTitle("%s 设置" % self.plugin_name)
            form = QFormLayout(dlg)
            editors = {}
            for item in self._settings_schema:
                key = item['key']
                kind = item.get('type', 'str')
                default = item.get('default', '')
                current = self.get_config(key, default)
                if kind == 'bool':
                    w = QCheckBox(item.get('label', key))
                    w.setChecked(bool(current))
                elif kind == 'int':
                    w = QSpinBox()
                    w.setRange(int(item.get('min', 0)),
                               int(item.get('max', 1000000)))
                    w.setValue(int(current or 0))
                elif kind == 'choice':
                    w = QComboBox()
                    for text, value in item.get('choices', []):
                        w.addItem(str(text), value)
                    idx = w.findData(current)
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                elif kind == 'text':
                    w = QPlainTextEdit()
                    w.setPlainText(str(current or ''))
                else:
                    w = QLineEdit(str(current or ''))
                editors[key] = (kind, w)
                if kind != 'bool':
                    form.addRow(item.get('label', key), w)
            buttons = QDialogButtonBox(
                QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            form.addRow(buttons)
            if dlg.exec_() != QDialog.Accepted:
                return
            for key, (kind, w) in editors.items():
                if kind == 'bool':
                    value = w.isChecked()
                elif kind == 'int':
                    value = w.value()
                elif kind == 'choice':
                    value = w.currentData()
                elif kind == 'text':
                    value = w.toPlainText()
                else:
                    value = w.text()
                self.set_config(key, value)
            self.save_plugin_config()
            self.show_status("插件设置已保存", 2000, "success")
        except Exception as e:
            self.log(f"打开插件设置失败: {e}", "error")

    def register_symbol_provider(self, provider, language_ids=None):
        """注册符号提供者 → 合并进「大纲」面板

        等价 Notepad++ 的 `functionList.xml`（用户/插件贡献符号解析器）。

        provider 签名：
            ``provider(text, filepath=..., language=...) -> list``
        返回符号列表，每项::

            {"name": "foo", "type": "function", "line": 10, "col": 0,
             "signature": "(a, b)", "children": [...]}

        line/col 从 0 开始；type 取值见 `ui/outline_panel.SymbolType`
        （class/function/method/variable/... 或自定义字符串）。

        权限：editor_read
        """
        self._check_permission(PERMISSION_EDITOR_READ)
        win = self._host_window()
        registrar = getattr(win, 'register_plugin_symbol_provider', None)
        if not callable(registrar) or not callable(provider):
            return False
        ok = registrar(provider, language_ids=language_ids,
                       plugin_name=self.plugin_name)
        if ok:
            self._registered_symbol_providers.append((provider, language_ids))
        return bool(ok)

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
        # 清理 v2.3 扩展点（补全提供者 / 诊断 / 后台任务）
        try:
            win = self._host_window()
            unregister = getattr(
                win, 'unregister_plugin_completion_provider', None)
            if callable(unregister):
                unregister(self.plugin_name)
        except Exception:
            pass
        # 清理 v2.4 扩展点（hover / 右键菜单 / 代码操作 / 设置 / 状态栏）
        try:
            win = self._host_window()
            extras = getattr(win, 'unregister_plugin_extras', None)
            if callable(extras):
                extras(self.plugin_name)
        except Exception:
            pass
        for widget in self._registered_status_items:
            try:
                bar = widget.parentWidget()
                if bar is not None and hasattr(bar, 'removeWidget'):
                    bar.removeWidget(widget)
                widget.deleteLater()
            except Exception:
                pass
        self._registered_status_items.clear()
        self._registered_hover_providers.clear()
        self._registered_context_actions.clear()
        self._registered_code_action_providers.clear()
        self._registered_decorations.clear()
        self._registered_symbol_providers.clear()
        self._settings_schema = []
        self._registered_completion_providers.clear()
        try:
            self.clear_diagnostics()
        except Exception:
            pass
        # ★ 不要 deleteLater()：后台线程可能正持有桥并 emit，
        #   析构 QObject 后从工作线程 emit → Qt 访问违例（实测段错误）。
        #   正确做法：置 cancelled + 断开信号；桥对象交给 GC，
        #   即使线程稍后 emit 也没有接收者，不会崩。
        for bridge in self._background_bridges:
            try:
                bridge.cancelled = True
            except Exception:
                pass
            for sig in ('done', 'failed'):
                try:
                    getattr(bridge, sig).disconnect()
                except Exception:
                    pass
        self._background_bridges.clear()
        self._background_threads.clear()

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
                action.setParent(None)
                action.deleteLater()
            except Exception:
                pass
        self._registered_actions.clear()

        # 清理子菜单
        #
        # 修复（审计用例 test_menu_item_survives_one_hot_reload）：
        #   原先只调 `menu.deleteLater()` —— **延迟删除**，子菜单仍挂在
        #   父菜单上。热重载时 `add_menu` 的"复用已存在子菜单"分支按文本
        #   找到的正是这个**待销毁的旧子菜单**，新动作被加进即将被销毁的
        #   容器；处理 DeferredDelete 后整项**凭空消失**（实测 0，期望 1）。
        #
        #   正确做法：先找到"承载该子菜单的那个 QAction"并从父菜单摘除，
        #   再 deleteLater。
        #
        #    ⚠️ 实测教训：`menu.menuAction().parent()` 返回的是**子菜单自己**
        #    （不是父菜单），所以不能直接用它 removeAction；
        #    必须遍历候选父菜单的 actions，找 `act.menu() is menu` 的那一个。
        for menu in self._registered_menus:
            try:
                holder = None
                holder_parent = None

                def _scan(parent_menu):
                    if parent_menu is None:
                        return None
                    try:
                        for act in parent_menu.actions():
                            if act.menu() is menu:
                                return act
                    except Exception:
                        pass
                    return None

                # 候选父：菜单自身的 parent()（通常是 QMenu）
                p = menu.parent()
                if p is not None and hasattr(p, 'actions'):
                    holder = _scan(p)
                    holder_parent = p
                # 再兜底扫描菜单栏
                if holder is None and self.win is not None:
                    try:
                        for act in self.win.menuBar().actions():
                            if act.menu():
                                h = _scan(act.menu())
                                if h is not None:
                                    holder, holder_parent = h, act.menu()
                                    break
                    except Exception:
                        pass

                menu.clear()
                if holder is not None and holder_parent is not None:
                    holder_parent.removeAction(holder)
                menu.setParent(None)
                menu.deleteLater()
            except Exception:
                pass
        self._registered_menus.clear()

        # 清理面板
        for dock in self._registered_panels:
            try:
                if self.win is not None:
                    self.win.removeDockWidget(dock)
                dock.setParent(None)
                dock.deleteLater()
            except Exception:
                pass
        self._registered_panels.clear()

        # 清理快捷键
        for action in self._registered_shortcuts:
            try:
                if self.win is not None:
                    self.win.removeAction(action)
                action.setParent(None)
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

    # ========================================================
    # 能力探测（借鉴 Notepad++ 插件 API 的"函数表"思路）
    # ========================================================
    # NPP 的做法：插件 DLL 拿到 NppData 后，通过函数指针表判断宿主
    # 提供哪些消息（NPPM_*），再决定注册哪些菜单/面板 —— 插件不会在
    # 旧版宿主上调用不存在的接口而崩溃。
    #
    # 本软件用 Python API 版本代替函数表，但同样需要一个**可探测的
    # 能力清单**：插件（尤其第三方插件）可以先查询宿主支持哪些扩展点、
    # 哪些事件，再决定注册策略，而不是 try/except 盲试。
    _CAPABILITY_EXTENSION_POINTS = (
        "completion", "diagnostics", "background",
        "hover", "code_action", "editor_context_menu",
        "status_item", "decoration", "settings_schema", "symbol_provider",
    )

    def get_api_capabilities(self) -> Dict[str, Any]:
        """返回宿主能力清单（供插件做能力探测）

        返回结构::

            {
              "api_version": "2.0.0",
              "app_version": "2.6.2",
              "extension_points": {"completion": True, ...},
              "events": ["file_opened", ...],
              "permissions": ["editor_read", ...],
            }

        推荐用法（新插件在 on_activate 开头）::

            caps = api.get_api_capabilities()
            if caps["extension_points"].get("completion"):
                api.register_completion_provider(self.suggest)
        """
        try:
            events = self.list_events()
        except Exception:
            events = []
        return {
            "api_version": API_VERSION,
            "app_version": self.get_app_version(),
            "extension_points": {
                name: True for name in self._CAPABILITY_EXTENSION_POINTS
            },
            "events": events,
            "permissions": sorted(self.permissions),
        }

    def list_events(self) -> List[str]:
        """列出所有可订阅事件名（等价于 NPP 的 NPPN_* 通知清单）

        事件通过 ``api.subscribe(name, callback)`` 订阅，
        通过 ``api.unsubscribe(name, callback)`` 退订。
        """
        try:
            return sorted(self._event_signal_map().keys())
        except Exception:
            return []

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

    from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow

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