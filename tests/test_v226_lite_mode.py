# -*- coding: utf-8 -*-
"""Lite 模式默认隐藏市场入口"""
import importlib


def test_lite_default_and_override(monkeypatch):
    from core import feature_policy as fp

    monkeypatch.delenv("QINGCAO_LITE", raising=False)
    assert fp.lite_mode() is True
    assert fp.show_market() is False
    monkeypatch.setenv("QINGCAO_LITE", "0")
    assert fp.lite_mode() is False
    assert fp.show_market() is True


def test_welcome_hides_market_by_default(monkeypatch):
    monkeypatch.delenv("QINGCAO_LITE", raising=False)
    import ui.welcome_widget_common as w

    importlib.reload(w)
    keys = [a[3] for a in w.QUICK_ACTIONS]
    assert "plugin_store" not in keys
