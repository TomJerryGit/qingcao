# -*- coding: utf-8 -*-
"""v2.26 B3-D6：PluginAPI debug_*（flag 默认关闭）"""

import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _api():
    from app.plugins import PluginAPI

    return PluginAPI(None, permissions=["debugger"], plugin_name="dbg_test")


def test_debug_disabled_by_default(monkeypatch):
    monkeypatch.delenv("QINGCAO_DEBUGGER_HOST", raising=False)
    api = _api()
    assert api.debug_available() is False
    assert api.debug_start("a.py")["ok"] is False
    assert api.debug_show_panel() is False


def test_debug_enabled_methods(monkeypatch):
    monkeypatch.setenv("QINGCAO_DEBUGGER_HOST", "1")
    api = _api()
    assert api.debug_available() is True
    # 非法脚本：service 返回 ok=False，而不是异常
    result = api.debug_start("definitely_missing_file.py")
    assert result["ok"] is False
    assert api.debug_stop()["ok"] is True


def test_api_has_debug_methods():
    src = open(os.path.join(ROOT, "app", "plugin_api_debug.py"), encoding="utf-8").read()
    for name in ("debug_start", "debug_stop", "debug_step", "debug_show_panel"):
        assert name in src
