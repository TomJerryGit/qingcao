# -*- coding: utf-8 -*-
"""P1 第3步：沙箱插件菜单 UI"""
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _FakeSandbox:
    def __init__(self):
        self.invoked = []

    def menu_items(self):
        return [
            {"id": "ignore_all", "label": "忽略全部",
             "path": "工具/拼写检查"},
            {"id": "recheck", "label": "重新检查", "path": ""},
        ]

    def invoke_menu(self, mid):
        self.invoked.append(mid)
        return mid == "ignore_all"

    def status_text(self):
        return "拼写: 0 条"

    def diagnostics(self, text):
        return []


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def test_refresh_menu_builds_actions_and_invokes(qapp):
    from ui.main_window import MainWindow
    win = MainWindow()
    fake = _FakeSandbox()
    try:
        win._sandboxed_plugins = {"spell": fake}
        n = win.refresh_sandbox_plugin_menus(quiet=True)
        assert n == 2
        sub = win._sandbox_menu
        labels = [a.text() for a in sub.actions()]
        assert any("忽略全部" in t for t in labels)
        assert any("刷新插件菜单" in t for t in labels)
        target = next(a for a in sub.actions()
                      if "忽略全部" in a.text())
        target.trigger()
        assert fake.invoked == ["ignore_all"]
    finally:
        _close(win)


def test_refresh_menu_without_plugins(qapp):
    from ui.main_window import MainWindow
    win = MainWindow()
    try:
        win._sandboxed_plugins = {}
        assert win.refresh_sandbox_plugin_menus(quiet=True) == 0
        labels = [a.text() for a in win._sandbox_menu.actions()]
        assert any("无可用沙箱插件" in t for t in labels)
    finally:
        _close(win)


def test_ui_wired_static():
    src = open(os.path.join(ROOT, "ui", "main_window.py"),
               encoding="utf-8").read()
    assert "refresh_sandbox_plugin_menus" in src
    assert "_invoke_sandbox_menu" in src
    assert "插件菜单" in src