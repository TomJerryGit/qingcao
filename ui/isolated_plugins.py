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
    QPlainTextEdit,
    QTextBrowser,
    QVBoxLayout,
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

    def get_current_filepath(self):
        proxy = self._current_proxy()
        if proxy is None:
            return ""
        for attr in ("get_filepath", "filepath"):
            try:
                value = getattr(proxy, attr)
                return str(value() if callable(value) else value) or ""
            except Exception:
                continue
        try:
            return str(getattr(proxy.document, "filepath", "") or "")
        except Exception:
            return ""

    def show_text_dialog(self, title, text, width=600, height=400):
        self._bridge.submit(lambda: QMessageBox.information(self.window, str(title), str(text)))
        return True

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

    def _git_client(self, filepath):
        from core.git_client import GitClient

        root = GitClient().find_root(filepath)
        return GitClient(root) if root else None

    def _debug_service(self):
        from core.debug_service import get_debug_service

        return get_debug_service()

    def debug_start(self, script, args=None):
        return self._debug_service().handle(
            "debug.start", {"script": str(script), "args": list(args or [])}
        )

    def debug_stop(self):
        return self._debug_service().handle("debug.stop")

    def debug_continue(self):
        return self._debug_service().handle("debug.continue")

    def debug_step(self, kind="over"):
        return self._debug_service().handle("debug.step", {"kind": kind})

    def debug_set_breakpoints(self, files):
        return self._debug_service().handle("debug.set_breakpoints", {"files": files or {}})

    def debug_locals(self):
        return self._debug_service().handle("debug.locals")

    def debug_stack(self):
        return self._debug_service().handle("debug.stack")

    def debug_eval(self, expr):
        return self._debug_service().handle("debug.eval", {"expr": str(expr)})

    def debug_context(self):
        service = self._debug_service()
        return {
            "locals": getattr(service, "last_locals", None),
            "stack": getattr(service, "last_stack", None),
            "breakpoint": getattr(service, "last_break", None),
        }

    def debug_show_panel(self):
        from ui.debug_host_panel import DebugHostPanel

        def _create():
            panel = getattr(self, "_debug_panel", None)
            if panel is None:
                panel = DebugHostPanel(self._debug_service(), self.window)
                self._debug_panel = panel
                self.window.addDockWidget(Qt.BottomDockWidgetArea, panel)
            panel.show()
            panel.raise_()

        self._bridge.submit(_create)
        return True

    def ai_run(
        self, prompt, system="", max_tokens=None, stream=False, use_history=False, session="default"
    ):
        from core.ai_service import get_ai_service

        return get_ai_service().run(
            prompt, system, max_tokens, bool(stream), bool(use_history), str(session)
        )

    def ai_preview_diff(self, text):
        import difflib

        def _show():
            proxy = self._current_proxy()
            if proxy is None:
                return
            try:
                selected = getattr(proxy, "selected_text", None)
                old = str(selected() if callable(selected) else "")
                if not old:
                    old = str(proxy.text())
            except Exception:
                old = ""
            diff = "".join(
                difflib.unified_diff(
                    old.splitlines(True),
                    str(text).splitlines(True),
                    fromfile="当前代码",
                    tofile="AI 建议",
                )
            )
            QMessageBox.information(self.window, "AI 差异预览", diff or "无差异")

        self._bridge.submit(_show)
        return True

    def ai_apply_result(self, text, mode="insert"):
        def _apply():
            proxy = self._current_proxy()
            if proxy is None:
                return
            try:
                if mode == "replace" and hasattr(proxy, "replace_selected_text"):
                    proxy.replace_selected_text(str(text))
                    return
                if hasattr(proxy, "insert_text"):
                    proxy.insert_text(str(text))
                    return
                sc = getattr(proxy, "sc", None)
                if sc is None:
                    return
                if mode == "replace":
                    sc.replaceSelectedText(str(text))
                else:
                    pos = sc.SendScintilla(sc.SCI_GETCURRENTPOS)
                    sc.SendScintilla(sc.SCI_INSERTTEXT, pos, str(text).encode("utf-8"))
            except Exception:
                pass

        self._bridge.submit(_apply)
        return True

    def ai_current_session(self):
        from core.ai_service import get_ai_service

        return get_ai_service().current_session()

    def ai_set_current_session(self, session):
        from core.ai_service import get_ai_service

        return get_ai_service().set_current_session(session)

    def ai_reset_history(self, session="default"):
        from core.ai_service import get_ai_service

        return get_ai_service().reset_history(str(session))

    def ai_show_panel(self):
        from ui.ai_host_panel import AIHostPanel

        buf = getattr(self, "_ai_buf", None)
        if buf is None:
            buf = []
            self._ai_buf = buf

        def _listener(chunk):
            panel = getattr(self, "_ai_panel", None)
            if panel is None:
                buf.append(str(chunk))
            else:
                self._bridge.submit(lambda c=str(chunk): panel.append_chunk(c))

        from core.ai_service import get_ai_service

        get_ai_service().set_stream_listener(_listener)

        def _create():
            if getattr(self, "_ai_panel", None) is None:
                panel = AIHostPanel(self.window)
                self._ai_panel = panel
                self.window.addDockWidget(Qt.BottomDockWidgetArea, panel)
            panel = self._ai_panel
            panel.clear()
            for chunk in buf:
                panel.append_chunk(chunk)
            buf.clear()
            panel.show()
            panel.raise_()
            # 远程面板注册：宿主侧统一发现/控制
            self.remote_panels["ai_output"] = {
                "dock": panel,
                "values": {},
                "cb": None,
                "kind": "ai",
                "text_widget": panel.view,
            }

        self._bridge.submit(_create)
        return True

    def ai_http_request(self, url, headers=None, json_data=None, timeout=60):
        from core.ai_http import request_json

        return request_json(url, headers=headers, json_data=json_data, timeout=timeout)

    def git_status(self, filepath):
        git = self._git_client(filepath)
        return git.status() if git else {}

    def git_branch(self, filepath):
        git = self._git_client(filepath)
        return git.current_branch() if git else ""

    def git_diff(self, filepath, staged=False):
        git = self._git_client(filepath)
        if not git:
            return ""
        return git.diff_staged(filepath) if staged else git.diff(filepath)

    def git_log(self, filepath, limit=30):
        git = self._git_client(filepath)
        return git.log(int(limit)) if git else []

    def git_commit(self, filepath, message):
        git = self._git_client(filepath)
        if not git:
            return [False, "不在 Git 仓库"]
        for path in git.status() or {}:
            git.add(path)
        ok, out = git.commit(message)
        return [bool(ok), out]

    def git_push(self, filepath):
        git = self._git_client(filepath)
        return list(git.push()) if git else [False, "不在 Git 仓库"]

    def git_pull(self, filepath):
        git = self._git_client(filepath)
        return list(git.pull()) if git else [False, "不在 Git 仓库"]

    def git_hunks(self, filepath):
        git = self._git_client(filepath)
        if not git:
            return []
        _code, diff, _err = git._run(["diff", "--", filepath])
        _header, hunks = git.parse_hunks(diff)
        return [{"index": i, "preview": "\n".join(h.splitlines()[:4])} for i, h in enumerate(hunks)]

    def git_stage_hunks(self, filepath, indices):
        git = self._git_client(filepath)
        if not git:
            return [False, "不在 Git 仓库"]
        ok, out = git.stage_hunks(filepath, indices)
        return [bool(ok), out]

    def git_switch(self, filepath, name, create=False):
        git = self._git_client(filepath)
        return list(git.switch_branch(name, bool(create))) if git else [False, "不在 Git 仓库"]

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

    def register_remote_panel(self, title, fields, refresh_cb, kind="fields"):
        self._panel_seq += 1
        pid = self._panel_seq

        def _create():
            dock = QDockWidget(str(title), self.window)
            body = QWidget(dock)
            values = {}
            text_widget = None
            if kind in ("text", "markdown"):
                text_widget = QPlainTextEdit() if kind == "text" else QTextBrowser()
                text_widget.setReadOnly(True) if kind == "text" else None
                body_layout = QVBoxLayout(body)
                body_layout.setContentsMargins(4, 4, 4, 4)
                body_layout.addWidget(text_widget)
            else:
                form = QFormLayout(body)
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
            self.remote_panels[pid] = {
                "dock": dock,
                "values": values,
                "cb": refresh_cb,
                "kind": kind,
                "text_widget": text_widget,
            }

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
                if rec.get("kind") in ("text", "markdown"):
                    widget = rec.get("text_widget")
                    body = result if isinstance(result, str) else str(result or "")
                    if widget is not None:
                        if rec.get("kind") == "markdown":
                            try:
                                widget.document().setMarkdown(body)
                            except Exception:
                                widget.setPlainText(body)
                        else:
                            widget.setPlainText(body)
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

    def update_remote_panel(self, panel_id, text):
        rec = self.remote_panels.get(panel_id)
        if rec is None:
            return False
        widget = rec.get("text_widget")

        def _apply():
            if widget is not None:
                widget.setPlainText(str(text))

        self._bridge.submit(_apply)
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
            trusted_names = {
                x.strip()
                for x in os.environ.get("QINGCAO_TRUSTED_PLUGINS", "").split(",")
                if x.strip()
            }
            try:
                from core.plugin_trust import verify_plugin_signature

                signed_ok, _msg = verify_plugin_signature(plugin_dir)
            except Exception:
                signed_ok = False
            proc = PluginProcess(
                plugin_dir,
                self.api,
                timeout=15,
                policy=policy,
                trusted=(name in trusted_names) or signed_ok,
                allow_high_risk=(name in trusted_names) or signed_ok,
            )
            self.api.host = proc
            try:
                proc.start()
                self.runtimes[name] = proc
                logger.info("isolated plugin started: %s", name)
            except PluginHostError as e:
                logger.warning("isolated plugin failed: %s (%s)", name, e)
                for level, msg in (proc.logs or [])[-20:]:
                    logger.warning("  child[%s] %s", level, msg)
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
