# -*- coding: utf-8 -*-
"""v2.26 P2：插件设置覆盖率"""

import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_all_plugins_have_settings_schema():
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "check_plugin_settings.py")],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
