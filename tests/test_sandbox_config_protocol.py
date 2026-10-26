# -*- coding: utf-8 -*-
"""P1 配置代理第1步：config_schema / config_apply 协议"""
PLUGIN = "\n".join([
    "class Plugin:",
    "    NAME = 'cfg_demo'",
    "    VERSION = '1.0.0'",
    "",
    "    def __init__(self):",
    "        self.applied = []",
    "",
    "    def config_schema(self):",
    "        return {",
    "            'enabled': {'type': 'bool', 'label': '启用',",
    "                        'default': True},",
    "            'max_words': {'type': 'int', 'label': '上限'},",
    "            'bad_type': {'type': 'weird'},",
    "            'not-a-dict': 1,",
    "        }",
    "",
    "    def on_config(self, values):",
    "        self.applied.append(values)",
    "        return True",
])


def _mk(tmp_path):
    d = tmp_path / "cfg_demo"
    d.mkdir()
    (d / "__init__.py").write_text(PLUGIN, encoding="utf-8")
    (d / "plugin.json").write_text('{"name": "cfg_demo"}',
                                   encoding="utf-8")
    return str(d)


def test_config_schema_and_apply(tmp_path):
    from infrastructure.plugin_sandbox_manager import SandboxedPlugin
    sp = SandboxedPlugin(_mk(tmp_path), timeout=5)
    try:
        schema = sp.config_schema()
        assert set(schema) == {"enabled", "max_words", "bad_type"}
        assert schema["enabled"]["type"] == "bool"
        assert schema["enabled"]["default"] is True
        assert schema["bad_type"]["type"] == "str"
        assert sp.config_apply({"enabled": False, "max_words": 50}) is True
        assert sp.config_apply({}) is False
    finally:
        sp.close()


def test_missing_config_methods_degrade(tmp_path):
    from infrastructure.plugin_sandbox_manager import SandboxedPlugin
    d = tmp_path / "plain"
    d.mkdir()
    (d / "__init__.py").write_text("class Plugin:\n    NAME='x'\n",
                                   encoding="utf-8")
    (d / "plugin.json").write_text('{"name": "x"}', encoding="utf-8")
    sp = SandboxedPlugin(str(d), timeout=3)
    try:
        assert sp.config_schema() == {}
        assert sp.config_apply({"a": 1}) is False
    finally:
        sp.close()