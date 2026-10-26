# -*- coding: utf-8 -*-
"""P2：沙箱忽略词 RPC"""
PLUGIN = "\n".join([
    "class Plugin:",
    "    NAME = 'ignore_demo'",
    "    VERSION = '1.0.0'",
    "",
    "    def __init__(self):",
    "        self.words = []",
    "",
    "    def diagnostics(self, text):",
    "        return [{'line': 0, 'col': 0, 'severity': 'warning',",
    "                 'message': '可疑拼写：thiss', 'code': 'S1'}]",
    "",
    "    def add_ignore_word(self, word):",
    "        self.words.append(word)",
    "        return True",
])


def _mk(tmp_path):
    d = tmp_path / "ignore_demo"
    d.mkdir(parents=True)
    (d / "__init__.py").write_text(PLUGIN, encoding="utf-8")
    (d / "plugin.json").write_text('{"name": "ignore_demo"}',
                                   encoding="utf-8")
    return str(d)


def test_sandbox_add_ignore_word(tmp_path):
    from infrastructure.plugin_sandbox_manager import SandboxedPlugin
    sp = SandboxedPlugin(_mk(tmp_path), timeout=5)
    try:
        assert sp.add_ignore_word("thiss") is True
        assert sp.add_ignore_word("") is False
        items = sp.diagnostics("x")
        assert items and items[0]["code"] == "S1"
    finally:
        sp.close()


def test_spell_check_sandbox_manifest_and_method():
    import json
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    manifest = json.load(open(os.path.join(
        root, "plugins", "spell_check", "plugin.json"), encoding="utf-8"))
    assert manifest.get("sandbox") is True
    src = open(os.path.join(root, "plugins", "spell_check",
                            "__init__.py"), encoding="utf-8").read()
    assert "def add_ignore_word(self, word)" in src
    assert "def diagnostics(self, text)" in src