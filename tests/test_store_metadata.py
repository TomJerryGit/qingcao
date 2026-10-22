# -*- coding: utf-8 -*-
"""商店元数据展示：update_url / changelog（P1 尾巴）"""
import ast
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(ROOT, "ui", "plugin_store.py")


def test_plugin_info_has_changelog_and_update_url():
    from ui.plugin_store import PluginInfo

    info = PluginInfo(name="p", changelog="修复了 X",
                      update_url="https://example.com/upd.json")
    assert info.changelog == "修复了 X"
    assert info.update_url.startswith("https://")


def test_detail_html_shows_update_metadata():
    src = open(STORE, encoding="utf-8").read()
    tree = ast.parse(src)
    # 找到构建详情 HTML 的方法（含技术信息片段）
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            seg = ast.get_source_segment(src, node) or ""
            if "技术信息" in seg:
                assert "更新地址" in seg, "详情页缺少更新地址"
                assert "更新日志" in seg, "详情页缺少更新日志"
                assert "changelog" in seg
                found = True
                break
    assert found, "未找到详情 HTML 构建方法"
