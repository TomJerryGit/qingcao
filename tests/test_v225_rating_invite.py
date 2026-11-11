# -*- coding: utf-8 -*-
"""v2.25 市场生态：评分邀请 + 详情社区评分提示"""


def test_should_show_rating_invite():
    from ui.plugin_client import PluginState
    from ui.plugin_store import PluginInfo, should_show_rating_invite

    installed = PluginInfo(name="a", state=PluginState.INSTALLED)
    not_installed = PluginInfo(name="b", state=PluginState.NOT_INSTALLED)
    assert should_show_rating_invite([installed], {}, False) is True
    assert should_show_rating_invite([installed], {"a": {"stars": 5}}, False) is False
    assert should_show_rating_invite([installed], {}, True) is False
    assert should_show_rating_invite([not_installed], {}, False) is False


def test_detail_community_tooltip(qapp):
    from PyQt5.QtWidgets import QLabel

    from ui.plugin_client import set_community_ratings
    from ui.plugin_detail import PluginDetailDialog
    from ui.plugin_store import PluginInfo

    set_community_ratings({"demo": {"average": 4.5, "count": 2}})
    dlg = PluginDetailDialog(PluginInfo(name="demo"))
    try:
        labels = [x for x in dlg.findChildren(QLabel) if "社区" in (x.text() or "")]
        assert labels, "详情未显示社区评分"
        assert "2 人" in labels[0].text()
        assert "样本不足 3 人" in labels[0].toolTip()
    finally:
        set_community_ratings({})
        dlg.deleteLater()
