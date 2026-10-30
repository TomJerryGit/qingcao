# -*- coding: utf-8 -*-
"""v2.17 P1：插件市场 UI 完善（筛选/徽章/依赖/回滚）"""
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _infos():
    from ui.plugin_store import PluginInfo
    return {
        "ed": PluginInfo(name="ed", signature="s", signature_algo="ed25519"),
        "hm": PluginInfo(name="hm", signature="s", signature_algo="hmac"),
        "sha": PluginInfo(name="sha", file_hash="a" * 64),
        "plain": PluginInfo(name="plain"),
    }


def test_security_bucket_and_filter(monkeypatch):
    from ui.plugin_store import filter_plugins_by_security, plugin_security_bucket
    infos = _infos()
    assert plugin_security_bucket(infos["ed"]) == "ed25519"
    assert plugin_security_bucket(infos["hm"]) == "hmac"
    assert plugin_security_bucket(infos["sha"]) == "sha256"
    assert plugin_security_bucket(infos["plain"]) == "unsigned"
    only = filter_plugins_by_security(list(infos.values()), "ed25519")
    assert [p.name for p in only] == ["ed"]
    assert len(filter_plugins_by_security(list(infos.values()), "all")) == 4

    monkeypatch.setenv("QINGCAO_PLUGIN_REVOKED", "ed")
    assert plugin_security_bucket(infos["ed"]) == "revoked"
    assert filter_plugins_by_security(list(infos.values()), "revoked")


def test_source_badge():
    from ui.plugin_store import PluginInfo, plugin_source_badge
    assert plugin_source_badge(PluginInfo(name="a", installed=True)) == "本地"
    assert plugin_source_badge(PluginInfo(name="b", verified=True)) == "官方"
    assert plugin_source_badge(PluginInfo(name="c")) == "第三方"


def test_card_badges_and_detail_dependency(qapp):
    from ui.plugin_store import PluginCard, PluginDetailDialog, PluginInfo
    info = PluginInfo(name="demo", display_name="Demo",
                      file_hash="b" * 64,
                      dependencies=["definitely_missing_pkg_xyz"])
    card = PluginCard(info)
    try:
        texts = [c.text() for c in card.findChildren(object)
                 if hasattr(c, "text")]
        joined = " ".join(t for t in texts if isinstance(t, str))
        assert "第三方" in joined
        assert "sha256" in joined
    finally:
        card.close()
    dlg = PluginDetailDialog(info)
    try:
        html = dlg._build_html()
        assert "安全状态" in html
        assert "依赖状态" in html
        assert "缺失" in html
    finally:
        dlg.close()


def test_market_ui_wiring_static():
    src = open(os.path.join(ROOT, "ui", "plugin_store.py"),
               encoding="utf-8").read()
    for key in ("SECURITY_FILTERS", "security_combo",
                "filter_plugins_by_security", "回滚", "重载插件"):
        assert key in src, key