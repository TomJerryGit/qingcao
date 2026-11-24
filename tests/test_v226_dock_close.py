# -*- coding: utf-8 -*-
"""全局搜索/性能监控 Dock 可关闭"""


def test_install_close_button(qapp):
    from PyQt5.QtWidgets import QDockWidget, QToolButton

    from ui.dock_title import install_close_button

    d = QDockWidget("测试")
    btn = install_close_button(d, "测试")
    assert isinstance(btn, QToolButton)
    assert d.titleBarWidget() is not None
    d.show()
    btn.click()
    assert not d.isVisible()
