# -*- coding: utf-8 -*-
"""浅色主题下面板子控件黑块修复测试（adapt_widget_styles）"""
from PyQt5.QtWidgets import QApplication, QTreeWidget, QWidget


def test_adapt_widget_styles_rewrites_child_inline_qss(monkeypatch):
    app = QApplication.instance() or QApplication([])
    import ui.main_window as mw

    calls = []

    def fake_adapt(qss, theme):
        calls.append(qss)
        return "QTreeWidget { background-color: #ffffff; color: #000000; }"

    monkeypatch.setattr(
        "infrastructure.theme_loader.adapt_qss_colors", fake_adapt)

    root = QWidget()
    child = QTreeWidget(root)
    child.setStyleSheet("QTreeWidget { background-color: #1e1e1e; }")
    theme = object()

    n = mw.adapt_widget_styles(root, theme)
    assert n >= 1
    assert "background-color: #ffffff" in child.styleSheet()
    # 幂等：第二次仍从原始值适配，不叠加
    mw.adapt_widget_styles(root, theme)
    assert "background-color: #ffffff" in child.styleSheet()
    assert len([c for c in calls if "#1e1e1e" in c]) >= 2
    root.deleteLater()
    app.processEvents()
