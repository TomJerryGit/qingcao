# -*- coding: utf-8 -*-
"""v2.26 P2：插件 UI 无障碍"""

import subprocess
import sys


def test_plugin_ui_accessibility():
    r = subprocess.run(
        [sys.executable, "tools/check_accessibility.py"], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout + r.stderr
