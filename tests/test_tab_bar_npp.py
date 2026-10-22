# -*- coding: utf-8 -*-
"""标签栏 NPP 习惯：中键关闭 / 双击空白处新建"""
from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QMouseEvent


def test_middle_click_closes_tab(qapp):
    from app.tabs import TabManager

    tabs = TabManager()
    tabs.add_tab("A")
    tabs.add_tab("B")
    assert tabs.count() == 2
    bar = tabs.tabBar()
    rect = bar.tabRect(0)
    ev = QMouseEvent(QEvent.MouseButtonPress, rect.center(),
                     Qt.MiddleButton, Qt.MiddleButton, Qt.NoModifier)
    tabs.eventFilter(bar, ev)
    assert tabs.count() == 1


def test_double_click_blank_creates_tab(qapp):
    from app.tabs import TabManager

    tabs = TabManager()
    n = tabs.count()
    bar = tabs.tabBar()
    far = QPoint(bar.width() + 100, 5)
    ev = QMouseEvent(QEvent.MouseButtonDblClick, far,
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    tabs.eventFilter(bar, ev)
    assert tabs.count() == n + 1
