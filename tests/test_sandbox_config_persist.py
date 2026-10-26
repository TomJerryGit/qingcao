# -*- coding: utf-8 -*-
"""P1 配置代理第2步：宿主持久化（QSettings）"""
import os


def _settings(tmp_path, name="cfg_plugin"):
    from PyQt5.QtCore import QSettings
    path = os.path.join(str(tmp_path), name + ".ini")
    return QSettings(path, QSettings.IniFormat)


SCHEMA = {
    "enabled": {"type": "bool", "label": "启用", "default": True},
    "max_words": {"type": "int", "label": "上限", "default": 200},
    "ratio": {"type": "float", "label": "比例", "default": 0.5},
    "words": {"type": "str_list", "label": "词表", "default": ["a", "b"]},
    "mode": {"type": "str", "label": "模式", "default": "normal"},
}


def test_coerce_types():
    from infrastructure.plugin_sandbox_manager import config_coerce
    assert config_coerce(SCHEMA["enabled"], "false") is False
    assert config_coerce(SCHEMA["enabled"], 0) is False
    assert config_coerce(SCHEMA["max_words"], "42") == 42
    assert config_coerce(SCHEMA["max_words"], "bad") == 200
    assert abs(config_coerce(SCHEMA["ratio"], "1.5") - 1.5) < 1e-9
    assert config_coerce(SCHEMA["words"], '["x","y"]') == ["x", "y"]
    assert config_coerce(SCHEMA["words"], "x,y") == ["x", "y"]
    assert config_coerce(SCHEMA["mode"], None) == "normal"


def test_save_load_roundtrip(tmp_path):
    from infrastructure.plugin_sandbox_manager import load_plugin_config, save_plugin_config
    s = _settings(tmp_path)
    saved = save_plugin_config("cfg_plugin", SCHEMA,
                               {"enabled": False, "max_words": 50,
                                "ratio": 0.25, "words": ["z"],
                                "unknown_key": 1}, settings=s)
    assert saved["enabled"] is False and saved["max_words"] == 50
    assert "unknown_key" not in saved
    loaded = load_plugin_config("cfg_plugin", SCHEMA, settings=s)
    assert loaded["enabled"] is False
    assert loaded["max_words"] == 50
    assert loaded["words"] == ["z"]
    assert loaded["mode"] == "normal"


def test_load_defaults_when_empty(tmp_path):
    from infrastructure.plugin_sandbox_manager import load_plugin_config
    s = _settings(tmp_path, "empty_plugin")
    loaded = load_plugin_config("empty_plugin", SCHEMA, settings=s)
    assert loaded["enabled"] is True
    assert loaded["max_words"] == 200
    assert loaded["words"] == ["a", "b"]
    assert loaded["mode"] == "normal"