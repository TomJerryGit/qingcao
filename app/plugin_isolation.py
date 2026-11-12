# -*- coding: utf-8 -*-
"""插件隔离开关（B1）：QINGCAO_PLUGIN_ISOLATION=off|demo|all。"""
import os


DEMO_PLUGINS = {"demo", "sandbox_demo"}


def isolation_mode():
    return (os.environ.get("QINGCAO_PLUGIN_ISOLATION", "off") or "off").strip().lower()


def should_isolate(plugin_name):
    mode = isolation_mode()
    if mode in ("1", "all", "strict"):
        return True
    if mode == "demo":
        return plugin_name in DEMO_PLUGINS
    return False
