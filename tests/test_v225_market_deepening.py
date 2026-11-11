# -*- coding: utf-8 -*-
"""v2.25 市场深化：社区评分排序 + 卡片双击/回车打开详情"""


def test_community_rating_sort_option():
    from ui.plugin_client import SORT_OPTIONS

    assert ("community_rating", "按社区评分") in SORT_OPTIONS


def test_sort_implementation_static():
    src = open("ui/plugin_store.py", encoding="utf-8").read()
    assert 'self._current_sort == "community_rating"' in src
    assert "get_community_rating(p.name)" in src


def test_card_enter_opens_detail(qapp):
    from PyQt5.QtCore import QEvent, Qt
    from PyQt5.QtGui import QKeyEvent

    from ui.plugin_store import PluginCard, PluginInfo

    card = PluginCard(PluginInfo(name="demo"))
    got = []
    card.detail_clicked.connect(lambda info: got.append(info.name))
    try:
        card.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
        assert got == ["demo"]
    finally:
        card.deleteLater()
