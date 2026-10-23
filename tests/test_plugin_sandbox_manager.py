# -*- coding: utf-8 -*-
"""插件子进程沙箱管理（B-3）测试"""
import json
import os


PLUGIN = '''# -*- coding: utf-8 -*-
class Plugin:
    NAME = "sandbox_demo"
    VERSION = "1.0.0"

    def symbols(self, text, filepath="", language=""):
        return [{"name": "s1", "type": "function", "line": 0}]

    def hover(self, line, col, filepath="", language=""):
        return "hover-%d" % line

    def completion(self, prefix, language="", filepath=""):
        return [prefix + "_c"]
'''

BROKEN = '''# -*- coding: utf-8 -*-
raise RuntimeError("broken on import")
'''


def _make(tmp_path, name="sandbox_demo", code=PLUGIN,
          sandbox=True, manifest_extra=None):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "__init__.py").write_text(code, encoding="utf-8")
    data = {"name": name, "display_name": name, "version": "1.0.0",
            "permissions": ["editor_read"], "api_version": "2.0.0"}
    if sandbox:
        data["sandbox"] = True
    if manifest_extra:
        data.update(manifest_extra)
    (d / "plugin.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return d


def test_is_sandbox_enabled_defaults_false(tmp_path):
    from infrastructure.plugin_sandbox_manager import is_sandbox_enabled
    on = _make(tmp_path, "on_plugin", sandbox=True)
    off = _make(tmp_path, "off_plugin", sandbox=False)
    assert is_sandbox_enabled(str(on)) is True
    assert is_sandbox_enabled(str(off)) is False
    assert is_sandbox_enabled(str(tmp_path / "nope")) is False


def test_discover_only_sandboxed(tmp_path):
    from infrastructure.plugin_sandbox_manager import discover_sandboxed_plugins
    _make(tmp_path, "on_plugin", sandbox=True)
    _make(tmp_path, "off_plugin", sandbox=False)
    names = [n for n, _p in discover_sandboxed_plugins(str(tmp_path))]
    assert names == ["on_plugin"]


def test_readonly_proxy_roundtrip(tmp_path):
    from infrastructure.plugin_sandbox_manager import SandboxedPlugin
    d = _make(tmp_path)
    sp = SandboxedPlugin(str(d), timeout=5)
    try:
        assert sp.available() is True
        assert sp.describe()["name"] == "sandbox_demo"
        syms = sp.symbols("x")
        assert syms and syms[0]["name"] == "s1"
        assert sp.hover(3, 0) == "hover-3"
        assert sp.completion("a") == ["a_c"]
    finally:
        sp.close()


def test_broken_plugin_degrades_without_raising(tmp_path):
    from infrastructure.plugin_sandbox_manager import SandboxedPlugin
    d = _make(tmp_path, "broken", code=BROKEN, sandbox=True)
    sp = SandboxedPlugin(str(d), timeout=1.0)
    try:
        assert sp.available() is False or sp.degraded
        # 不抛异常，返回空结果
        assert sp.symbols("x") == []
        assert sp.completion("a") == []
        assert sp.degraded is True
        assert sp.last_error
    finally:
        sp.close()