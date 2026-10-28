# -*- coding: utf-8 -*-
"""v2.12.0 P2：大文件跳过实时诊断 + 主题性能门禁"""
import importlib.util
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _FakeDoc:
    filepath = ""


class _FakeProxy:
    def __init__(self, text):
        self._text = text
        self.document = _FakeDoc()

    def get_text(self):
        return self._text


class _FakeSandbox:
    def __init__(self):
        self.diag_calls = 0

    def diagnostics(self, text):
        self.diag_calls += 1
        return []


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def _set_pref(enabled):
    from PyQt5.QtCore import QSettings
    s = QSettings("QingCao", "Editor")
    s.setValue("sandbox_live_diagnostics", enabled)
    s.sync()


def test_large_file_skips_live_diagnostics(qapp):
    from unittest.mock import patch

    from ui.main_window import MainWindow
    _set_pref(True)
    win = MainWindow()
    fake = _FakeSandbox()
    try:
        win._sandboxed_plugins = {"big": fake}
        big = "x" * (win.MAX_LIVE_DIAGNOSTICS_BYTES + 10)
        with patch.object(win.tabs, "current_proxy",
                          return_value=_FakeProxy(big)):
            assert win._run_live_sandbox_diagnostics() == 0
        assert fake.diag_calls == 0
    finally:
        _set_pref(False)
        _close(win)


def test_small_file_runs_live_diagnostics(qapp):
    from unittest.mock import patch

    from ui.main_window import MainWindow
    _set_pref(True)
    win = MainWindow()
    fake = _FakeSandbox()
    try:
        win._sandboxed_plugins = {"small": fake}
        with patch.object(win.tabs, "current_proxy",
                          return_value=_FakeProxy("hello")):
            win._run_live_sandbox_diagnostics()
        assert fake.diag_calls >= 1
    finally:
        _set_pref(False)
        _close(win)


def test_theme_reapply_in_bench_thresholds():
    path = os.path.join(ROOT, "tools", "bench_optimization.py")
    spec = importlib.util.spec_from_file_location("qc_bench", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert "theme_reapply" in mod.THRESHOLDS
    assert mod.THRESHOLDS["theme_reapply"] > 0