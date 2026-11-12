# -*- coding: utf-8 -*-
"""B1.5：把隔离插件（PluginProcess）接到主窗口菜单/状态栏。"""

import logging
import os

from PyQt5.QtCore import QObject, QSettings, QThread, pyqtSignal
from PyQt5.QtWidgets import QAction, QApplication, QLabel, QMenu, QMessageBox

from core.plugin_sandbox_policy import SandboxPolicy
from core.plugin_supervisor import PluginHostError, PluginProcess


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
        self._cache_text()
        self.menus = {}
        self.status_items = {}
        self.settings = QSettings("QingCao", "PluginData")
        self._next_status = 1
        self._schemas = {}

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

    def invoke(self, callback_id):
        if self.host is None:
            return None
        try:
            if hasattr(self.host, "invoke_callback"):
                return self.host.invoke_callback(callback_id)
            return self.host.invoke(callback_id)
        except Exception as e:
            logger.warning("isolated menu callback failed: %s", e)
            return None

    # ---- 配置 ----
    def get_config(self, key, default=None):
        return self.settings.value("plugins/%s" % key, default)

    def set_config(self, key, value):
        self.settings.setValue("plugins/%s" % key, value)
        return True

    def register_settings_schema(self, schema):
        self._schemas[id(schema)] = schema
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

    def start(self, names, plugins_dir=None):
        root = plugins_dir or os.path.join(ROOT, "plugins")
        for name in names:
            plugin_dir = os.path.join(root, name)
            if not os.path.isdir(plugin_dir):
                continue
            policy = SandboxPolicy([plugin_dir, ROOT])
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

    def invoke(self, callback_id):
        for proc in self.runtimes.values():
            try:
                return proc.invoke_callback(callback_id)
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
