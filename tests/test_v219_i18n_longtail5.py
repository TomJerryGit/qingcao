# -*- coding: utf-8 -*-
"""v2.19 长尾 5：剩余提示/错误消息"""

import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_error_prefixes(monkeypatch):
    monkeypatch.setenv("QINGCAO_LANG", "en_US")
    from core.i18n_json import clear_cache

    clear_cache()
    from ui.i18n_widgets import translate_text

    assert translate_text("切换语言失败: 缺少语言包") == "Language Switch Failed: 缺少语言包"
    assert translate_text("主题已切换: dark_night") == "Theme switched: dark_night"
    assert translate_text("定义位于: a.py:10") == "Definition at: a.py:10"
    assert translate_text("保存错误") == "保存错误"  # 未命中回退


def test_static_hints(monkeypatch):
    monkeypatch.setenv("QINGCAO_LANG", "en_US")
    from core.i18n_json import clear_cache, tr

    clear_cache()
    assert tr("重新打开上次的文件") == "Reopen Last File"
    assert tr("排除的目录，用分号分隔") == ("Excluded directories, separated by semicolons")
    assert tr("留空使用默认（jsDelivr CDN）") == ("Leave empty to use default (jsDelivr CDN)")


def test_dictionary_batch5():
    en = json.load(open(os.path.join(ROOT, "locale", "en_US", "strings.json"), encoding="utf-8"))
    assert len(en) >= 640, len(en)
    for k in ("切换语言失败", "重新打开上次的文件", "插件未声明配置"):
        assert k in en
