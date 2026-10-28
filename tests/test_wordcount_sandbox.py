# -*- coding: utf-8 -*-
"""wordcount 沙箱试点：状态栏文本 RPC"""
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_wordcount_sandbox_status_text():
    from infrastructure.plugin_sandbox_manager import SandboxedPlugin
    path = os.path.join(ROOT, "plugins", "wordcount_sandbox")
    sp = SandboxedPlugin(path, timeout=8)
    try:
        txt = sp.status_text("hello world foo")
        assert "字数: 3" in txt
        assert "字符: 15" in txt
    finally:
        sp.close()


def test_manifest_sandbox_enabled():
    import json
    m = json.load(open(os.path.join(
        ROOT, "plugins", "wordcount_sandbox", "plugin.json"),
        encoding="utf-8"))
    assert m.get("sandbox") is True
    assert m.get("enabled") is True


def test_host_refresh_passes_text(qapp):
    from unittest.mock import patch

    from ui.main_window import MainWindow
    win = MainWindow()
    seen = {}

    class FakeSp:
        def status_text(self, text=None):
            seen["text"] = text
            return "字数: 1"

    class Proxy:
        document = type("D", (), {"filepath": ""})()

        def get_text(self):
            return "hello"

    try:
        win._sandboxed_plugins = {"wc": FakeSp()}
        with patch.object(win.tabs, "current_proxy", return_value=Proxy()):
            win._refresh_sandbox_status()
        assert seen.get("text") == "hello"
    finally:
        try:
            sess = getattr(win, "session", None)
            if sess is not None and hasattr(sess, "save"):
                sess.save = lambda *a, **k: None
        except Exception:
            pass
        win.close()