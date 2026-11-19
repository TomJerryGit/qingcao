# -*- coding: utf-8 -*-
"""Sprint 4：使用统计趋势"""


def test_trend_aggregates_daily(tmp_path, monkeypatch):
    from core import plugin_usage

    plugin_usage.set_path(str(tmp_path / "u.json"))
    monkeypatch.setenv("QINGCAO_PLUGIN_USAGE", "1")
    plugin_usage.record("demo", "activate")
    plugin_usage.record("demo", "activate")
    plugin_usage.record("demo", "deactivate")
    rows = plugin_usage.trend(7)
    assert rows and rows[-1]["activate"] == 2 and rows[-1]["deactivate"] == 1


def test_usage_dialog_has_trend(qapp, tmp_path, monkeypatch):
    from core import plugin_usage

    plugin_usage.set_path(str(tmp_path / "u2.json"))
    plugin_usage.record("demo", "activate")
    from ui.plugin_usage_dialog import PluginUsageDialog

    dlg = PluginUsageDialog()
    try:
        assert dlg.trend_table.rowCount() >= 1
    finally:
        dlg.close()
