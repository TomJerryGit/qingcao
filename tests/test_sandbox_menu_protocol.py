# -*- coding: utf-8 -*-
"""P1 第1步：沙箱菜单/状态代理协议"""
PLUGIN = "\n".join([
    "class Plugin:",
    "    NAME = 'menu_demo'",
    "    VERSION = '1.0.0'",
    "",
    "    def __init__(self):",
    "        self.invoked = []",
    "",
    "    def menu_items(self):",
    "        return [",
    "            {'id': 'ignore_all', 'label': '忽略全部',",
    "             'path': '工具/拼写检查'},",
    "            {'id': 'recheck', 'label': '重新检查', 'path': ''},",
    "            {'label': 'no-id'},  # 无 id，应被过滤",
    "            'not-a-dict',",
    "        ]",
    "",
    "    def invoke_menu(self, mid):",
    "        self.invoked.append(mid)",
    "        return mid == 'ignore_all'",
    "",
    "    def status_text(self):",
    "        return '拼写: 3 条'",
])


def _mk(tmp_path, name="menu_demo"):
    d = tmp_path / name
    d.mkdir(parents=True)
    (d / "__init__.py").write_text(PLUGIN, encoding="utf-8")
    (d / "plugin.json").write_text('{"name": "menu_demo"}',
                                   encoding="utf-8")
    return str(d)


def test_menu_items_protocol(tmp_path):
    from infrastructure.plugin_sandbox_manager import SandboxedPlugin
    sp = SandboxedPlugin(_mk(tmp_path), timeout=5)
    try:
        items = sp.menu_items()
        assert len(items) == 2
        assert items[0]["id"] == "ignore_all"
        assert items[0]["label"] == "忽略全部"
        assert items[1]["id"] == "recheck"
        assert sp.invoke_menu("ignore_all") is True
        assert sp.invoke_menu("recheck") is False
        assert sp.invoke_menu("") is False
        assert sp.status_text() == "拼写: 3 条"
    finally:
        sp.close()


def test_missing_menu_methods_degrade(tmp_path):
    from infrastructure.plugin_sandbox_manager import SandboxedPlugin
    d = tmp_path / "plain"
    d.mkdir()
    (d / "__init__.py").write_text(
        "class Plugin:\n    NAME='x'\n", encoding="utf-8")
    (d / "plugin.json").write_text('{"name": "x"}', encoding="utf-8")
    sp = SandboxedPlugin(str(d), timeout=3)
    try:
        assert sp.menu_items() == []
        assert sp.invoke_menu("x") is False
        assert sp.status_text() == ""
    finally:
        sp.close()