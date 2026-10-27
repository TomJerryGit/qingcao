# -*- coding: utf-8 -*-
"""v2.11.0 P0：沙箱配置热更新"""
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _FakeSandbox:
    def __init__(self):
        self.applied = []
        self.diag_calls = 0

    def config_schema(self):
        return {"enabled": {"type": "bool", "label": "启用",
                            "default": True},
                "max_words": {"type": "int", "label": "上限",
                              "default": 10}}

    def config_apply(self, values):
        self.applied.append(values)
        return True

    def diagnostics(self, text):
        self.diag_calls += 1
        return []

    def menu_items(self):
        return []


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def test_config_saved_hot_apply(qapp, tmp_path):
    from PyQt5.QtCore import QSettings

    from ui.main_window import MainWindow
    win = MainWindow()
    fake = _FakeSandbox()
    try:
        f = tmp_path / "hot.txt"
        f.write_text("hello\n", encoding="utf-8")
        win.tabs.open_file(str(f))
        win._sandboxed_plugins = {"hot_cfg": fake}
        ok = win._sandbox_config_saved(
            "hot_cfg", {"enabled": False, "max_words": 33})
        assert ok is True
        assert fake.applied and fake.applied[-1]["enabled"] is False
        assert fake.applied[-1]["max_words"] == 33
        assert fake.diag_calls >= 1
    finally:
        try:
            s = QSettings("QingCao", "Plugin_hot_cfg")
            s.clear()
            s.sync()
        except Exception:
            pass
        _close(win)


def test_hot_update_wired_static():
    src = open(os.path.join(ROOT, "ui", "main_window.py"),
               encoding="utf-8").read()
    assert "_sandbox_config_saved" in src
    assert "run_sandboxed_diagnostics" in src