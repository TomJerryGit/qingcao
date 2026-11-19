# -*- coding: utf-8 -*-
"""Windows 子进程窗口控制：避免 GUI 程序弹出/闪烁 CMD 窗口。"""

import os
import subprocess


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def hidden_kwargs():
    if os.name != "nt":
        return {}
    return {"creationflags": CREATE_NO_WINDOW}


def install_no_window_default():
    """把 subprocess.Popen 默认设为 CREATE_NO_WINDOW（进程级）。"""
    if os.name != "nt":
        return False
    orig = subprocess.Popen
    if getattr(orig, "_qc_no_window", False):
        return True

    def popen(*args, **kwargs):
        kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
        return orig(*args, **kwargs)

    popen._qc_no_window = True
    subprocess.Popen = popen
    return True
