# -*- coding: utf-8 -*-
"""B1.5：把隔离插件（PluginProcess）接到主窗口菜单/状态栏。"""

import logging
import os

from PyQt5.QtCore import QObject, QSettings, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDockWidget,
    QFormLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QWidget,
)

from core.plugin_sandbox_policy import SandboxPolicy
from core.plugin_supervisor import PluginHostError, PluginProcess
from ui.plugin_settings_dialog import SchemaSettingsDialog


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
logger = logging.getLogger("QingCao.IsolatedPlugins")


class _UIBridge(QObject):
    """从插件 reader 线程把 UI 操作排队到 GUI 线程。"""

    call = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.call.connect(self._run)

    def _run(self, fn):
        try:
            fn()
        except Exception:
            logger.exception("isolated UI bridge failed")

    def submit(self, fn):
        app = QApplication.instance()
        if app is not None and QThread.currentThread() is app.thread():
            fn()
        else:
            self.call.emit(fn)


class WindowHostAPI:
    """宿主 API：直接操作 QMainWindow 的菜单/状态栏（UI 操作排队到 GUI 线程）。"""

    def __init__(self, window, host=None):
        self.window = window
        self.host = host
        self._bridge = _UIBridge(window if isinstance(window, QObject) else None)
        self._cached_text = ""
        try:
            window.tabs.currentChanged.connect(lambda *_: self._cache_text())
        except Exception:
            pass
        self._cached_text = ""
        self._cache_text()
        self.menus = {}
        self.status_items = {}
        self.settings = QSettings("QingCao", "PluginData")
        self._next_status = 1
        self._schemas = {}
        self.schemas = {}
        self._settings_actions = {}
        self.remote_panels = {}
        self.providers = {"hover": {}, "code_action": {}, "completion": {}}
        self._panel_seq = 0

    # ---- 编辑器 ----
    def _current_proxy(self):
        try:
            ed = self.window.tabs.currentWidget()
            return getattr(ed, "proxy", None)
        except Exception:
            return None

    def _cache_text(self):
        proxy = self._current_proxy()
        if proxy is not None:
            try:
                self._cached_text = proxy.text()
            except Exception:
                pass

    def get_current_text(self):
        app = QApplication.instance()
        if app is not None and QThread.currentThread() is app.thread():
            self._cache_text()
            return self._cached_text
        return self._cached_text

    def set_current_text(self, text):
        def _apply():
            proxy = self._current_proxy()
            if proxy is not None:
                proxy.set_text(text)
            self._cached_text = text

        self._bridge.submit(_apply)
        return True

    # ---- UI ----
    def show_message(self, title, text):
        self._bridge.submit(lambda: QMessageBox.information(self.window, str(title), str(text)))
        return True

    def add_menu(self, path, callback_id):
        def _create():
            parts = [p for p in str(path).split("/") if p]
            if not parts:
                return
            menubar = self.window.menuBar()
            menu = None
            for title in parts[:-1]:
                found = None
                container = menubar if menu is None else menu
                for act in container.actions():
                    if act.text().replace("&", "").strip() == title:
                        found = act.menu()
                        break
                if found is None:
                    found = container.addMenu(title)
                menu = found
            action = QAction(parts[-1], self.window)
            if menu is not None:
                menu.addAction(action)
            else:
                menubar.addAction(action)
            self.menus[callback_id] = action
            action.triggered.connect(lambda _=False, cid=callback_id: self.invoke(cid))

        self._bridge.submit(_create)
        return True

    def add_status_item(self, text):
        sid = self._next_status
        self._next_status += 1

        def _create():
            label = QLabel(str(text))
            try:
                self.window.statusBar().addPermanentWidget(label)
            except Exception:
                pass
            self.status_items[sid] = label

        self._bridge.submit(_create)
        return sid

    def remove_status_item(self, status_id):
        label = self.status_items.pop(status_id, None)
        if label is not None:
            label.deleteLater()
            return True
        return False

    def invoke(self, callback_id, *args):
        if self.host is None:
            return None
        try:
            if hasattr(self.host, "invoke_callback"):
                return self.host.invoke_callback(callback_id, *args)
            return self.host.invoke(callback_id)
        except Exception as e:
            logger.warning("isolated menu callback failed: %s", e)
            return None

    # ---- 配置 ----
    def _cfg_key(self, key, plugin_name=None):
        if plugin_name:
            return "plugins/%s/%s" % (plugin_name, key)
        return "plugins/%s" % key

    def get_config(self, key, default=None, plugin_name=None):
        return self.settings.value(self._cfg_key(key, plugin_name), default)

    def set_config(self, key, value, plugin_name=None):
        self.settings.setValue(self._cfg_key(key, plugin_name), value)
        return True

    def register_settings_schema(self, schema, plugin_name=None):
        name = plugin_name or "unknown"
        self.schemas[name] = schema

        def _create_menu():
            menubar = self.window.menuBar()
            tools = None
            for act in menubar.actions():
                if act.text().replace("&", "").strip() == "工具":
                    tools = act.menu()
                    break
            if tools is None:
                tools = menubar.addMenu("工具")
            sub = None
            for act in tools.actions():
                if act.text() == "插件设置":
                    sub = act.menu()
                    break
            if sub is None:
                sub = tools.addMenu("插件设置")
            action = QAction("设置: %s" % name, self.window)
            action.triggered.connect(lambda _=False, n=name: self.open_settings(n).exec_())
            sub.addAction(action)
            self._settings_actions[name] = action

        self._bridge.submit(_create_menu)
        return True

    def open_settings(self, plugin_name):
        schema = self.schemas.get(plugin_name)
        if schema is None:
            raise ValueError("plugin has no settings schema: %s" % plugin_name)
        return SchemaSettingsDialog(plugin_name, schema, parent=self.window)

    def register_remote_panel(self, title, fields, refresh_cb):
        self._panel_seq += 1
        pid = self._panel_seq

        def _create():
            dock = QDockWidget(str(title), self.window)
            body = QWidget(dock)
            form = QFormLayout(body)
            values = {}
            for f in fields or []:
                key = f.get("key") if isinstance(f, dict) else str(f)
                label = (f.get("label") if isinstance(f, dict) else key) or key
                val = QLabel("-")
                form.addRow(str(label) + ":", val)
                values[key] = val
            dock.setWidget(body)
            try:
                self.window.addDockWidget(Qt.RightDockWidgetArea, dock)
            except Exception:
                pass
            self.remote_panels[pid] = {"dock": dock, "values": values, "cb": refresh_cb}

            def refresh():
                rec = self.remote_panels.get(pid)
                if not rec:
                    return
                text = self.get_current_text()
                try:
                    cb = rec["cb"]
                    if callable(cb):
                        result = cb(text)
                    elif hasattr(self, "invoke_callback"):
                        result = self.invoke_callback(cb, text)
                    else:
                        result = None
                except Exception as e:
                    logger.warning("remote panel refresh failed: %s", e)
                    return
                if isinstance(result, dict):
                    for k, label in rec["values"].items():
                        if k in result:
                            label.setText(str(result[k]))

            timer = QTimer(dock)
            timer.timeout.connect(refresh)
            timer.start(1000)
            self.remote_panels[pid]["timer"] = timer
            refresh()

        self._bridge.submit(_create)
        return True

    def show_remote_panel(self, panel_id=0):
        def _show():
            rec = self.remote_panels.get(panel_id) or next(iter(self.remote_panels.values()), None)
            if rec:
                rec["dock"].show()
                rec["dock"].raise_()

        self._bridge.submit(_show)
        return True

    def _invoke_provider(self, cb_id, *args):
        if hasattr(self, "invoke_callback"):
            return self.invoke_callback(cb_id, *args)
        return None

    def register_hover_provider(self, cb_id, language_ids=None, plugin_name=None):
        self.providers["hover"][cb_id] = language_ids
        if hasattr(self.window, "register_plugin_hover_provider"):

            def _hover(line, col, filepath="", language=""):
                return self._invoke_provider(cb_id, line, col, filepath, language)

            self.window.register_plugin_hover_provider(
                _hover, language_ids or [], plugin_name or "unknown"
            )
        return True

    def register_code_action_provider(self, cb_id, language_ids=None, plugin_name=None):
        self.providers["code_action"][cb_id] = language_ids
        if hasattr(self.window, "register_plugin_code_action_provider"):

            def _actions(line, col, filepath="", language=""):
                items = self._invoke_provider(cb_id, line, col, filepath, language) or []
                out = []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item = dict(item)
                    aid = item.pop("action_id", None)
                    if aid is not None:
                        item["callback"] = lambda _aid=aid: self._invoke_provider(_aid)
                    out.append(item)
                return out

            self.window.register_plugin_code_action_provider(
                _actions, language_ids or [], plugin_name or "unknown"
            )
        return True

    def add_editor_context_menu(self, label, cb_id, plugin_name=None):
        if hasattr(self.window, "add_plugin_editor_context_action"):
            self.window.add_plugin_editor_context_action(
                str(label), lambda: self._invoke_provider(cb_id), plugin_name or "unknown"
            )
            return True
        return False

    def register_completion_provider(self, cb_id, language_ids=None):
        self.providers["completion"][cb_id] = language_ids
        return True

    def log(self, message, level="info"):
        logger.info("[%s] %s", level, message)
        self._bridge.submit(lambda: self.window.statusBar().showMessage(str(message), 3000))
        return True


