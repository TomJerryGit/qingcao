# -*- coding: utf-8 -*-
"""真实插件迁移验证：json_formatter 使用 v2.3/v2.4 扩展点

这是"API 不是摆设"的证据：真实插件（不是测试桩）注册 hover、代码操作、
右键菜单、设置 schema，并真的把 JSON 语法错误发布到问题面板。
"""
import importlib.util
import os

import pytest


def _load_plugin():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "plugins", "json_formatter", "__init__.py")
    spec = importlib.util.spec_from_file_location(
        "qc_test_json_formatter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Plugin()


def _make_api(win):
    from app.plugins import PluginAPI
    return PluginAPI(
        win,
        permissions=["editor_read", "editor_write"],
        plugin_name="json_formatter",
    )


def test_json_formatter_uses_extension_points(qapp, tmp_path):
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        api = _make_api(win)
        plugin = _load_plugin()
        plugin.api = api
        plugin.on_activate()

        # ---- 注册检查 ----
        assert any(e.get("plugin") == "json_formatter"
                   for e in win._plugin_hover_providers), "hover 未注册"
        assert any(e.get("plugin") == "json_formatter"
                   for e in win._plugin_code_action_providers), \
            "代码操作未注册"
        assert any(e.get("plugin") == "json_formatter"
                   for e in win.collect_editor_context_actions()), \
            "右键菜单项未注册"
        assert "json_formatter" in win._plugin_settings_schemas, \
            "设置 schema 未注册"
        assert api.get_config("indent", None) == 2, "设置默认值未写入"

        # ---- 合法 JSON：hover + 代码操作 ----
        good = tmp_path / "good.json"
        good.write_text('{"a": 1, "b": [1, 2]}', encoding="utf-8")
        win.tabs.open_file(str(good))

        hover = win.collect_plugin_hover(
            str(good), 0, 0, language="json")
        assert "JSON" in hover, "hover 文本为空: %r" % (hover,)

        titles = [a["title"] for a in win.collect_code_actions(
            str(good), 0, 0, language="json")]
        assert any("格式化" in t for t in titles), \
            "代码操作缺少格式化: %r" % (titles,)
        assert any("压缩" in t for t in titles)

        # ---- 非法 JSON：语法错误发布到问题面板 ----
        bad = tmp_path / "bad.json"
        bad.write_text('{"a": }', encoding="utf-8")
        win.tabs.open_file(str(bad))
        n = plugin.check_and_report()
        assert n == 1, "诊断未发布"

        from core.problems import get_problem_manager
        manager = get_problem_manager()
        mine = [p for p in manager.all_problems()
                if p.source == "json_formatter"]
        assert mine and mine[0].severity == "error"

        # ---- 卸载清理 ----
        # 真实卸载路径是 PluginLoader: on_deactivate() → api.cleanup()；
        # 这里两步都调，验证扩展点被注销/清理。
        plugin.on_deactivate()
        api.cleanup()
        assert win.collect_plugin_hover(
            str(good), 0, 0, language="json") == "", "hover 未清理"
        assert not any(e.get("plugin") == "json_formatter"
                       for e in win._plugin_hover_providers)
        mine = [p for p in get_problem_manager().all_problems()
                if p.source == "json_formatter"]
        assert not mine, "卸载后诊断未清理"
    finally:
        _close_without_session(win)


def _close_without_session(win):
    """关闭测试窗口但**不写会话文件**

    实测污染：MainWindow.closeEvent 会保存会话；测试批量创建/关闭窗口会
    把"无可见面板/无标签"的状态写进真实用户会话文件，导致后续测试
    （如 test_p1_features::test_default_panels_visible）恢复出空面板布局。
    """
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()
