# -*- coding: utf-8 -*-
"""v2.19 P1-2 长尾：控件树翻译 / 偏好页 / 覆盖率"""

import io
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_tr_label(monkeypatch):
    monkeypatch.setenv("QINGCAO_LANG", "en_US")
    from core.i18n_json import clear_cache

    clear_cache()
    from ui.i18n_widgets import tr_label

    assert tr_label("显示行号：") == "Show Line Numbers："
    assert tr_label("取消") == "Cancel"
    assert tr_label("不存在的字符串") == "不存在的字符串"


def test_translate_widgets(qapp, monkeypatch):
    monkeypatch.setenv("QINGCAO_LANG", "en_US")
    from core.i18n_json import clear_cache

    clear_cache()
    from PyQt5.QtWidgets import (
        QCheckBox,
        QGroupBox,
        QLabel,
        QLineEdit,
        QVBoxLayout,
        QWidget,
    )

    from ui.i18n_widgets import translate_widgets

    root = QWidget()
    layout = QVBoxLayout(root)
    group = QGroupBox("缩进")
    QVBoxLayout(group).addWidget(QCheckBox("自动换行", group))
    layout.addWidget(group)
    layout.addWidget(QLabel("显示行号", root))
    edit = QLineEdit(root)
    edit.setPlaceholderText("搜索插件")
    layout.addWidget(edit)
    n = translate_widgets(root)
    assert n >= 4, n
    assert group.title() == "Indentation"
    assert root.findChild(QCheckBox).text() == "Word Wrap"
    assert root.findChild(QLabel).text() == "Show Line Numbers"
    assert edit.placeholderText() == "Search Plugins"
    root.close()


def test_preferences_dialog_english(qapp, monkeypatch):
    monkeypatch.setenv("QINGCAO_LANG", "en_US")
    from core.i18n_json import clear_cache

    clear_cache()
    from PyQt5.QtWidgets import QGroupBox, QPushButton

    from ui.preferences_panel import PreferencesDialog

    dlg = PreferencesDialog()
    try:
        assert dlg.windowTitle() == "Preferences"
        titles = {g.title() for g in dlg.findChildren(QGroupBox)}
        assert "Indentation" in titles, titles
        buttons = {b.text() for b in dlg.findChildren(QPushButton)}
        assert "OK" in buttons and "Cancel" in buttons, buttons
        cats = [dlg.category_list.item(i).text() for i in range(dlg.category_list.count())]
        assert any("General" in c for c in cats), cats
    finally:
        dlg.close()


def test_coverage_tool_and_report(monkeypatch, tmp_path):
    monkeypatch.setenv("QINGCAO_LANG", "en_US")
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "qc_i18n_cov", os.path.join(ROOT, "tools", "i18n_coverage.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from core.i18n_json import clear_cache

    clear_cache()
    out = tmp_path / "cov.md"
    import sys

    old_argv = sys.argv
    sys.argv = ["i18n_coverage.py", "--out", str(out)]
    try:
        assert mod.main() == 0
    finally:
        sys.argv = old_argv
    text = out.read_text(encoding="utf-8")
    assert "重点 UI 覆盖率" in text
    assert os.path.isfile(os.path.join(ROOT, "docs", "i18n_coverage_report.md"))
