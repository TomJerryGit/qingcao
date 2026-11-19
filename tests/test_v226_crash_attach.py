# -*- coding: utf-8 -*-
"""Sprint 1：ProcDump 自动附加"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_build_command():
    from tools.crash_attach import build_command

    cmd = build_command("procdump.exe", "d", target=["python", "x.py"])
    assert "-x" in cmd and cmd[-2:] == ["python", "x.py"]
    cmd2 = build_command("procdump.exe", "d", pid=123)
    assert cmd2[-2] == "123" and cmd2[-1] == "d"
