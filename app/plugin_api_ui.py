# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""UI/菜单/面板/对话框职责（v2.24 从 plugin_api.py 拆出）。"""

from app.plugin_api_common import *  # noqa: F401,F403,F405


class UiMixin:
    def add_menu(self, path: str, callback: Callable, shortcut: Optional[str] = None):
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

            parts = path.split("/")
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

    def add_toolbar_action(
        self, text: str, callback: Callable, icon: Optional[str] = None
    ) -> Optional[QAction]:
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

    def register_shortcut(self, shortcut: str, callback: Callable) -> Optional[QAction]:
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

    def add_panel(
        self, title: str, widget: QWidget, area: str = "right", visible: bool = True
    ) -> Optional[QDockWidget]:
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
                applier = getattr(self.win, "apply_theme_to_widget", None)
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

    def add_editor_context_menu(self, label, callback):
        """向编辑器右键菜单添加一项

        参数:
            label: 显示文本
            callback: 点击时执行（主线程）
        权限：editor_read
        """
        self._check_permission(PERMISSION_EDITOR_READ)
        win = self._host_window()
        adder = getattr(win, "add_plugin_editor_context_action", None)
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
            adder = getattr(win, "add_plugin_status_item", None)
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
        target = getattr(editor, "sc", editor)
        fn = getattr(target, "add_plugin_decoration", None)
        if not callable(fn):
            return False
        ok = fn(start_line, end_line, color)
        if ok:
            self._registered_decorations.append((target, start_line, end_line))
        return bool(ok)

    def show_status(self, message: str, timeout: int = 3000, level: str = "info"):
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

    def show_notification(self, title: str, message: str, level: str = "info"):
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

    def show_message(self, title: str, message: str, icon: str = "info") -> None:
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
                title,
                message,
                QMessageBox.Ok,
                self.win,
            ).exec_()
        except Exception:
            pass

    def ask_yes_no(self, title: str, message: str) -> bool:
        """询问是/否"""
        if not self.require_permission(PERMISSION_DIALOG):
            return False
        try:
            ret = QMessageBox.question(self.win, title, message, QMessageBox.Yes | QMessageBox.No)
            return ret == QMessageBox.Yes
        except Exception:
            return False

    def ask_string(self, title: str, label: str, default: str = "") -> Tuple[str, bool]:
        """输入字符串"""
        if not self.require_permission(PERMISSION_DIALOG):
            return ("", False)
        try:
            return QInputDialog.getText(self.win, title, label, text=default)
        except Exception:
            return ("", False)

    def ask_integer(
        self,
        title: str,
        label: str,
        default: int = 0,
        min_val: int = -2147483648,
        max_val: int = 2147483647,
        step: int = 1,
    ) -> Tuple[int, bool]:
        """输入整数"""
        if not self.require_permission(PERMISSION_DIALOG):
            return (default, False)
        try:
            return QInputDialog.getInt(self.win, title, label, default, min_val, max_val, step)
        except Exception:
            return (default, False)

    def ask_item(
        self, title: str, label: str, items: List[str], current: int = 0
    ) -> Tuple[str, bool]:
        """从列表中选择"""
        if not self.require_permission(PERMISSION_DIALOG):
            return ("", False)
        try:
            return QInputDialog.getItem(self.win, title, label, items, current, False)
        except Exception:
            return ("", False)

    def open_file_dialog(
        self, title: str = "打开文件", directory: str = "", file_filter: str = "所有文件 (*.*)"
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
            path, _ = QFileDialog.getOpenFileName(self.win, title, directory, file_filter)
            return path or None
        except Exception:
            return None

    def open_files_dialog(
        self, title: str = "打开多个文件", directory: str = "", file_filter: str = "所有文件 (*.*)"
    ) -> List[str]:
        """打开多文件选择对话框"""
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return []
        if not self.require_permission(PERMISSION_DIALOG):
            return []
        try:
            paths, _ = QFileDialog.getOpenFileNames(self.win, title, directory, file_filter)
            return paths
        except Exception:
            return []

    def save_file_dialog(
        self, title: str = "保存文件", default_name: str = "", file_filter: str = "所有文件 (*.*)"
    ) -> Optional[str]:
        """保存文件对话框"""
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return None
        if not self.require_permission(PERMISSION_DIALOG):
            return None
        try:
            path, _ = QFileDialog.getSaveFileName(self.win, title, default_name, file_filter)
            return path or None
        except Exception:
            return None

    def choose_directory(self, title: str = "选择目录", directory: str = "") -> Optional[str]:
        """选择目录对话框"""
        if not self.require_permission(PERMISSION_FILESYSTEM):
            return None
        if not self.require_permission(PERMISSION_DIALOG):
            return None
        try:
            path = QFileDialog.getExistingDirectory(self.win, title, directory)
            return path or None
        except Exception:
            return None

    def show_text_dialog(self, title: str, text: str, width: int = 600, height: int = 400):
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
            if not isinstance(item, dict) or not item.get("key"):
                continue
            norm.append(dict(item))
        self._settings_schema = norm
        # 登记到宿主（供设置面板/文档/测试查询）
        try:
            win = self._host_window()
            registrar = getattr(win, "register_plugin_settings_schema", None)
            if callable(registrar):
                registrar(self.plugin_name, norm)
        except Exception:
            pass
        # 未设置过的项写入默认值，便于插件直接 get_config
        for item in norm:
            if "default" in item:
                try:
                    if self.get_config(item["key"], None) is None:
                        self.set_config(item["key"], item["default"])
                except Exception:
                    pass
        try:
            action = self.add_menu(
                "工具/插件设置/%s…" % self.plugin_name, self._open_settings_dialog
            )
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
                key = item["key"]
                kind = item.get("type", "str")
                default = item.get("default", "")
                current = self.get_config(key, default)
                if kind == "bool":
                    w = QCheckBox(item.get("label", key))
                    w.setChecked(bool(current))
                elif kind == "int":
                    w = QSpinBox()
                    w.setRange(int(item.get("min", 0)), int(item.get("max", 1000000)))
                    w.setValue(int(current or 0))
                elif kind == "choice":
                    w = QComboBox()
                    for text, value in item.get("choices", []):
                        w.addItem(str(text), value)
                    idx = w.findData(current)
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                elif kind == "text":
                    w = QPlainTextEdit()
                    w.setPlainText(str(current or ""))
                else:
                    w = QLineEdit(str(current or ""))
                editors[key] = (kind, w)
                if kind != "bool":
                    form.addRow(item.get("label", key), w)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            form.addRow(buttons)
            if dlg.exec_() != QDialog.Accepted:
                return
            for key, (kind, w) in editors.items():
                if kind == "bool":
                    value = w.isChecked()
                elif kind == "int":
                    value = w.value()
                elif kind == "choice":
                    value = w.currentData()
                elif kind == "text":
                    value = w.toPlainText()
                else:
                    value = w.text()
                self.set_config(key, value)
            self.save_plugin_config()
            self.show_status("插件设置已保存", 2000, "success")
        except Exception as e:
            self.log(f"打开插件设置失败: {e}", "error")

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
                if "qss" in theme:
                    self.win.setStyleSheet(theme["qss"])
        except Exception as e:
            self.show_status(f"应用主题失败: {e}", 3000, "error")

    # ========================================================
    # 消息通知（跨插件通信）
    # ========================================================
