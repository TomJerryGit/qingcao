# -*- coding: utf-8 -*-
"""v2.26：隔离加载器支持插件包相对导入"""

import os
import sys


def test_loader_supports_relative_import(tmp_path):
    plugin = tmp_path / "rel_plugin"
    plugin.mkdir()
    (plugin / "helper.py").write_text("VALUE = 42\n", encoding="utf-8")
    (plugin / "__init__.py").write_text(
        "from .helper import VALUE\nclass Plugin:\n    VALUE = VALUE\n", encoding="utf-8"
    )
    from core.plugin_host import load_plugin

    mod = load_plugin(str(plugin))
    assert mod.VALUE == 42
