# -*- coding: utf-8 -*-
"""v2.25 B2.1b：隔离插件 hover/code-action/右键 provider 接线"""

import json
import os
import time

from PyQt5.QtWidgets import QMainWindow


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pump(qapp, cond, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.05)
        if cond():
            return True
    return False


class FakeWin(QMainWindow):
    def __init__(self):
        super().__init__()
        self.hover = None
        self.code = None
        self.ctx = None

    def register_plugin_hover_provider(self, provider, language_ids=None, plugin_name=""):
        self.hover = (provider, language_ids, plugin_name)
        return True

    def register_plugin_code_action_provider(self, provider, language_ids=None, plugin_name=""):
        self.code = (provider, language_ids, plugin_name)
        return True

    def add_plugin_editor_context_action(self, label, callback, plugin_name=""):
        self.ctx = (label, callback, plugin_name)
        return True


def test_isolated_providers_end_to_end(tmp_path, qapp):
    from ui.isolated_plugins import IsolatedPluginHost

    d = tmp_path / "prov"
    d.mkdir()
    (d / "plugin.json").write_text(
        json.dumps(
            {
                "name": "prov",
                "version": "1.0.0",
                "permissions": ["editor_read", "editor_write", "dialog"],
            }
        ),
        encoding="utf-8",
    )
    (d / "__init__.py").write_text(
        """
class Plugin:
    def on_activate(self):
        self.api.register_hover_provider(self.hover, ["json"])
        self.api.register_code_action_provider(self.actions, ["json"])
        self.api.add_editor_context_menu("测试动作", self.ctx)
    def hover(self, line, col, filepath="", language=""):
        return "hover:%s:%s" % (line, col)
    def actions(self, line, col, filepath="", language=""):
        return [{"title": "DoIt", "kind": "quickfix", "callback": self.run_it}]
    def run_it(self):
        self.api.log("action-called")
    def ctx(self):
        self.api.log("ctx-called")
    def on_deactivate(self):
        pass
""",
        encoding="utf-8",
    )
    win = FakeWin()
    host = IsolatedPluginHost(win)
    try:
        host.start({"prov"}, plugins_dir=str(tmp_path))
        assert _pump(qapp, lambda: win.hover and win.code and win.ctx)
        assert win.hover[0](2, 3, filepath="a.json", language="json") == "hover:2:3"
        items = win.code[0](2, 3, filepath="a.json", language="json")
        assert items and items[0]["title"] == "DoIt"
        cb = items[0]["callback"]
        cb()
        assert _pump(
            qapp, lambda: any("action-called" in m for _l, m in host.runtimes["prov"].logs)
        )
        win.ctx[1]()
        assert _pump(qapp, lambda: any("ctx-called" in m for _l, m in host.runtimes["prov"].logs))
    finally:
        host.stop_all()
        win.close()


def test_json_formatter_isolated_registers_providers(qapp):
    from ui.isolated_plugins import IsolatedPluginHost

    win = FakeWin()
    host = IsolatedPluginHost(win)
    try:
        host.start({"json_formatter"})
        assert "json_formatter" in host.runtimes, "json_formatter 未完成隔离激活"
        assert _pump(qapp, lambda: win.hover is not None and win.code is not None)
        # 代码操作代理应返回列表（无文本时可为空）
        items = win.code[0](0, 0, filepath="a.json", language="json")
        assert isinstance(items, list)
    finally:
        host.stop_all()
        win.close()
