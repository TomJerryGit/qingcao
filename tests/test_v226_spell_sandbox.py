# -*- coding: utf-8 -*-
"""v2.26：spell_check 标准沙箱契约（manifest + worker 方法）"""

import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_spell_check_is_standard_sandbox():
    from infrastructure.plugin_sandbox_manager import is_sandbox_enabled

    plugin_dir = os.path.join(ROOT, "plugins", "spell_check")
    assert is_sandbox_enabled(plugin_dir)
    worker = open(
        os.path.join(ROOT, "infrastructure", "plugin_sandbox_worker.py"), encoding="utf-8"
    ).read()
    for method in ("diagnostics", "add_ignore_word", "menu_items", "invoke_menu"):
        assert method in worker
