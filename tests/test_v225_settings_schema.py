# -*- coding: utf-8 -*-
"""v2.25 R1.2：插件 settings schema 对话框与隔离插件设置菜单"""

import json
import os
import time

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QMainWindow


def _pump(qapp, cond, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.05)
        if cond():
            return True
    return False


def test_normalize_schema_forms():
    from ui.plugin_settings_dialog import normalize_schema

    assert normalize_schema({"a": {"type": "int"}}) == [{"type": "int", "key": "a"}]
    assert normalize_schema([{"key": "b"}]) == [{"key": "b"}]


def test_dialog_values_and_save(tmp_path, qapp):
    from ui.plugin_settings_dialog import SchemaSettingsDialog

    settings = QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat)
    dlg = SchemaSettingsDialog(
        "demo",
        [
            {"key": "enabled", "type": "bool", "default": True},
            {"key": "n", "type": "int", "default": 3},
            {
                "key": "mode",
                "type": "choice",
                "default": "chars",
                "choices": [("字符", "chars"), ("词", "words")],
            },
            {"key": "name", "type": "str", "default": "x"},
        ],
        settings=settings,
    )
    try:
        dlg.widgets["enabled"][0].setChecked(False)
        dlg.widgets["n"][0].setValue(9)
        dlg.widgets["mode"][0].setCurrentIndex(1)
        dlg.widgets["name"][0].setText("hello")
        dlg.accept()
        assert settings.value("plugins/demo/enabled") in (False, "false")
        assert int(settings.value("plugins/demo/n")) == 9
        assert settings.value("plugins/demo/mode") == "words"
        assert settings.value("plugins/demo/name") == "hello"
    finally:
        dlg.deleteLater()


def test_isolated_plugin_settings_menu(tmp_path, qapp):
    from ui.isolated_plugins import IsolatedPluginHost

    d = tmp_path / "cfg_plugin"
    d.mkdir()
    (d / "plugin.json").write_text(
        json.dumps({"name": "cfg_plugin", "version": "1.0.0", "permissions": ["dialog"]}),
        encoding="utf-8",
    )
    (d / "__init__.py").write_text(
        """
class Plugin:
    def on_activate(self):
        self.api.register_settings_schema([
            {"key": "indent", "type": "int", "default": 2},
        ])
    def on_deactivate(self):
        pass
""",
        encoding="utf-8",
    )
    win = QMainWindow()
    host = IsolatedPluginHost(win)
    try:
        host.start({"cfg_plugin"}, plugins_dir=str(tmp_path))
        assert _pump(qapp, lambda: "cfg_plugin" in host.api.schemas)
        assert "cfg_plugin" in host.api._settings_actions
        dlg = host.api.open_settings("cfg_plugin")
        assert "indent" in dlg.widgets
        dlg.deleteLater()
    finally:
        host.stop_all()
        win.close()
