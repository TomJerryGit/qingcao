# -*- coding: utf-8 -*-
"""P1 配置代理第3步：设置 UI + 启动下发"""
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _FakeSandbox:
    def __init__(self):
        self.applied = []

    def config_schema(self):
        return {"enabled": {"type": "bool", "label": "启用",
                            "default": True}}

    def config_apply(self, values):
        self.applied.append(values)
        return True

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


def test_apply_sandbox_configs_on_start(qapp):
    from PyQt5.QtCore import QSettings

    from ui.main_window import MainWindow
    win = MainWindow()
    fake = _FakeSandbox()
    try:
        win._sandboxed_plugins = {"cfg_test_ui": fake}
        count = win._apply_sandbox_configs()
        assert count == 1
        assert fake.applied and fake.applied[0]["enabled"] is True
    finally:
        try:
            s = QSettings("QingCao", "Plugin_cfg_test_ui")
            s.clear()
            s.sync()
        except Exception:
            pass
        _close(win)


def test_settings_ui_wired_static():
    src = open(os.path.join(ROOT, "ui", "main_window.py"),
               encoding="utf-8").read()
    assert "open_sandbox_plugin_settings" in src
    assert "_apply_sandbox_configs" in src
    assert "插件设置" in src
    assert "config_apply" in src