# -*- coding: utf-8 -*-
"""v2.25 插件模板生成器"""

import importlib.util
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location(
        "qc_new_plugin", os.path.join(ROOT, "tools", "new_plugin.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_create_plugin_files_and_syntax(tmp_path):
    mod = _load()
    target = mod.create_plugin(
        "demo_tool",
        dest=str(tmp_path),
        display="演示工具",
        author="Tester",
        permissions=["editor_read", "dialog"],
    )
    assert os.path.isfile(os.path.join(target, "plugin.json"))
    assert os.path.isfile(os.path.join(target, "__init__.py"))
    assert os.path.isfile(os.path.join(target, "README.md"))
    manifest = json.load(open(os.path.join(target, "plugin.json"), encoding="utf-8"))
    assert manifest["name"] == "demo_tool"
    assert manifest["display_name"] == "演示工具"
    assert manifest["api_version"] == "2.0.0"
    assert manifest["permissions"] == ["editor_read", "dialog"]
    src = open(os.path.join(target, "__init__.py"), encoding="utf-8").read()
    compile(src, "__init__.py", "exec")
    assert "class Plugin(PluginBase)" in src
    assert 'NAME = "demo_tool"' in src


def test_invalid_id_and_existing_dir(tmp_path):
    mod = _load()
    try:
        mod.create_plugin("Bad-Id", dest=str(tmp_path))
    except ValueError:
        pass
    else:
        raise AssertionError("非法 id 未报错")
    target = mod.create_plugin("ok_plugin", dest=str(tmp_path))
    try:
        mod.create_plugin("ok_plugin", dest=str(tmp_path))
    except FileExistsError:
        pass
    else:
        raise AssertionError("已存在目录未报错")
    assert os.path.isdir(target)
