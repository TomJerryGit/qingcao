# -*- coding: utf-8 -*-
"""插件模板生成器（v2.25 阶段 3.2）。

python tools/new_plugin.py my_plugin
python tools/new_plugin.py my_plugin --display "我的插件" --permissions editor_read,dialog
"""

import argparse
import io
import json
import os
import re
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def _manifest(plugin_id, display, desc, author, version, license_, category, perms):
    return {
        "name": plugin_id,
        "display_name": display,
        "version": version,
        "description": desc,
        "author": author,
        "license": license_,
        "type": "plugin",
        "category": category,
        "tags": [plugin_id],
        "permissions": perms,
        "dependencies": [],
        "api_version": "2.0.0",
        "enabled": True,
        "auto_load": True,
        "load_order": 200,
        "keywords": [],
    }


def _plugin_init(plugin_id, display, desc, author, version, perms):
    return (
        "# -*- coding: utf-8 -*-\n"
        '"""' + display + ' 插件（由 tools/new_plugin.py 生成）。"""\n'
        "from app.plugins import PluginBase\n\n\n"
        "class Plugin(PluginBase):\n"
        '    NAME = "' + plugin_id + '"\n'
        '    VERSION = "' + version + '"\n'
        '    DESCRIPTION = "' + desc + '"\n'
        '    AUTHOR = "' + author + '"\n'
        "    PERMISSIONS = " + repr(perms) + "\n\n"
        "    def on_activate(self):\n"
        '        self.api.log("' + display + ' 已激活")\n'
        '        self.api.add_menu("工具/' + display + '/运行示例", self.run_demo)\n\n'
        "    def on_deactivate(self):\n"
        '        self.api.log("' + display + ' 已停用")\n\n'
        "    def run_demo(self):\n"
        "        text = self.api.get_current_text()\n"
        '        self.api.show_message("' + display + '", f"当前字符数: {len(text)}")\n'
    )


def _readme(plugin_id, display):
    return (
        "# " + display + "（" + plugin_id + "）\n\n"
        "青草编辑器插件（由 `tools/new_plugin.py` 生成）。\n\n"
        "## 开发\n\n"
        "```powershell\npython main.py   # 启动后：工具 → 插件管理 → 重载\n```\n\n"
        "- 清单：`plugin.json`；入口：`__init__.py` 中的 `Plugin` 类；\n"
        "- 文档：`docs/plugin_development.md`。\n\n"
        "## 本地安装\n\n把本目录（或 zip）放到 `plugins/` 下，重载插件即可。\n"
    )


def create_plugin(
    plugin_id,
    dest=None,
    display=None,
    desc="",
    author="Your Name",
    version="1.0.0",
    license_="MIT",
    category="tool",
    permissions=None,
):
    """生成插件目录；返回目标路径。已存在且非空时抛 FileExistsError。"""
    if not _ID_RE.match(plugin_id or ""):
        raise ValueError("插件 id 必须是小写字母开头的 snake_case（2–41 字符）")
    perms = permissions or ["editor_read", "dialog"]
    base = dest or os.path.join(ROOT, "plugins")
    target = os.path.join(base, plugin_id)
    if os.path.isdir(target) and os.listdir(target):
        raise FileExistsError("目录已存在且非空: %s" % target)
    os.makedirs(target, exist_ok=True)
    display = display or plugin_id.replace("_", " ").title()
    manifest = _manifest(
        plugin_id, display, desc or (display + " 插件"), author, version, license_, category, perms
    )
    io.open(os.path.join(target, "plugin.json"), "w", encoding="utf-8", newline="\n").write(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    io.open(os.path.join(target, "__init__.py"), "w", encoding="utf-8", newline="\n").write(
        _plugin_init(plugin_id, display, manifest["description"], author, version, perms)
    )
    io.open(os.path.join(target, "README.md"), "w", encoding="utf-8", newline="\n").write(
        _readme(plugin_id, display)
    )
    return target


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成青草编辑器插件模板")
    ap.add_argument("plugin_id")
    ap.add_argument("--dest", default=None, help="父目录（默认 plugins/）")
    ap.add_argument("--display", default=None)
    ap.add_argument("--description", default="")
    ap.add_argument("--author", default="Your Name")
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--license", dest="license_", default="MIT")
    ap.add_argument("--category", default="tool")
    ap.add_argument("--permissions", default="editor_read,dialog")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    perms = [p.strip() for p in args.permissions.split(",") if p.strip()]
    try:
        if args.dry_run:
            print("[new-plugin] 将生成 %s（dry-run）" % args.plugin_id)
            return 0
        target = create_plugin(
            args.plugin_id,
            dest=args.dest,
            display=args.display,
            desc=args.description,
            author=args.author,
            version=args.version,
            license_=args.license_,
            category=args.category,
            permissions=perms,
        )
    except (ValueError, FileExistsError) as e:
        print("[new-plugin] %s" % e)
        return 1
    print("[new-plugin] 已生成: %s" % target)
    print("下一步：重启/重载插件 → 工具菜单出现「%s」示例项" % (args.display or args.plugin_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
