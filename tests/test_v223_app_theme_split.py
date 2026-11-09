# -*- coding: utf-8 -*-
"""v2.23：app/plugins.py 与 theme_loader.py 拆分结构"""

import dataclasses
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _lines(rel):
    return len(open(os.path.join(ROOT, rel), encoding="utf-8").readlines())


def test_app_plugins_split():
    assert _lines("app/plugins.py") < 600
    assert os.path.isfile(os.path.join(ROOT, "app", "plugin_api.py"))
    from app.plugin_api import PluginAPI
    from app.plugins import PERMISSION_NETWORK, PluginBase, parse_permissions
    from app.plugins import PluginAPI as ReExported

    assert ReExported is PluginAPI
    assert callable(parse_permissions)
    assert PERMISSION_NETWORK and PluginBase is not None


def test_theme_split():
    assert _lines("infrastructure/theme_loader.py") < 1600
    assert os.path.isfile(os.path.join(ROOT, "infrastructure", "theme_model.py"))
    from infrastructure.theme_loader import Theme, ThemeLoader, ThemeManager
    from infrastructure.theme_model import BuiltinThemes, ThemeColors, adapt_qss_colors

    assert ThemeLoader and ThemeManager
    assert {f.name for f in dataclasses.fields(ThemeColors)}
    assert {f.name for f in dataclasses.fields(Theme)}
    assert BuiltinThemes is not None and callable(adapt_qss_colors)
