# -*- coding: utf-8 -*-
"""P1 第2步：沙箱菜单规格收集（数据层）"""


class _FakePlugin:
    def __init__(self, items):
        self._items = items

    def menu_items(self):
        return list(self._items)


class _BrokenPlugin:
    def menu_items(self):
        raise RuntimeError("boom")


def test_collect_menu_specs_normalizes_and_sorts():
    from infrastructure.plugin_sandbox_manager import collect_menu_specs
    plugins = {
        "spell": _FakePlugin([
            {"id": "ignore_all", "label": "忽略全部",
             "path": "工具/拼写检查"},
            {"label": "no-id"},
            "bad",
        ]),
        "json": _FakePlugin([
            {"id": "format", "label": "格式化", "path": "工具/JSON"},
        ]),
        "broken": _BrokenPlugin(),
    }
    specs = collect_menu_specs(plugins)
    assert len(specs) == 2
    assert specs[0]["plugin"] == "json"
    assert specs[0]["id"] == "format"
    assert specs[1]["plugin"] == "spell"
    assert specs[1]["path"] == "工具/拼写检查"
    assert all(isinstance(s["label"], str) for s in specs)


def test_collect_menu_specs_empty_and_none():
    from infrastructure.plugin_sandbox_manager import collect_menu_specs
    assert collect_menu_specs({}) == []
    assert collect_menu_specs(None) == []


def test_main_window_has_data_layer():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "ui", "main_window.py"),
               encoding="utf-8").read()
    assert "_sandbox_menu_specs" in src
    assert "collect_menu_specs" in src