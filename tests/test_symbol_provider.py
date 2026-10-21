# -*- coding: utf-8 -*-
"""插件 symbol provider → 大纲面板（NPP functionList 等价）测试"""
import os

import pytest


def _api(win, name="sym_plugin"):
    from app.plugins import PluginAPI
    return PluginAPI(win, permissions=["editor_read"],
                     plugin_name=name)


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def _provider(text, filepath="", language=""):
    return [
        {"name": "PlugFunc", "type": "function", "line": 1,
         "signature": "(x)", "children": [
             {"name": "inner", "type": "variable", "line": 2},
         ]},
    ]


def test_collect_plugin_symbols_normalizes(qapp):
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        api = _api(win)
        assert api.register_symbol_provider(
            _provider, language_ids=["mylang", ".mylang"]) is True

        items = win.collect_plugin_symbols(
            "abc", filepath="a.mylang", language="mylang")
        assert len(items) == 1
        assert items[0]["name"] == "PlugFunc"
        assert items[0]["signature"] == "(x)"
        assert items[0]["children"][0]["name"] == "inner"

        # 语言不匹配 → 不收集
        assert win.collect_plugin_symbols(
            "abc", filepath="a.other", language="other") == []
        api.cleanup()
    finally:
        _close(win)


def test_outline_merges_plugin_symbols(qapp, tmp_path):
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        assert win._ensure_panel("outline") is True
        panel = win.outline
        api = _api(win)
        api.register_symbol_provider(
            _provider, language_ids=["mylang", ".mylang"])

        f = tmp_path / "demo.mylang"
        f.write_text("// hello\nPlugFunc(x)\n", encoding="utf-8")
        win.tabs.open_file(str(f))
        panel._do_update()

        names = [s.name for s in panel._current_symbols]
        assert "PlugFunc" in names, "插件符号未进入大纲: %r" % (names,)

        api.cleanup()
        panel._do_update()
        names = [s.name for s in panel._current_symbols]
        assert "PlugFunc" not in names
    finally:
        _close(win)


def test_capabilities_include_symbol_provider(qapp):
    from app.plugins import PluginAPI

    api = PluginAPI(None, permissions=["editor_read"], plugin_name="cap")
    caps = api.get_api_capabilities()
    assert caps["extension_points"]["symbol_provider"] is True
