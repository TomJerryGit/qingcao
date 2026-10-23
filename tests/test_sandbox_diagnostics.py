# -*- coding: utf-8 -*-
"""C-1：沙箱受限诊断协议测试"""
import json


PLUGIN = "\n".join([
    "class Plugin:",
    "    NAME = 'diag_demo'",
    "    VERSION = '1.0.0'",
    "",
    "    def diagnostics(self, text):",
    "        issues = [",
    "            {'line': 0, 'col': 1, 'severity': 'warning',",
    "             'message': 'bad word', 'code': 'D001'},",
    "            {'line': 2, 'col': 0, 'severity': 'ERROR',",
    "             'message': 'error here', 'code': 'D002'},",
    "            {'line': -5, 'col': -1, 'severity': 'weird',",
    "             'message': 'normalized', 'code': 'D003'},",
    "            'not-a-dict',",
    "            {'line': 1, 'message': ''},",
    "        ]",
    "        issues += [{'line': i, 'col': 0, 'severity': 'info',",
    "                    'message': 'm%d' % i} for i in range(600)]",
    "        return issues",
])


def _mk(tmp_path):
    d = tmp_path / "diag_demo"
    d.mkdir(parents=True)
    (d / "__init__.py").write_text(PLUGIN, encoding="utf-8")
    (d / "plugin.json").write_text('{"name": "diag_demo"}',
                                   encoding="utf-8")
    return str(d)


def test_sandbox_diagnostics_normalized_and_capped(tmp_path):
    from infrastructure.plugin_sandbox_manager import SandboxedPlugin
    sp = SandboxedPlugin(_mk(tmp_path), timeout=5)
    try:
        out = sp.diagnostics("hello")
        assert isinstance(out, list)
        assert len(out) == 500, len(out)
        first = out[0]
        assert first["code"] == "D001" and first["severity"] == "warning"
        assert out[1]["severity"] == "error"
        third = out[2]
        assert third["line"] == 0 and third["col"] == 0
        assert third["severity"] == "warning"
        assert all(isinstance(i["message"], str) and i["message"]
                   for i in out)
    finally:
        sp.close()


def test_missing_diagnostics_returns_empty(tmp_path):
    from infrastructure.plugin_sandbox_manager import SandboxedPlugin
    d = tmp_path / "diag_demo"
    d.mkdir()
    (d / "__init__.py").write_text(
        "class Plugin:\n    NAME='x'\n", encoding="utf-8")
    (d / "plugin.json").write_text('{"name": "x"}', encoding="utf-8")
    sp = SandboxedPlugin(str(d), timeout=3)
    try:
        assert sp.diagnostics("x") == []
    finally:
        sp.close()