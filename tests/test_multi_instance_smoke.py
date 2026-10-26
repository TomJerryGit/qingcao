# -*- coding: utf-8 -*-
"""P1：多实例冒烟脚本可运行且通过"""
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_multi_instance_smoke():
    path = os.path.join(ROOT, "tools", "smoke_multi_instance.py")
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    out = subprocess.run([sys.executable, path], cwd=ROOT, env=env,
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr