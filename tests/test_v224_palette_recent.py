# -*- coding: utf-8 -*-
"""v2.24.x UX：命令面板最近使用排序 + 持久化"""


def test_sort_by_usage_uses_action_key(qapp):
    import time

    from ui.command_palette import BasePalette, PaletteItem, PaletteMode

    p = BasePalette(None, PaletteMode.COMMAND)
    try:
        a = PaletteItem(title="A", action_name="a")
        b = PaletteItem(title="B", action_name="b")
        p.set_items([a, b])
        now = time.time()
        # 历史 key 使用 action: 前缀
        p.set_usage_history({"action:b": (now, 3)})
        ordered = p._sort_by_usage(p.items)
        assert ordered[0].action_name == "b"
    finally:
        p.close()


def test_usage_history_persisted_roundtrip(qapp):
    from ui.command_palette import BasePalette, PaletteMode

    p = BasePalette(None, PaletteMode.COMMAND)
    try:
        p.set_usage_history({"action:x": (123.0, 2)})
        p._save_persisted_usage()
        loaded = p._load_persisted_usage()
        assert loaded.get("action:x") == (123.0, 2)
    finally:
        p.close()
