# -*- coding: utf-8 -*-
"""内置插件迁移验证：markdown_preview（诊断+设置）/ todo_panel（设置+状态栏）

与 `test_json_formatter_plugin.py` 同一思路：加载**真实插件模块**，
验证扩展点的注册、行为、清理，而不是只测 API 本身。
"""
import importlib.util
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_plugin(name):
    path = os.path.join(ROOT, "plugins", name, "__init__.py")
    spec = importlib.util.spec_from_file_location("qc_test_%s" % name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Plugin()


def _api(win, perms, name):
    from app.plugins import PluginAPI
    return PluginAPI(win, permissions=list(perms), plugin_name=name)


def _close(win):
    """关闭窗口但不写会话文件（避免污染真实用户会话）"""
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def test_markdown_preview_diagnostics_and_settings(qapp, tmp_path):
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        api = _api(win, ["editor_read", "dialog"], "markdown_preview")
        plugin = _load_plugin("markdown_preview")
        plugin.api = api
        plugin.on_activate()

        assert "markdown_preview" in win._plugin_settings_schemas
        assert api.get_config("check_image_alt", None) is True

        md = tmp_path / "bad.md"
        md.write_text(
            "# 标题\n\n![](x.png)\n\n```python\nprint(1)\n",
            encoding="utf-8",
        )
        win.tabs.open_file(str(md))
        n = plugin.check_and_report()
        assert n >= 2, "应同时报告空 alt 与未闭合围栏，实际 %d" % n

        from core.problems import get_problem_manager
        manager = get_problem_manager()
        mine = [p for p in manager.get_for_file(str(md))
                if p.source == "markdown_preview"]
        codes = {p.code for p in mine}
        assert "MD001" in codes, "缺少图片 alt 诊断: %r" % (codes,)
        assert "MD002" in codes, "缺少代码围栏诊断: %r" % (codes,)

        plugin.on_deactivate()
        api.cleanup()
        mine = [p for p in manager.get_for_file(str(md))
                if p.source == "markdown_preview"]
        assert not mine, "卸载后诊断未清理"
    finally:
        _close(win)


def test_todo_panel_settings_and_status_item(qapp):
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        api = _api(win, ["filesystem", "editor_read", "dialog"], "todo_panel")
        plugin = _load_plugin("todo_panel")
        plugin.api = api
        plugin.on_activate()

        assert "todo_panel" in win._plugin_settings_schemas
        assert api.get_config("max_items", None) == 200

        label = getattr(plugin, "_status_label", None)
        assert label is not None, "状态栏项未创建"
        assert "TODO" in label.text()

        plugin.on_deactivate()
        api.cleanup()
    finally:
        _close(win)
