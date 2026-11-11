# -*- coding: utf-8 -*-
"""v2.25 市场：社区评分样本提示"""


def test_community_tooltip_sample_hint(qapp):
    from PyQt5.QtWidgets import QLabel

    from ui.plugin_client import set_community_ratings
    from ui.plugin_store import PluginCard, PluginInfo

    set_community_ratings({"demo": {"average": 4.5, "count": 2}})
    card = PluginCard(PluginInfo(name="demo"))
    try:
        labels = [lab for lab in card.findChildren(QLabel) if "社区" in (lab.text() or "")]
        assert labels, "未找到社区评分标签"
        tip = labels[0].toolTip()
        assert "4.5" in tip and "2 人" in tip
        assert "样本不足 3 人" in tip
    finally:
        card.deleteLater()
