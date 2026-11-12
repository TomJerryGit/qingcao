# -*- coding: utf-8 -*-
"""v2.25 插件沙箱阶段 A：静态审计/可信列表"""

import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_audit_source_detects_import_and_call(tmp_path):
    from core.plugin_guard import audit_source

    p = tmp_path / "bad.py"
    p.write_text(
        "import subprocess\nimport os\n\ndef run():\n    os.system('whoami')\n    subprocess.Popen(['x'])\n",
        encoding="utf-8",
    )
    findings = audit_source(str(p))
    kinds = {(f["kind"], f["name"]) for f in findings}
    assert ("import", "subprocess") in kinds
    assert any(k == "call" and "os.system" in n for k, n in kinds)
    assert any(f["risk"] == "high" for f in findings)


def test_trusted_allowlist_marks_allowed(tmp_path, monkeypatch):
    import core.plugin_guard as g

    plugin = tmp_path / "plugins" / "demo_x"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text('{"name": "demo_x"}', encoding="utf-8")
    (plugin / "__init__.py").write_text("import ctypes\n", encoding="utf-8")
    trusted = tmp_path / "trusted.json"
    trusted.write_text(json.dumps({"plugins": ["demo_x"]}), encoding="utf-8")
    monkeypatch.setattr(g, "_TRUSTED_CACHE", None)
    monkeypatch.setenv("QINGCAO_TRUSTED_PLUGINS", str(trusted))
    mod = g.audit_plugin(str(plugin), "demo_x")
    # trusted_plugins() 默认路径不含 tmp；直接传 path 验证
    from core.plugin_guard import trusted_plugins

    assert "demo_x" in trusted_plugins(str(trusted))


def test_audit_all(tmp_path):
    from core.plugin_guard import audit_all

    root = tmp_path / "plugins"
    for name, body in (("a", "import socket\n"), ("b", "X = 1\n")):
        d = root / name
        d.mkdir(parents=True)
        (d / "plugin.json").write_text('{"name": "%s"}' % name, encoding="utf-8")
        (d / "__init__.py").write_text(body, encoding="utf-8")
    reports = audit_all(str(root))
    by = {r["plugin"]: r for r in reports}
    assert "a" in by and any(f["name"] == "socket" for f in by["a"]["findings"])
    assert not any(f["risk"] == "high" for f in by["b"]["findings"] if f["name"] == "socket")


def test_default_trusted_list_has_first_party():
    from core.plugin_guard import trusted_plugins

    names = trusted_plugins(os.path.join(ROOT, "resources", "trusted_plugins.json"))
    assert "demo" in names and "wordcount" in names
