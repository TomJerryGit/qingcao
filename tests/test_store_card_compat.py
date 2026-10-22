# -*- coding: utf-8 -*-
"""商店列表行内兼容性徽章（静态契约 + 判定函数）

说明：直接实例化 PluginCard 在 offscreen 平台会触发 Qt 崩溃
（0xC0000409），因此这里验证源码契约与判定函数，避免不稳定的 GUI
实例化；真实卡片行为由与详情页共用的同一判定函数保证。
"""
import ast
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "ui", "plugin_store.py")


def _source():
    return open(STORE, encoding="utf-8").read()


def test_card_source_has_compat_badge_and_disable_logic():
    src = _source()
    tree = ast.parse(src)

    build_uis = []
    update_btns = []
    action_clicks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            seg = ast.get_source_segment(src, node) or ""
            if node.name == "_build_ui" and "title_layout" in seg:
                build_uis.append(seg)
            elif node.name == "_update_action_button":
                update_btns.append(seg)
            elif node.name == "_on_action_clicked":
                action_clicks.append(seg)

    assert build_uis, "未找到 PluginCard._build_ui"
    assert any("compat_label" in s and "check_plugin_compatibility" in s
               and "不兼容" in s for s in build_uis), "标题行缺少徽章"

    assert any("不兼容" in s and "setEnabled(False)" in s
               for s in update_btns), "不兼容时应置灰按钮"

    assert any("_compat_ok" in s for s in action_clicks), "点击应兜底拦截"


def test_compat_judgement_used_by_card():
    from ui.plugin_store import PluginInfo, check_plugin_compatibility

    bad = PluginInfo(name="p", min_app_version="99.0.0")
    ok, reason = check_plugin_compatibility(bad)
    assert ok is False and "需要应用" in reason

    good = PluginInfo(name="p")
    assert check_plugin_compatibility(good)[0] is True
