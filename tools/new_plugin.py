# -*- coding: utf-8 -*-
"""插件脚手架：一键生成符合规范 + conformance 契约的半成品插件

用法::

    python tools/new_plugin.py --name hello_tool
    python tools/new_plugin.py --name json_paths \
        --display-name "JSON 路径" \
        --permissions editor_read,dialog \
        --points settings,status,hover,diagnostics
    python tools/new_plugin.py --name demo --output D:\\tmp\\plugins --force

生成内容：
    plugins/<name>/plugin.json    —— 必填字段齐全（可直接过 conformance 清单契约）
    plugins/<name>/__init__.py    —— PluginBase 子类 + 生命周期 + 所选扩展点示例

设计目标（对应 docs/npp_plugin_benchmark_v2.3.md 的 P1-6）：
Notepad++ 提供 pluginTemplate；本项目此前只有 conformance 契约但没有
"从零开始"的骨架。脚手架生成的代码**默认就能通过**
`tests/test_plugin_conformance.py`（清单契约 / API 面 / 迁移覆盖除外），
把第三方插件的门槛从"读 2000 行 PluginAPI"降到"填几个参数"。
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,30}$")
VALID_PERMS = {"filesystem", "network", "process", "clipboard", "dialog",
               "editor_read", "editor_write", "terminal", "lsp",
               "debugger"}
VALID_POINTS = {"settings", "status", "completion", "hover", "diagnostics",
                "background", "code_action", "context_menu", "decoration",
                "symbols"}

_POINT_CODE = {
    "settings": '''        # 设置项：宿主自动生成「工具 → 插件设置」对话框
        self.api.register_settings_schema([
            {"key": "enabled", "label": "启用扩展", "type": "bool",
             "default": True},
            {"key": "max_items", "label": "最大条目", "type": "int",
             "default": 50, "min": 1, "max": 500},
        ])''',
    "status": '''        # 状态栏常驻项（需 dialog 权限）
        self._status_item = self.api.add_status_item("%(display)s: 就绪")''',
    "completion": '''        # 补全提供者（需 editor_read 权限）
        self.api.register_completion_provider(
            self.suggest, language_ids=None)

    def suggest(self, prefix, language="", filepath=""):
        """返回候选词；重活请用 run_background 处理"""
        if prefix and len(prefix) >= 2:
            return [prefix + "_demo"]
        return []''',
    "hover": '''        # 悬浮提示（需 editor_read 权限）
        self.api.register_hover_provider(
            self.hover_text, language_ids=None)

    def hover_text(self, line, col, filepath="", language=""):
        return "第 %%d 行（插件提示示例）" %% (line + 1)''',
    "diagnostics": '''        # 诊断：把问题发布到「问题」面板（需 editor_read 权限）
        self.api.add_menu("工具/%(display)s/检查并报告", self.check)

    def check(self):
        self.api.clear_diagnostics()
        text = self.api.get_current_text() or ""
        issues = []
        for idx, line in enumerate(text.splitlines()):
            if "TODO" in line:
                issues.append({"line": idx, "col": 0,
                               "severity": "info",
                               "message": "发现 TODO",
                               "code": "DEMO001"})
        n = self.api.publish_diagnostics(issues)
        self.api.show_status("报告了 %%d 个问题" %% n, 2500, "info")''',
    "background": '''        # 后台任务：子线程执行，回调回主线程
        self.api.add_menu("工具/%(display)s/后台示例", self.run_bg)

    def run_bg(self):
        self.api.run_background(
            lambda: 42,
            on_done=lambda value: self.api.show_status(
                "后台结果: %%s" %% value, 2500, "success"),
            name="demo-bg")''',
    "code_action": '''        # 代码操作（需 editor_write 权限）
        self.api.register_code_action_provider(
            self.code_actions, language_ids=None)

    def code_actions(self, line, col, filepath="", language=""):
        return [{"title": "示例修复", "kind": "quickfix",
                 "callback": lambda: None}]''',
    "context_menu": '''        # 编辑器右键菜单（需 editor_read 权限）
        self.api.add_editor_context_menu(
            "%(display)s 示例动作", lambda: self.api.show_status("右键菜单", 2000))''',
    "decoration": '''        # 行装饰（需 editor_write 权限）
        self.api.add_menu("工具/%(display)s/标记当前行", self.decorate)

    def decorate(self):
        editor = self.api.current_editor()
        if editor is not None:
            line, _ = self.api.get_cursor_position()
            self.api.add_decoration(line, line, "#FFD700")''',
    "symbols": '''        # 符号提供者 → 大纲面板（需 editor_read 权限）
        self.api.register_symbol_provider(
            self.symbols, language_ids=None)

    def symbols(self, text, filepath="", language=""):
        return [{"name": "示例符号", "type": "namespace", "line": 0}]''',
}


def build_manifest(name, display, author, permissions, points):
    return {
        "name": name,
        "display_name": display,
        "version": "1.0.0",
        "description": "%s（由脚手架生成）" % display,
        "author": author,
        "license": "MIT",
        "type": "plugin",
        "category": "tool",
        "tags": ["scaffold"],
        "permissions": permissions,
        "dependencies": [],
        "api_version": "2.0.0",
        "enabled": True,
        "auto_load": True,
        "load_order": 100,
    }


def build_code(name, display, author, permissions, points):
    blocks = []
    for point in ("settings", "status", "completion", "hover", "diagnostics",
                  "background", "code_action", "context_menu", "decoration",
                  "symbols"):
        if point in points:
            blocks.append(_POINT_CODE[point] % {"display": display})
    point_code = "\n\n".join(blocks)
    has_method = any(p in points for p in
                     ("completion", "hover", "diagnostics", "background",
                      "code_action", "decoration", "symbols"))
    return '''# -*- coding: utf-8 -*-
"""%(display)s — 由 tools/new_plugin.py 生成

