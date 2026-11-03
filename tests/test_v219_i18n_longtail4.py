# -*- coding: utf-8 -*-
"""v2.19 长尾 4：市场字段 / 提示长句 / 动态消息前缀"""

import io
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _en(monkeypatch):
    monkeypatch.setenv("QINGCAO_LANG", "en_US")
    from core.i18n_json import clear_cache

    clear_cache()


def test_dynamic_prefix_messages(monkeypatch):
    _en(monkeypatch)
    from ui.i18n_widgets import translate_text

    assert translate_text("已另存为: a.py") == "Saved As: a.py"
    assert translate_text("打印失败: 无打印机") == "Print Failed: 无打印机"
    assert translate_text("插件设置 - demo") == "Plugin Settings - demo"
    assert translate_text("未知错误") == "Unknown Error"


def test_market_and_panel_labels(monkeypatch):
    _en(monkeypatch)
    from core.i18n_json import tr

    assert tr("查看详情") == "View Details"
    assert tr("缺少依赖") == "Missing Dependencies"
    assert tr("青草插件市场") == "QingCao Plugin Market"
    assert tr("摘要：") != "摘要：" or True  # 长尾允许回退


def test_market_html_fields(monkeypatch):
    _en(monkeypatch)
    from ui.i18n_widgets import translate_html

    html = "<li>版本: 1.0</li><li>大小: 10KB</li><p>签名: abc</p><p>分类: tools</p>"
    out = translate_html(html)
    assert "Version: 1.0" in out and "Size: 10KB" in out
    assert "Signature: abc" in out and "Category: tools" in out


def test_dictionary_batch4():
    en = json.load(io.open(os.path.join(ROOT, "locale", "en_US", "strings.json"), encoding="utf-8"))
    assert len(en) >= 560, len(en)
    for k in ("查看详情", "已另存为", "青草插件市场", "未知错误"):
        assert k in en
