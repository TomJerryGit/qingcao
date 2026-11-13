# -*- coding: utf-8 -*-
"""v2.26 P2：AI diff 预览"""

import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_build_diff_contains_changes():
    try:
        from plugins.ai_assistant.ai_result_dialog import AIResultDialog
    except Exception:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "ai_result_dialog", os.path.join(ROOT, "plugins", "ai_assistant", "ai_result_dialog.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        AIResultDialog = mod.AIResultDialog
    diff = AIResultDialog._build_diff("a = 1\n", "a = 2\n")
    assert "---" in diff and "+++" in diff
    assert "-a = 1" in diff and "+a = 2" in diff
    assert AIResultDialog._build_diff("x", "x") == ""


def test_diff_button_present_static():
    src = open(
        os.path.join(ROOT, "plugins", "ai_assistant", "ai_result_dialog.py"), encoding="utf-8"
    ).read()
    assert "预览差异" in src and "_on_diff_preview" in src
