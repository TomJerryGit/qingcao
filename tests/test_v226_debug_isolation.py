# -*- coding: utf-8 -*-
"""v2.26 D6：python_debugger 隔离分支"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_debugger_is_isolatable():
    from app.plugin_isolation import ISOLATABLE_PLUGINS

    assert "python_debugger" in ISOLATABLE_PLUGINS


def test_broker_has_debug_permissions():
    from core.plugin_host import METHOD_PERMISSIONS

    for name in (
        "debug_start",
        "debug_stop",
        "debug_continue",
        "debug_step",
        "debug_set_breakpoints",
        "debug_locals",
        "debug_stack",
        "debug_eval",
    ):
        assert METHOD_PERMISSIONS.get(name) == "debugger"


def test_plugin_has_isolated_branch():
    src = open("plugins/python_debugger/__init__.py", encoding="utf-8").read()
    assert "_isolated_mode" in src
    assert "api.debug_start" in src and "api.debug_stop" in src
