# -*- coding: utf-8 -*-
"""Sprint 2：功能使用本地统计"""


def test_record_top_low_and_disable(tmp_path, monkeypatch):
    from core import feature_usage as fu

    fu.set_path(str(tmp_path / "u.json"))
    monkeypatch.setenv("QINGCAO_FEATURE_USAGE", "1")
    fu.record("a")
    fu.record("a")
    fu.record("b")
    assert fu.top(1)[0][0] == "a"
    assert fu.low(1)[0][0] == "b"
    monkeypatch.setenv("QINGCAO_FEATURE_USAGE", "0")
    assert fu.record("c") is False


def test_instrument_action(qapp, tmp_path, monkeypatch):
    from PyQt5.QtWidgets import QAction

    from core import feature_usage as fu

    fu.set_path(str(tmp_path / "u2.json"))
    monkeypatch.setenv("QINGCAO_FEATURE_USAGE", "1")
    a = QAction("x")
    assert fu.instrument_action(a, "菜单/测试")
    a.trigger()
    assert fu.snapshot()["菜单/测试"]["count"] == 1
