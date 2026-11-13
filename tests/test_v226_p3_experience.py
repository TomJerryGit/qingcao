# -*- coding: utf-8 -*-
"""v2.26 P3：JSONC/Schema、wordcount CJK/选区、logtail 过滤"""

import json


def test_jsonc_strip_comments_and_trailing_commas():
    from plugins.json_formatter import Plugin

    src = """{
      // comment
      "a": 1, /* block */
      "b": [1, 2,],
    }"""
    cleaned = Plugin.strip_jsonc(src)
    data = json.loads(cleaned)
    assert data == {"a": 1, "b": [1, 2]}


def test_json_schema_basic_error():
    from plugins.json_formatter import Plugin

    plugin = Plugin.__new__(Plugin)
    schema = {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}
    assert plugin._schema_error({"name": 1}, schema, "$")
    assert plugin._schema_error({"name": "x"}, schema, "$") == ""


def test_wordcount_cjk_and_stats():
    from plugins.wordcount import count_text_stats

    stats = count_text_stats("你好 world\n第二行")
    assert stats["chars"] == len("你好 world\n第二行")
    assert stats["words"] == 6  # 5 个 CJK 字 + 1 个英文词
    assert stats["lines"] == 2
    assert stats["reading_time"] >= 1


def test_logtail_filter_lines():
    from plugins.logtail import filter_lines

    text = "INFO ok\nERROR bad\nWARN slow"
    assert filter_lines(text, "ERROR") == "ERROR bad"
    assert filter_lines(text, "NOPE") == ""
    assert filter_lines(text, "") == text


def test_logtail_has_multifile_and_pause_ui():
    src = open("plugins/logtail/__init__.py", encoding="utf-8").read()
    for text in ("file_combo", "pause_btn", "filter_edit", "监视文件"):
        assert text in src
