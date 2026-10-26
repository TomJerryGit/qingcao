# -*- coding: utf-8 -*-
"""P2：显示环境自检脚本可运行"""
import json
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_verify_display_env_json():
    path = os.path.join(ROOT, "tools", "verify_display_env.py")
    out = subprocess.run([sys.executable, path, "--json"], cwd=ROOT,
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=60)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    for key in ("monitor_count", "monitors", "primary_dpi",
                "high_contrast", "platform"):
        assert key in data
    assert isinstance(data["monitor_count"], int)