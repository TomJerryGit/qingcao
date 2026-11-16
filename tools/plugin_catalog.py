# -*- coding: utf-8 -*-
"""插件目录生成：plugins/*/plugin.json → docs/plugin_catalog.md。"""

import argparse
import glob
import io
import json
import os


def collect(root):
    rows = []
    for path in sorted(glob.glob(os.path.join(root, "*", "plugin.json"))):
        try:
            data = json.load(io.open(path, encoding="utf-8"))
        except Exception:
            continue
        rows.append(
            {
                "name": data.get("name") or os.path.basename(os.path.dirname(path)),
                "display": data.get("display_name") or data.get("name", ""),
                "version": data.get("version", ""),
                "category": data.get("category", ""),
                "permissions": data.get("permissions") or [],
                "sandbox": bool(data.get("sandbox")),
                "enabled": bool(data.get("enabled", True)),
                "description": data.get("description", ""),
            }
        )
    return sorted(rows, key=lambda r: (r["category"], r["name"]))


def render(rows, out):
    total = len(rows)
    sandbox = sum(1 for r in rows if r["sandbox"])
    disabled = sum(1 for r in rows if not r["enabled"])
    lines = [
        "# 插件目录",
        "",
        "- 插件总数：%d" % total,
        "- 沙箱插件：%d" % sandbox,
        "- 默认禁用：%d" % disabled,
        "",
        "| 插件 | 名称 | 版本 | 分类 | 权限 | 沙箱 | 启用 | 说明 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            "| `%s` | %s | %s | %s | %s | %s | %s | %s |"
            % (
                r["name"],
                r["display"],
                r["version"],
                r["category"],
                ", ".join(r["permissions"]) or "-",
                "✅" if r["sandbox"] else "—",
                "✅" if r["enabled"] else "—",
                r["description"][:50],
            )
        )
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    return total, sandbox


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="plugins")
    ap.add_argument("--out", default="docs/plugin_catalog.md")
    args = ap.parse_args(argv)
    rows = collect(args.root)
    total, sandbox = render(rows, args.out)
    print("[catalog] plugins=%d sandbox=%d -> %s" % (total, sandbox, args.out))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
