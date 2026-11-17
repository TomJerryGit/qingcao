# -*- coding: utf-8 -*-
"""v2.26 阶段 B：AI 自动调试闭环"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_auto_debug_fixes_bug(tmp_path):
    from core.ai_autodebug import auto_debug

    f = tmp_path / "bug.py"
    f.write_text("print(unknown_name)\n", encoding="utf-8")

    def ai(prompt):
        assert "unknown_name" in prompt
        return "```python\nprint('fixed')\n```"

    r = auto_debug(str(f), ai, max_rounds=2)
    assert r["ok"] and r["rounds"] == 1
    assert "fixed" in f.read_text(encoding="utf-8")


def test_auto_debug_rolls_back(tmp_path):
    from core.ai_autodebug import auto_debug

    f = tmp_path / "bad.py"
    f.write_text("print(1/0)\n", encoding="utf-8")

    def ai(prompt):
        return "still broken("

    r = auto_debug(str(f), ai, max_rounds=2)
    assert not r["ok"]
    assert "1/0" in f.read_text(encoding="utf-8")


def test_extract_and_validate():
    from core.ai_autodebug import extract_code, validate_python

    assert extract_code("```python\nx=1\n```") == "x=1"
    assert validate_python("x=1")[0]
    assert not validate_python("def (")[0]
