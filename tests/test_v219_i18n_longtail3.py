# -*- coding: utf-8 -*-
"""v2.19 长尾 3：欢迎页技巧 / 市场 HTML / 面板状态"""

import io
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from ui_source_utils import read_market_source


def _en(monkeypatch):
    monkeypatch.setenv("QINGCAO_LANG", "en_US")
    from core.i18n_json import clear_cache

    clear_cache()


def test_translate_html(monkeypatch):
    _en(monkeypatch)
    from ui.i18n_widgets import translate_html

    html = "<h3>权限要求</h3><ul><li>版本: 1.0</li><li>最低版本: 2.0</li><li>更新日志: x</li></ul>"
    out = translate_html(html)
    assert "Permissions" in out
    assert "Version: 1.0" in out
    assert "Minimum Version: 2.0" in out
    assert "Changelog" in out
    assert "<h3>" in out and "</ul>" in out


def test_daily_tips_translated(monkeypatch):
    _en(monkeypatch)
    from core.i18n_json import tr
    from ui.tips import TIPS

    assert tr(TIPS[0]).startswith("Press Ctrl+Shift+P")
    assert sum(1 for t in TIPS if tr(t) != t) >= len(TIPS) - 1


def test_panel_labels(monkeypatch, qapp):
    _en(monkeypatch)
    from PyQt5.QtWidgets import QLabel

    from ui.i18n_widgets import translate_widgets

    label = QLabel("无匹配")
    n = translate_widgets(label)
    assert n >= 1
    assert label.text() == "No matches"
    label.close()


def test_market_html_wiring_static():
    src = read_market_source()
    assert "translate_html" in src
    welcome = io.open(os.path.join(ROOT, "ui", "welcome_widget.py"), encoding="utf-8").read()
    assert "_tr(self._current_tip)" in welcome


def test_dictionary_batch3():
    en = json.load(io.open(os.path.join(ROOT, "locale", "en_US", "strings.json"), encoding="utf-8"))
    assert len(en) >= 450, len(en)
    for k in ("无匹配", "权限要求", "全部来源", "最低版本"):
        assert k in en
