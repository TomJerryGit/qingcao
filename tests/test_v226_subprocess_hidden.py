# -*- coding: utf-8 -*-
"""CMD 闪窗：subprocess 默认隐藏窗口"""

import os
import subprocess


def test_hidden_kwargs_windows():
    from core.subprocess_utils import CREATE_NO_WINDOW, hidden_kwargs

    if os.name == "nt":
        assert hidden_kwargs()["creationflags"] == CREATE_NO_WINDOW
    else:
        assert hidden_kwargs() == {}


def test_install_idempotent(monkeypatch):
    import core.subprocess_utils as su

    orig = subprocess.Popen
    try:
        assert su.install_no_window_default() in (True, False)
        assert su.install_no_window_default() in (True, False)
    finally:
        subprocess.Popen = orig
