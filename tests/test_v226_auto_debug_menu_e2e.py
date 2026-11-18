# -*- coding: utf-8 -*-
"""v2.26 Sprint1：自动调试真实菜单链路 e2e（AI 桩，不联网）"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _Client:
    def __init__(self):
        self.calls = []

    def chat(self, prompt, system="", use_history=False, **kwargs):
        self.calls.append(prompt)
        return "```python\nprint('fixed')\n```"


class _API:
    def __init__(self, path):
        self.path = path
        self.menus = {}
        self.messages = []
        self.status = []
        self.client = _Client()

    def __getattr__(self, name):
        return lambda *a, **k: None

    def _host_window(self):
        return None

    def get_current_filepath(self):
        return self.path

    def get_config(self, *a, **k):
        return None

    def add_menu(self, path, callback=None, *a, **k):
        self.menus[path] = callback

    def register_settings_schema(self, *a, **k):
        pass

    def register_status_item(self, *a, **k):
        return 0

    def ask_string(self, *a, **k):
        return ("1", True)

    def get_ai_client(self):
        return self.client

    def show_status(self, *a, **k):
        self.status.append(a)

    def show_message(self, *a, **k):
        self.messages.append(a)

    def log(self, *a, **k):
        pass


def test_auto_debug_menu_e2e(tmp_path, qapp):
    from plugins.ai_assistant import Plugin

    f = tmp_path / "bug.py"
    f.write_text("print(undefined_name)\n", encoding="utf-8")
    plugin = Plugin()
    api = _API(str(f))
    plugin.api = api
    plugin._register_menus()
    action = next((cb for path, cb in api.menus.items() if "自动调试当前文件" in path), None)
    assert action is not None
    action()
    assert "fixed" in f.read_text(encoding="utf-8")
    assert api.client.calls
    assert any("自动调试结果" in str(m) for m in api.messages)
