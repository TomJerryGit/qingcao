# -*- coding: utf-8 -*-
"""商店兼容性徽章 + 全部更新按钮 + 门控测试（P1）"""
import ast
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "ui", "plugin_store.py")


def _new_info(**kw):
    from ui.plugin_store import PluginInfo
    data = dict(name="p", display_name="P", version="1.0.0")
    data.update(kw)
    return PluginInfo(**data)


def test_check_plugin_compatibility_helper():
    from ui.plugin_store import check_plugin_compatibility

    assert check_plugin_compatibility(_new_info(), "2.2.0")[0] is True
    ok, reason = check_plugin_compatibility(
        _new_info(min_app_version="2.0.0"), "0.9.0")
    assert ok is False and "需要应用" in reason
    ok, reason = check_plugin_compatibility(
        _new_info(min_app_version="2.0.0", max_app_version="2.1.0"), "2.2.0")
    assert ok is False and "仅支持" in reason


def test_install_update_paths_are_gated_and_button_exists():
    src = open(STORE, encoding="utf-8").read()
    tree = ast.parse(src)
    fns = [n for n in ast.walk(tree)
           if isinstance(n, ast.FunctionDef)
           and n.name in ("_on_install", "_on_update", "_update_all")]
    assert len(fns) == 3
    for fn in fns:
        text = ast.get_source_segment(src, fn) or ""
        assert "check_plugin_compatibility" in text, fn.name
    assert "update_all_btn" in src, "缺少全部更新按钮"
    assert '"⬆ 全部更新"' in src.replace("\u2b06", "⬆") or "全部更新" in src
    assert "✅ 兼容当前版本" in src
