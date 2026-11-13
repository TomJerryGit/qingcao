# -*- coding: utf-8 -*-
"""插件隔离开关（B1）：QINGCAO_PLUGIN_ISOLATION=off|demo|all。"""
import os


# 已验证可在子进程完整运行的插件（B2.1 能力面）
ISOLATABLE_PLUGINS = {
    "demo", "wordcount", "json_formatter", "sandbox_demo",
    "todo_panel", "markdown_preview", "logtail",
}
DEMO_PLUGINS = ISOLATABLE_PLUGINS


def isolation_mode():
    return (os.environ.get("QINGCAO_PLUGIN_ISOLATION", "off") or "off").strip().lower()


def should_isolate(plugin_name):
    if plugin_name not in ISOLATABLE_PLUGINS:
        return False
    mode = isolation_mode()
    if mode in ("1", "all", "strict", "demo"):
        return True
    return False


def isolated_plugin_names(plugins_dir=None):
    """当前模式下应由子进程承载的插件名集合。"""
    import json
    import os

    mode = isolation_mode()
    if mode in ("off", "", "0"):
        return set()
    root = plugins_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins")
    names = set()
    try:
        for entry in os.listdir(root):
            mf = os.path.join(root, entry, "plugin.json")
            if not os.path.isfile(mf):
                continue
            try:
                data = json.load(open(mf, encoding="utf-8"))
            except Exception:
                continue
            name = data.get("name") or entry
            # 仅隔离已验证兼容的插件；其余保持进程内（避免 all 模式破坏功能）
            if name not in ISOLATABLE_PLUGINS:
                continue
            if mode in ("demo", "1", "all", "strict"):
                names.add(name)
    except Exception:
        pass
    return names
