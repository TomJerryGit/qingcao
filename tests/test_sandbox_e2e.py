# -*- coding: utf-8 -*-
"""B-4/B-5：沙箱插件端到端（加载排除 -> 宿主代理 -> 符号合并 -> 退出关闭）"""
import json
import os


PLUGIN_LINES = [
    "# -*- coding: utf-8 -*-",
    "class Plugin:",
    "    NAME = 'e2e_sandbox'",
    "    VERSION = '1.0.0'",
    "",
    "    def symbols(self, text, filepath='', language=''):",
    "        if not (filepath or '').endswith('.sdemo'):",
    "            return []",
    "        return [{'name': 'S-' + l.strip()[3:].strip(),",
    "                 'type': 'namespace', 'line': i}",
    "                for i, l in enumerate((text or '').splitlines())",
    "                if l.strip().startswith('## ')]",
]
PLUGIN_CODE = "\n".join(PLUGIN_LINES) + "\n"


def _mk(root, name="e2e_sandbox", enabled=True):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "__init__.py").write_text(PLUGIN_CODE, encoding="utf-8")
    (d / "plugin.json").write_text(json.dumps({
        "name": name, "display_name": name, "version": "1.0.0",
        "permissions": ["editor_read"], "api_version": "2.0.0",
        "enabled": enabled, "sandbox": True,
    }), encoding="utf-8")
    return d


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    try:
        win._close_sandboxed_plugins()
    except Exception:
        pass
    win.close()


def test_repo_demo_is_disabled_by_default():
    from infrastructure.plugin_sandbox_manager import discover_sandboxed_plugins, is_sandbox_enabled
    repo_plugins = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "plugins")
    names = [n for n, _ in discover_sandboxed_plugins(repo_plugins)]
    assert "sandbox_demo" not in names
    d = os.path.join(repo_plugins, "sandbox_demo")
    assert is_sandbox_enabled(d) is False


def test_loader_excludes_and_host_proxies(qapp, tmp_path):
    from infrastructure.plugin_loader import PluginLoader
    from ui.main_window import MainWindow

    root = tmp_path / "plugins"
    root.mkdir()
    _mk(root)

    loader = PluginLoader()
    result = loader.load_all(
        plugin_dir=str(root), api_factory=lambda s: object(),
        auto_activate=False, exclude_names={"e2e_sandbox"})
    assert "e2e_sandbox" not in loader.specs
    assert result.total == 0

    win = MainWindow()
    try:
        win._sandbox_plugin_dir = str(root)
        text = "## 第一章\nbody\n## 第二章\n"
        items = win.collect_plugin_symbols(text, "a.sdemo", "sdemo")
        names = [i["name"] for i in items]
        assert "S-第一章" in names and "S-第二章" in names, names
        assert win.collect_plugin_symbols(text, "a.py", "python") == []
    finally:
        _close(win)


def test_disabled_sandbox_plugin_not_discovered(tmp_path):
    from infrastructure.plugin_sandbox_manager import discover_sandboxed_plugins
    root = tmp_path / "plugins2"
    root.mkdir()
    _mk(root, "off_plugin", enabled=False)
    assert discover_sandboxed_plugins(str(root)) == []