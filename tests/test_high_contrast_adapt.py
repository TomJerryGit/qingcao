# -*- coding: utf-8 -*-
"""v2.13.0 P0：高对比度自动适配"""
import os
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def _set_follow(value):
    from PyQt5.QtCore import QSettings
    s = QSettings("QingCao", "Editor")
    s.setValue("follow_system_high_contrast", value)
    s.sync()


def test_high_contrast_qss_builder():
    from infrastructure.theme_loader import build_high_contrast_qss
    q = build_high_contrast_qss()
    assert "palette(" in q
    assert "QPlainTextEdit" in q and "QMenuBar" in q


def test_system_high_contrast_detect_type():
    from infrastructure.theme_loader import system_high_contrast
    val = system_high_contrast()
    assert val in (True, False, None)


def test_apply_when_system_high_contrast(qapp):
    from ui.main_window import MainWindow
    _set_follow(True)
    win = MainWindow()
    try:
        with patch("infrastructure.theme_loader.system_high_contrast",
                   return_value=True), \
             patch("infrastructure.theme_loader.build_high_contrast_qss",
                   return_value="QC-HC-QSS-TEST"):
            assert win.apply_high_contrast_if_needed() is True
        assert "QC-HC-QSS-TEST" in win.styleSheet()
        assert win._system_high_contrast is True
    finally:
        _set_follow(True)
        _close(win)


def test_respects_follow_off(qapp):
    from ui.main_window import MainWindow
    _set_follow(False)
    win = MainWindow()
    try:
        with patch("infrastructure.theme_loader.system_high_contrast",
                   return_value=True):
            assert win.apply_high_contrast_if_needed() is False
    finally:
        _set_follow(True)
        _close(win)


def test_startup_wired_static():
    src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    assert "apply_high_contrast_if_needed" in src
    win_src = open(os.path.join(ROOT, "ui", "main_window.py"),
                   encoding="utf-8").read()
    assert "_follow_system_high_contrast" in win_src
    assert "跟随系统高对比度" in win_src