# -*- coding: utf-8 -*-
"""v2.26 P4：低风险插件激活冒烟（统一 FakeAPI）"""

import importlib
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _FakeAPI:
    def __init__(self):
        self.records = {"menus": [], "status": [], "settings": [], "providers": []}

    # 常用 getter
    def get_current_filepath(self):
        return ""

    def get_current_text(self):
        return "b\na\nb"

    def get_selected_text(self):
        return ""

    def get_config(self, key, default=None):
        return default

    def set_config(self, *a, **k):
        return True

    def current_editor(self):
        return None

    def all_editors(self):
        return []

    def log(self, *a, **k):
        pass

    def show_status(self, *a, **k):
        pass

    def show_message(self, *a, **k):
        pass

    def show_notification(self, *a, **k):
        pass

    def ask_string(self, *a, **k):
        return ("", False)

    def ask_yes_no(self, *a, **k):
        return False

    def add_menu(self, path, callback=None, **k):
        self.records["menus"].append(path)

    def add_status_item(self, text=None, *a, **k):
        self.records["status"].append(str(text or ""))
        return 0

    def register_settings_schema(self, schema, *a, **k):
        self.records["settings"].append(schema)

    def register_symbol_provider(self, *a, **k):
        self.records["providers"].append("symbol")

    def register_hover_provider(self, *a, **k):
        self.records["providers"].append("hover")

    def register_code_action_provider(self, *a, **k):
        self.records["providers"].append("code_action")

    def add_editor_context_menu(self, *a, **k):
        self.records["providers"].append("context")

    def clear_diagnostics(self):
        return 0

    def publish_diagnostics(self, *a, **k):
        return 0

    def subscribe(self, *a, **k):
        pass

    def register_command(self, *a, **k):
        pass

    def __getattr__(self, name):
        return lambda *a, **k: None


def _activate(module_name):
    mod = importlib.import_module(module_name)
    plugin = mod.Plugin()
    api = _FakeAPI()
    plugin.api = api
    plugin.on_activate()
    return plugin, api


def test_low_risk_plugins_activate():
    for mod in (
        "plugins.demo",
        "plugins.line_sort",
        "plugins.wordcount",
        "plugins.json_formatter",
        "plugins.logtail",
        "plugins.todo_panel",
        "plugins.markdown_preview",
        "plugins.my_plugin",
    ):
        plugin, api = _activate(mod)
        assert api.records["menus"] or api.records["status"], mod
        try:
            plugin.on_deactivate()
        except Exception:
            pass