class IsolatedPluginHost(QObject):
    """管理多个隔离插件进程 + 窗口 API 桥。"""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.api = WindowHostAPI(window)
        self.runtimes = {}
        self.api.invoke_callback = self.invoke

    def start(self, names, plugins_dir=None):
        root = plugins_dir or os.path.join(ROOT, "plugins")
        for name in names:
            plugin_dir = os.path.join(root, name)
            if not os.path.isdir(plugin_dir):
                continue
            allowed_hosts = []
            try:
                import json

                manifest = json.load(
                    open(os.path.join(plugin_dir, "plugin.json"), encoding="utf-8")
                )
                allowed_hosts = manifest.get("network_allowlist") or []
            except Exception:
                pass
            policy = SandboxPolicy([plugin_dir, ROOT], allowed_hosts)
            proc = PluginProcess(plugin_dir, self.api, timeout=15, policy=policy)
            self.api.host = proc
            try:
                proc.start()
                self.runtimes[name] = proc
                logger.info("isolated plugin started: %s", name)
            except PluginHostError as e:
                logger.warning("isolated plugin failed: %s (%s)", name, e)
                proc.stop()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.stop_all)
        return self

    def invoke(self, callback_id, *args):
        for proc in self.runtimes.values():
            try:
                return proc.invoke_callback(callback_id, *args)
            except Exception:
                continue
        return None

    def stop_all(self):
        for name, proc in list(self.runtimes.items()):
            try:
                proc.stop()
            except Exception:
                pass
            self.runtimes.pop(name, None)
