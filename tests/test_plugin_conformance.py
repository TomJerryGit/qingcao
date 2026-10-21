# -*- coding: utf-8 -*-
"""插件 conformance 测试骨架（v2.3/v2.4 扩展点契约 + 插件清单契约）

## 为什么需要

扩展点 API 已经交付，但"某个插件声称支持"和"宿主真的按契约工作"之间
没有自动化保障。这个文件是**骨架**，两层契约：

1. **扩展点契约**（`EXTENSION_CONTRACTS`）：每个 API 验证
   `注册 → 生效 → 卸载清理` 三件事；
2. **插件清单契约**（manifest）：扫描 `plugins/*/plugin.json`，
   验证必填字段、权限合法、`api_version` 可解析、入口模块存在
   `Plugin` 类且实现 `on_activate/on_deactivate`。

维护方式：
* 新增扩展点 → 在 `EXTENSION_CONTRACTS` 加一条 `@contract("名字")`；
* 新增插件 → 自动进入清单契约，无需改测试。

运行：
    python -m pytest tests/test_plugin_conformance.py -q
    # 插件清单单项失败会指出插件名，方便插件作者排查
"""
import ast
import json
import os

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.path.join(ROOT, "plugins")
ALL_PERMS = ["editor_read", "editor_write", "dialog"]

_EXTENSION_CONTRACTS = {}


def contract(name):
    """注册一条扩展点契约"""

    def deco(fn):
        _EXTENSION_CONTRACTS[name] = fn
        return fn

    return deco


def _api(win, perms=None, name="conformance"):
    from app.plugins import PluginAPI
    return PluginAPI(win, permissions=list(perms or ALL_PERMS),
                     plugin_name=name)


def _close(win):
    """关闭窗口但不写会话文件（避免污染真实用户会话，见测试经验）"""
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


# ============================================================
# 1. 扩展点契约
# ============================================================
@contract("completion")
def _c_completion(api, win, tmp_path):
    api.register_completion_provider(
        lambda prefix, language="", filepath="":
            ["conf_word"] if prefix == "co" else [])
    assert "conf_word" in win.collect_plugin_completions(
        "co", language="python", filepath="x.py")
    api.cleanup()
    assert win.collect_plugin_completions(
        "co", language="python", filepath="x.py") == []


@contract("diagnostics")
def _c_diagnostics(api, win, tmp_path):
    from core.problems import get_problem_manager
    fp = str(tmp_path / "conf.py")
    n = api.publish_diagnostics(
        [{"line": 0, "col": 0, "severity": "error", "message": "conf"}],
        filepath=fp)
    assert n == 1
    assert any(p.source == "conformance"
               for p in get_problem_manager().get_for_file(fp))
    api.cleanup()
    assert not any(p.source == "conformance"
                   for p in get_problem_manager().get_for_file(fp))


@contract("background")
def _c_background(api, win, tmp_path):
    import time
    got = {}
    api.run_background(lambda: 7,
                       on_done=lambda r: got.update(value=r),
                       name="conformance")
    deadline = time.time() + 5
    while time.time() < deadline and "value" not in got:
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()
        time.sleep(0.005)
    assert got.get("value") == 7


@contract("hover")
def _c_hover(api, win, tmp_path):
    api.register_hover_provider(
        lambda line, col, filepath="", language="": "conf-hover")
    assert "conf-hover" in win.collect_plugin_hover(
        "x.py", 0, 0, language="python")
    api.cleanup()
    assert win.collect_plugin_hover("x.py", 0, 0, language="python") == ""


@contract("code-action")
def _c_code_action(api, win, tmp_path):
    called = {"n": 0}
    api.register_code_action_provider(
        lambda line, col, filepath="", language="": [{
            "title": "conf-fix", "kind": "quickfix",
            "callback": lambda: called.__setitem__("n", 1)}])
    actions = win.collect_code_actions("x.py", 0, 0, language="python")
    assert [a["title"] for a in actions] == ["conf-fix"]
    actions[0]["callback"]()
    assert called["n"] == 1


@contract("editor-context-menu")
def _c_context_menu(api, win, tmp_path):
    api.add_editor_context_menu("conf-action", lambda: None)
    assert any(e.get("label") == "conf-action"
               for e in win.collect_editor_context_actions())
    api.cleanup()
    assert win.collect_editor_context_actions() == []


@contract("status-item")
def _c_status_item(api, win, tmp_path):
    item = api.add_status_item("conf-status")
    assert item is not None
    api.cleanup()


@contract("decoration")
def _c_decoration(api, win, tmp_path):
    f = tmp_path / "conf_deco.py"
    f.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    win.tabs.open_file(str(f))
    assert api.add_decoration(0, 2, "#FF0000") is True