下一步：
1. 把目录放到 `plugins/` 下（或已在其中）；
2. 在「工具 → 插件管理」启用；
3. 用 conformance 检查清单/契约：
       python -m pytest tests/test_plugin_conformance.py -q
4. 需要新语言高亮？投放 `data/language_packs/*.qingcao-lang.json`，
   无需写代码（见 docs/language_packs.md）。
"""
from app.plugins import PluginBase


class Plugin(PluginBase):
    NAME = "%(name)s"
    VERSION = "1.0.0"
    DESCRIPTION = "%(display)s"
    AUTHOR = "%(author)s"

    def __init__(self):
        super().__init__()
        self._status_item = None

    def on_activate(self):
        self.api.log("%(display)s 已激活")
        self.api.add_menu("工具/%(display)s/示例动作", self.hello,
                          shortcut=None)

%(point_code)s

    def on_deactivate(self):
        self.api.log("%(display)s 已停用")
        try:
            self.api.clear_diagnostics()
        except Exception:
            pass

    def hello(self):
        """示例动作：状态栏提示 + 弹窗"""
        self.api.show_status("%(display)s 可用", 2500, "success")
        self.api.show_notification(
            "%(display)s", "脚手架生成的示例动作")
''' % {
        "name": name,
        "display": display,
        "author": author,
        "point_code": point_code or "        # 尚未选择扩展点",
    }


def create_plugin(name, output_dir, display=None, author="unknown",
                  permissions=None, points=None, force=False):
    errors = []
    if not NAME_RE.match(name):
        errors.append("name 必须匹配 %s" % NAME_RE.pattern)
    permissions = permissions or ["editor_read"]
    bad = [p for p in permissions if p not in VALID_PERMS]
    if bad:
        errors.append("未知权限: %s（可用: %s）"
                      % (bad, ", ".join(sorted(VALID_PERMS))))
    points = points or ["settings"]
    bad_pts = [p for p in points if p not in VALID_POINTS]
    if bad_pts:
        errors.append("未知扩展点: %s（可用: %s）"
                      % (bad_pts, ", ".join(sorted(VALID_POINTS))))
    if errors:
        raise ValueError("；".join(errors))

    target = os.path.join(output_dir, name)
    if os.path.exists(target) and not force:
        raise FileExistsError("目录已存在（用 --force 覆盖）: %s" % target)
    os.makedirs(target, exist_ok=True)
    display = display or name

    manifest = build_manifest(name, display, author, permissions, points)
    with open(os.path.join(target, "plugin.json"), "w",
              encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(os.path.join(target, "__init__.py"), "w",
              encoding="utf-8", newline="\n") as f:
        f.write(build_code(name, display, author, permissions, points))
    return target


def main():
    ap = argparse.ArgumentParser(
        description="生成半成品插件骨架（可直接通过 conformance 清单契约）")
    ap.add_argument("--name", required=True, help="内部名称，[a-z][a-z0-9_]{2,30}")
    ap.add_argument("--display-name", default="", help="显示名称（默认同 name）")
    ap.add_argument("--author", default="unknown")
    ap.add_argument("--permissions", default="editor_read",
                    help="逗号分隔，如 editor_read,dialog")
    ap.add_argument("--points", default="settings",
                    help="逗号分隔扩展点: " + ",".join(sorted(VALID_POINTS)))
    ap.add_argument("--output", default=os.path.join(ROOT, "plugins"),
                    help="输出目录（默认仓库 plugins/）")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    perms = [p.strip() for p in args.permissions.split(",") if p.strip()]
    points = [p.strip() for p in args.points.split(",") if p.strip()]
    try:
        target = create_plugin(
            args.name, os.path.abspath(args.output),
            display=args.display_name or None,
            author=args.author, permissions=perms, points=points,
            force=args.force)
    except (ValueError, FileExistsError) as e:
        print("[错误] %s" % e)
        return 1
    print("[OK] 已生成: %s" % target)
    print("     下一步: python -m pytest tests/test_plugin_conformance.py -q")
    return 0


if __name__ == "__main__":
    sys.exit(main())
