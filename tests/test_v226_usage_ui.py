# -*- coding: utf-8 -*-
"""v2.26 P2：使用统计 UI + 无障碍覆盖"""

import importlib.util
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_usage_dialog_rows(qapp, tmp_path, monkeypatch):
    from core import plugin_usage

    plugin_usage.set_path(str(tmp_path / "u.json"))
    plugin_usage.record("demo", "activate")
    from ui.plugin_usage_dialog import PluginUsageDialog

    dlg = PluginUsageDialog()
    try:
        assert dlg.table.rowCount() == 1
        assert dlg.table.item(0, 0).text() == "demo"
    finally:
        dlg.close()


def test_accessibility_tool_passes():
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, "tools/check_accessibility.py"], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stdout + r.stderr
