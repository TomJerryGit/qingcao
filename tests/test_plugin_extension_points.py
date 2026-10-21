# -*- coding: utf-8 -*-
"""插件扩展点（v2.3）：补全提供者 / 诊断发布 / 后台任务

这三个 API 是"插件从挂菜单升级为参与编辑智能"的关键，因此每个都
必须验证**接线真实生效**，而不只是方法返回 True：

* 补全：插件候选真的出现在 `EditorWidget.local_completions()` 结果里，
  且清理（卸载）后消失；
* 诊断：真的进入 `core.problems.ProblemManager`，且只替换**本插件来源**
  的条目（不误删 LSP 等其它来源）；
* 后台任务：`on_done` 真的在主线程执行（Qt 信号桥）。

另外验证权限门控：没有 editor_read 权限时必须抛 PermissionError。
"""
import threading
import time

import pytest


def _api(win, permissions=("editor_read",), name="test_plugin"):
    from app.plugins import PluginAPI
    return PluginAPI(win, permissions=list(permissions), plugin_name=name)


def test_completion_provider_merged_and_unregistered(qapp, tmp_path):
    """插件补全候选项出现在本地补全结果里，卸载后消失"""
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        api = _api(win)
        called = {"n": 0}

        def provider(prefix, language="", filepath=""):
            called["n"] += 1
            return ["plugword"] if prefix == "pl" else []

        assert api.register_completion_provider(
            provider, language_ids=["python"]) is True

        # 语言匹配规则（单元级）：python 命中、js 不命中
        assert "plugword" in win.collect_plugin_completions(
            "pl", language="python", filepath="x.py")
        assert win.collect_plugin_completions(
            "pl", language="javascript", filepath="x.js") == []

        # 用真实 .py 文件打开，让 _completion_language() 能识别 python
        py_file = tmp_path / "x.py"
        py_file.write_text("x = 1\n", encoding="utf-8")
        proxy = win.tabs.open_file(str(py_file))
        editor = proxy.sc
        # 测试环境里本地补全默认关闭/阈值取自用户偏好，这里显式开启
        editor._completion_enabled = True
        editor._completion_min_prefix = 2
        words = editor.local_completions("pl")
        assert "plugword" in words, "插件补全未合并进候选: %r" % (words,)
        assert called["n"] >= 1, "提供者未被调用"

        # 卸载（cleanup）后注销
        api.cleanup()
        assert "plugword" not in editor.local_completions("pl")
    finally:
        win.close()


def test_publish_diagnostics_merges_and_clears(qapp):
    """诊断进入 ProblemManager；clear 只删本插件来源"""
    from core.problems import Problem, get_problem_manager
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        manager = get_problem_manager()
        fp = "C:/qc_test/diag_target.py"
        # 预置一条"别的来源"的诊断，验证不会被本插件清掉
        manager.set_file_problems(fp, [Problem(
            filepath=fp, line=9, col=0, severity="warning",
            message="from LSP", source="lsp")])

        api = _api(win, name="diag_plugin")
        n = api.publish_diagnostics(
            [{"line": 2, "col": 1, "severity": "error",
              "message": "boom", "code": "E001"}],
            filepath=fp,
        )
        assert n == 1
        got = manager.get_for_file(fp)
        mine = [p for p in got if p.source == "diag_plugin"]
        assert len(mine) == 1
        assert mine[0].message == "boom"
        assert mine[0].line == 2
        assert any(p.source == "lsp" for p in got), "误删了其它来源的诊断"

        # 实时校验语义：再次发布 = 覆盖本插件上一批
        api.publish_diagnostics([], filepath=fp)
        got = manager.get_for_file(fp)
        assert not [p for p in got if p.source == "diag_plugin"]
        assert any(p.source == "lsp" for p in got)

        assert api.clear_diagnostics(fp) == 0
        manager.remove_file(fp)
    finally:
        win.close()


