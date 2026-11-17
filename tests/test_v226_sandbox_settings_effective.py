# -*- coding: utf-8 -*-
"""v2.26 P1：沙箱设置实际生效"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_whitespace_config_affects_diagnostics():
    from plugins.whitespace_sandbox import Plugin

    p = Plugin()
    p.on_config({"max_line_length": 5})
    items = p.diagnostics("123456789")
    assert any(i["code"] == "long-line" and i["col"] == 5 for i in items)


def test_wordcount_config_affects_mode():
    from plugins.wordcount_sandbox import Plugin

    p = Plugin()
    p.on_config({"count_mode": "words", "max_chars": 4})
    text = p.status_text("a b c d e")
    assert "词数:" in text and "字符:" not in text


def test_sandbox_demo_message_config():
    from plugins.sandbox_demo import Plugin

    p = Plugin()
    p.on_config({"message": "hello"})
    assert p.status_text() == "hello"