@contract("settings-schema")
def _c_settings_schema(api, win, tmp_path):
    assert api.register_settings_schema([
        {"key": "conf_int", "label": "整数", "type": "int",
         "default": 5, "min": 0, "max": 9},
    ]) is True
    assert api.get_config("conf_int", None) == 5
    assert "conformance" in win._plugin_settings_schemas


def test_extension_contracts(qapp, tmp_path):
    """所有扩展点契约：注册 → 生效 → 卸载清理"""
    from ui.main_window import MainWindow

    assert _EXTENSION_CONTRACTS, "没有任何扩展点契约"
    win = MainWindow()
    try:
        failures = []
        for name, check in sorted(_EXTENSION_CONTRACTS.items()):
            api = _api(win)
            try:
                check(api, win, tmp_path)
            except AssertionError as e:
                failures.append("%s: %s" % (name, e))
            except Exception as e:
                failures.append("%s: 异常 %r" % (name, e))
            finally:
                try:
                    api.cleanup()
                except Exception:
                    pass
        assert not failures, "扩展点契约失败:\n" + "\n".join(failures)
    finally:
        _close(win)


# ============================================================
# 2. 插件清单契约（自动扫描所有插件）
# ============================================================
def _plugin_dirs():
    if not os.path.isdir(PLUGIN_DIR):
        return []
    out = []
    for name in sorted(os.listdir(PLUGIN_DIR)):
        path = os.path.join(PLUGIN_DIR, name)
        if os.path.isdir(path) and os.path.isfile(
                os.path.join(path, "plugin.json")):
            out.append((name, path))
    return out


def test_plugin_manifest_conformance():
    """每个插件的 manifest 与入口模块都符合契约"""
    from app.plugins import ALL_PERMISSIONS

    plugins = _plugin_dirs()
    assert plugins, "没有发现任何插件"
    failures = []
    for name, path in plugins:
        mf = os.path.join(path, "plugin.json")
        try:
            with open(mf, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            failures.append("%s: manifest 无法解析 (%s)" % (name, e))
            continue

        for key in ("name", "display_name", "version",
                    "permissions", "api_version"):
            if key not in data:
                failures.append("%s: 缺少字段 %s" % (name, key))

        bad_perms = [p for p in data.get("permissions", [])
                     if p not in ALL_PERMISSIONS]
        if bad_perms:
            failures.append("%s: 未知权限 %s" % (name, bad_perms))

        try:
            parts = [int(x) for x in
                     str(data.get("api_version", "0")).split(".")]
            assert len(parts) >= 2
        except Exception:
            failures.append("%s: api_version 不可解析 %r"
                            % (name, data.get("api_version")))

        # 入口模块**不 import**（插件模块顶层会创建 QObject/定时器，
        # 在无 QApplication 或测试环境下执行会引入 Qt 副作用）——
        # 改用 AST 静态检查类与方法是否存在。
        entry = os.path.join(path, "__init__.py")
        if not os.path.isfile(entry):
            failures.append("%s: 缺少入口 __init__.py" % name)
            continue
        try:
            with open(entry, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=entry)
            plugin_cls = next(
                (n for n in tree.body
                 if isinstance(n, ast.ClassDef) and n.name == "Plugin"),
                None)
            if plugin_cls is None:
                failures.append("%s: 入口缺少 Plugin 类" % name)
                continue
            methods = {n.name for n in plugin_cls.body
                       if isinstance(n, (ast.FunctionDef,
                                         ast.AsyncFunctionDef))}
            for hook in ("on_activate", "on_deactivate"):
                if hook not in methods:
                    failures.append("%s: Plugin 缺少 %s" % (name, hook))
        except SyntaxError as e:
            failures.append("%s: 入口语法错误 (%s)" % (name, e))
        except Exception as e:
            failures.append("%s: 入口静态检查失败 (%s)" % (name, e))

    assert not failures, "插件清单契约失败:\n" + "\n".join(failures)
    print("  清单契约通过: %d 个插件" % len(plugins))


# ============================================================
# 3. SDK 自检：API 面存在且可见
# ============================================================
def test_api_surface_has_extension_points(qapp):
    """所有已发布扩展点都在 PluginAPI 上（防止误删/改名）"""
    from app.plugins import PluginAPI

    expected = [
        "register_completion_provider", "publish_diagnostics",
        "clear_diagnostics", "run_background",
        "register_hover_provider", "register_code_action_provider",
        "add_editor_context_menu", "add_status_item", "add_decoration",
        "register_settings_schema",
    ]
    missing = [name for name in expected if not hasattr(PluginAPI, name)]
    assert not missing, "PluginAPI 缺少扩展点: %s" % missing
