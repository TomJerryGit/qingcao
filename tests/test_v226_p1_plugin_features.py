# -*- coding: utf-8 -*-
"""v2.26 P1：JSONL / 日志高亮 / Markdown 目录"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _API:
    def __init__(self, text):
        self.text = text
        self.replaced = None
        self.status = []

    def get_selected_text(self):
        return self.text

    def get_current_text(self):
        return self.text

    def replace_selected_text(self, text):
        self.replaced = text

    def set_editor_text(self, text):
        self.replaced = text

    def get_config(self, *a, **k):
        return None

    def log(self, *a, **k):
        pass

    def show_status(self, *a, **k):
        self.status.append(a)

    def show_message(self, *a, **k):
        pass


def test_jsonl_formatting():
    from plugins.json_formatter import Plugin

    api = _API('{"b": 2}\n{"a": 1}')
    plugin = Plugin()
    plugin.api = api
    plugin.format_jsonl()
    assert api.replaced == '{"b":2}\n{"a":1}'


def test_logtail_find_matches():
    from plugins.logtail import find_matches

    assert find_matches("a1 b2 a3", r"a\d") == [(0, 2), (6, 8)]
    assert find_matches("abc", "") == []


def test_markdown_extract_headings():
    from plugins.markdown_preview import extract_headings

    text = "# A\n\n## B\ntext\n### C"
    assert extract_headings(text) == [(1, "A", 1), (2, "B", 3), (3, "C", 5)]
