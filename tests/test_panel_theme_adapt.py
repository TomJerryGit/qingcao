# -*- coding: utf-8 -*-
"""浅色主题下面板子控件黑块修复测试（adapt_widget_styles）"""
from types import SimpleNamespace

from PyQt5.QtWidgets import QApplication, QTreeWidget, QWidget


def test_adapt_widget_styles_rewrites_child_inline_qss(monkeypatch):
    app = QApplication.instance() or QApplication([])
    import ui.main_window as mw

    def fake_adapt(qss, theme):
        color = "#ffffff" if getattr(theme, "name", "") == "light" else "#000000"
        return "QTreeWidget { background-color: %s; }" % color

    monkeypatch.setattr(
        "infrastructure.theme_loader.adapt_qss_colors", fake_adapt)

    root = QWidget()
    child = QTreeWidget(root)
    child.setStyleSheet("QTreeWidget { background-color: #1e1e1e; }")

    light = SimpleNamespace(name="light")
    n = mw.adapt_widget_styles(root, light)
    assert n >= 1
    assert "background-color: #ffffff" in child.styleSheet()

    # 同主题重复调用：缓存短路，不再遍历/改写
    n2 = mw.adapt_widget_styles(root, light)
    assert n2 == 0
    assert "background-color: #ffffff" in child.styleSheet()

    # 切换主题：从原始深色 QSS 重新适配（不会叠加失真）
    dark = SimpleNamespace(name="dark")
    n3 = mw.adapt_widget_styles(root, dark)
    assert n3 >= 1
    assert "background-color: #000000" in child.styleSheet()
    root.deleteLater()
    app.processEvents()