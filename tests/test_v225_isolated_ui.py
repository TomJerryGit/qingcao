# -*- coding: utf-8 -*-
"""v2.25 沙箱 B1.5：隔离插件接到窗口菜单/状态栏"""

import time

from PyQt5.QtWidgets import QMainWindow, QMessageBox


def _pump(qapp, cond, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.05)
        if cond():
            return True
    return False


def test_window_host_api_menu_status(tmp_path, monkeypatch, qapp):
    from core.plugin_supervisor import PluginProcess
    from ui.isolated_plugins import WindowHostAPI

    d = tmp_path / "ui_plugin"
    d.mkdir()
    (d / "plugin.json").write_text(
        '{"name": "ui_plugin", "version": "1.0.0", "permissions": ["dialog"]}', encoding="utf-8"
    )
    (d / "__init__.py").write_text(
        """
class Plugin:
    def on_activate(self):
        self.api.add_menu("工具/隔离测试/运行", self.run)
        self.api.add_status_item("隔离就绪")
    def run(self):
        self.api.show_message("隔离", "callback-ok")
    def on_deactivate(self):
        pass
""",
        encoding="utf-8",
    )
    win = QMainWindow()
    api = WindowHostAPI(win)
    proc = PluginProcess(str(d), api, timeout=15)
    api.host = proc
    captured = {}
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: captured.setdefault("msg", a))
    try:
        proc.start()
        assert _pump(qapp, lambda: bool(api.menus) and bool(api.status_items))
        texts = [a.text() for a in win.menuBar().actions()]
        assert any(t.replace("&", "") == "工具" for t in texts)
        menu = next(
            a.menu() for a in win.menuBar().actions() if a.text().replace("&", "") == "工具"
        )
        sub = next(a.menu() for a in menu.actions() if a.text().replace("&", "") == "隔离测试")
        action = next(a for a in sub.actions() if a.text() == "运行")
        action.trigger()
        assert _pump(qapp, lambda: bool(captured.get("msg")))
        assert "callback-ok" in str(captured.get("msg"))
        assert api.status_items
    finally:
        proc.stop()
        win.close()


def test_demo_isolated_with_window_host(qapp, monkeypatch):
    """真实 demo 插件经 PluginProcess + QMainWindow 宿主菜单/状态栏。"""
    from app.plugin_isolation import isolated_plugin_names
    from ui.isolated_plugins import IsolatedPluginHost

    monkeypatch.setenv("QINGCAO_PLUGIN_ISOLATION", "demo")
    assert "demo" in isolated_plugin_names()

    win = QMainWindow()
    host = IsolatedPluginHost(win)
    captured = {}
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: captured.setdefault("msg", a))
    try:
        host.start({"demo"})
        assert "demo" in host.runtimes
        assert _pump(qapp, lambda: bool(host.api.menus) and bool(host.api.status_items)), (
            "demo 菜单/状态项未注册"
        )
        for cid in host.api.menus:
            host.invoke(cid)
            break
        assert _pump(qapp, lambda: bool(captured.get("msg"))), "demo 回调未执行"
    finally:
        host.stop_all()
        win.close()


def test_manager_excludes_isolated_plugins():
    src = open("app/plugin_manager.py", encoding="utf-8").read()
    assert "isolated_plugin_names" in src
