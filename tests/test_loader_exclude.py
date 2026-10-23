# -*- coding: utf-8 -*-
"""B-3c：加载器导入级排除测试（沙箱插件不被主进程 import）"""
import json
import os


def _mk_plugin(root, name, write_marker=False):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    code = "class Plugin:\n    NAME = %r\n    VERSION = '1.0.0'\n" % name
    if write_marker:
        code += ("\nimport os\nwith open(os.path.join(os.path.dirname("
                 "__file__), 'IMPORTED'), 'w') as f:\n"
                 "    f.write('x')\n")
    (d / "__init__.py").write_text(code, encoding="utf-8")
    (d / "plugin.json").write_text(json.dumps({
        "name": name, "display_name": name, "version": "1.0.0",
        "permissions": ["editor_read"], "api_version": "2.0.0",
    }), encoding="utf-8")
    return d


def test_excluded_plugin_is_not_imported(tmp_path):
    from infrastructure.plugin_loader import PluginLoader

    root = tmp_path / "plugins"
    root.mkdir()
    _mk_plugin(root, "normal_plugin")
    sandbox_dir = _mk_plugin(root, "sandbox_plugin", write_marker=True)
    marker = sandbox_dir / "IMPORTED"

    loader = PluginLoader()
    result = loader.load_all(
        plugin_dir=str(root),
        api_factory=lambda spec: object(),
        auto_activate=False,
        exclude_names={"sandbox_plugin"},
    )
    assert result.total == 1, result.total
    assert not marker.exists(), "被排除插件不应被主进程 import"
    assert "sandbox_plugin" not in loader.specs


def test_without_exclude_plugin_is_imported(tmp_path):
    from infrastructure.plugin_loader import PluginLoader

    root = tmp_path / "plugins2"
    root.mkdir()
    sandbox_dir = _mk_plugin(root, "sandbox_plugin2", write_marker=True)
    marker = sandbox_dir / "IMPORTED"
    loader = PluginLoader()
    result = loader.load_all(
        plugin_dir=str(root),
        api_factory=lambda spec: object(),
        auto_activate=False,
    )
    assert result.total == 1
    assert marker.exists(), "未排除时应正常 import（对照组）"