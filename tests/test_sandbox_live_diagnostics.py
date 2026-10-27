# -*- coding: utf-8 -*-
"""v2.11.0 P1：实时沙箱诊断"""
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def _set_pref(win, enabled):
    from PyQt5.QtCore import QSettings
    s = QSettings("QingCao", "Editor")
    s.setValue("sandbox_live_diagnostics", enabled)
    s.sync()


def test_live_diagnostics_disabled_by_default(qapp, tmp_path):
    from PyQt5.QtCore import QSettings

    from ui.main_window import MainWindow
    _set_pref(None, False)
    win = MainWindow()
    try:
        f = tmp_path / "live.txt"
        f.write_text("hello\n", encoding="utf-8")
        win.tabs.open_file(str(f))
        win._schedule_sandbox_diagnostics()
        timer = getattr(win, "_sandbox_diag_timer", None)
        assert timer is None or not timer.isActive()
    finally:
        _set_pref(None, False)
        _close(win)


def test_live_diagnostics_enabled_runs_after_debounce(qapp, tmp_path):
    from ui.main_window import MainWindow
    _set_pref(None, True)
    win = MainWindow()
    fake = _FakeSandbox()
    try:
        f = tmp_path / "live2.txt"
        f.write_text("hello\n", encoding="utf-8")
        win.tabs.open_file(str(f))
        win._sandboxed_plugins = {"live_diag": fake}
        assert win._sandbox_live_enabled() is True
        win._schedule_sandbox_diagnostics()
        assert win._sandbox_diag_timer.isActive()
        assert win._sandbox_diag_timer.interval() == 500
        win._sandbox_diag_timer.stop()
        win._run_live_sandbox_diagnostics()
        assert fake.diag_calls >= 1
    finally:
        _set_pref(None, False)
        _close(win)


def test_live_diagnostics_wired_static():
    src = open(os.path.join(ROOT, "ui", "main_window.py"),
               encoding="utf-8").read()
    assert "_schedule_sandbox_diagnostics" in src
    assert "_run_live_sandbox_diagnostics" in src
    assert "实时沙箱诊断" in src