def test_run_background_callbacks_on_main_thread(qapp):
    """后台任务在子线程执行，on_done 回到主线程"""
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        api = _api(win, permissions=(), name="bg_plugin")
        got = {}
        main_ident = threading.get_ident()

        def work():
            return 42

        def on_done(result):
            got["value"] = result
            got["thread"] = threading.get_ident()

        api.run_background(work, on_done=on_done, name="unit")
        deadline = time.time() + 5
        while time.time() < deadline and "value" not in got:
            qapp.processEvents()
            time.sleep(0.005)

        assert got.get("value") == 42
        assert got.get("thread") == main_ident, "回调没有回到主线程"

        # 异常路径：on_error 收到异常文本
        err = {}
        api.run_background(lambda: 1 / 0,
                           on_error=lambda msg: err.update(msg=msg),
                           name="unit-err")
        deadline = time.time() + 5
        while time.time() < deadline and "msg" not in err:
            qapp.processEvents()
            time.sleep(0.005)
        assert "division" in err.get("msg", "").lower()
    finally:
        win.close()


def test_extension_points_require_editor_read(qapp):
    """缺少 editor_read 权限时必须拒绝（抛 PermissionError）"""
    from app.plugins import PermissionError as PluginPermissionError
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        api = _api(win, permissions=(), name="no_perm")
        with pytest.raises(PluginPermissionError):
            api.register_completion_provider(lambda *a, **k: [])
        with pytest.raises(PluginPermissionError):
            api.publish_diagnostics([])
        with pytest.raises(PluginPermissionError):
            api.clear_diagnostics()
    finally:
        win.close()


def test_hover_provider_collected_and_filtered(qapp):
    """hover：语言过滤 + 清理后不再返回"""
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        api = _api(win, name="hover_plugin")
        assert api.register_hover_provider(
            lambda line, col, filepath="", language="":
                "行 %d 的提示" % line,
            language_ids=["python"],
        ) is True
        assert "行 3" in win.collect_plugin_hover(
            "x.py", 3, 0, language="python")
        assert win.collect_plugin_hover(
            "x.js", 3, 0, language="javascript") == ""
        api.cleanup()
        assert win.collect_plugin_hover(
            "x.py", 3, 0, language="python") == ""
    finally:
        win.close()


def test_context_menu_code_action_and_status_item(qapp):
    """右键菜单项 / 代码操作 / 状态栏项 的注册与清理"""
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        api = _api(win, permissions=("editor_read", "editor_write", "dialog"),
                   name="ui_plugin")
        fired = {"ctx": 0, "code": 0}
        assert api.add_editor_context_menu(
            "插件动作", lambda: fired.__setitem__("ctx", 1)) is True
        assert len(win.collect_editor_context_actions()) == 1

        assert api.register_code_action_provider(
            lambda line, col, filepath="", language="": [{
                "title": "修复它", "kind": "quickfix",
                "callback": lambda: fired.__setitem__("code", 1),
            }], language_ids=["python"]) is True
        actions = win.collect_code_actions(
            "x.py", 1, 0, language="python")
        assert len(actions) == 1 and actions[0]["title"] == "修复它"
        actions[0]["callback"]()
        assert fired["code"] == 1

        item = api.add_status_item("插件状态")
        assert item is not None
        api.cleanup()
        assert win.collect_editor_context_actions() == []
        assert win.collect_code_actions("x.py", 1, 0, language="python") == []
    finally:
        win.close()


def test_decoration_and_settings_schema(qapp, tmp_path):
    """装饰应用 / 设置 schema 注册与默认值"""
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        api = _api(win, permissions=("editor_read", "editor_write", "dialog"),
                   name="deco_plugin")
        py_file = tmp_path / "d.py"
        py_file.write_text("a = 1\nb = 2\n", encoding="utf-8")
        win.tabs.open_file(str(py_file))
        assert api.add_decoration(0, 1, "#FF0000") is True

        assert api.register_settings_schema([
            {"key": "timeout", "label": "超时", "type": "int",
             "default": 30, "min": 1, "max": 600},
            {"key": "enabled", "label": "启用", "type": "bool",
             "default": True},
        ]) is True
        assert api.get_config("timeout", None) == 30
        assert api.get_config("enabled", None) is True
        api.cleanup()
    finally:
        win.close()
