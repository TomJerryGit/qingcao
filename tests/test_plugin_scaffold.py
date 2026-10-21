# -*- coding: utf-8 -*-
"""插件脚手架（tools/new_plugin.py）测试"""
import ast
import importlib.util
import json
import subprocess
import sys


def _run(tmp_path, *args):
    return subprocess.run(
        [sys.executable, "tools/new_plugin.py", "--output", str(tmp_path)]
        + list(args), capture_output=True, text=True,
        encoding="utf-8", errors="replace")


def test_scaffold_generates_conformant_plugin(tmp_path):
    r = _run(tmp_path, "--name", "scaffold_demo",
             "--display-name", "脚手架示例",
             "--permissions", "editor_read,dialog",
             "--points", "settings,status,hover,diagnostics,symbols")
    assert r.returncode == 0, r.stdout + r.stderr

    d = tmp_path / "scaffold_demo"
    data = json.loads((d / "plugin.json").read_text(encoding="utf-8"))
    for key in ("name", "display_name", "version", "description",
                "author", "license", "type", "category", "tags",
                "permissions", "api_version", "enabled", "auto_load"):
        assert key in data, "manifest 缺字段 %s" % key
    assert data["permissions"] == ["editor_read", "dialog"]
    assert data["display_name"] == "脚手架示例"

    tree = ast.parse((d / "__init__.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "Plugin")
    methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    assert {"on_activate", "on_deactivate", "hello"} <= methods

    src = (d / "__init__.py").read_text(encoding="utf-8")
    assert "register_settings_schema" in src
    assert "add_status_item" in src
    assert "register_hover_provider" in src

    # 生成模块可被真实导入（PluginBase 可解析）
    spec = importlib.util.spec_from_file_location(
        "scaffold_demo_mod", d / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.Plugin.NAME == "scaffold_demo"


def test_scaffold_rejects_invalid_input(tmp_path):
    assert _run(tmp_path, "--name", "Bad-Name").returncode != 0
    assert _run(tmp_path, "--name", "okname",
                "--permissions", "not_a_perm").returncode != 0
    assert _run(tmp_path, "--name", "okname",
                "--points", "nope").returncode != 0


def test_scaffold_refuses_overwrite_without_force(tmp_path):
    assert _run(tmp_path, "--name", "dup_plugin").returncode == 0
    second = _run(tmp_path, "--name", "dup_plugin")
    assert second.returncode != 0
    assert _run(tmp_path, "--name", "dup_plugin",
                "--force").returncode == 0
