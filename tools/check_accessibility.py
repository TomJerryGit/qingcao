# -*- coding: utf-8 -*-
"""无障碍检查（P2）：关键插件 UI 控件需有 tooltip/accessibleName。"""

import argparse
import io
import os
import sys


REQUIRES = {
    "ui/plugin_settings_dialog.py": ["setAccessibleName("],
    "ui/remote_ui_renderer.py": ["setAccessibleName("],
    "ui/debug_host_panel.py": ["setAccessibleName("],
}

CHECKS = {
    "ui/ai_host_panel.py": [
        "new_session_btn",
        "rename_btn",
        "delete_btn",
        "export_btn",
        "import_btn",
        "search_btn",
    ],
    "ui/plugin_store_card.py": ["fav_btn"],
    "ui/plugin_store.py": [
        "update_all_btn",
        "install_local_btn",
        "usage_btn",
        "compare_btn",
        "search_edit",
    ],
    "ui/debug_host_panel.py": ["stack_tree", "locals_tree"],
    "ui/plugin_usage_dialog.py": ["table"],
}


def check_file(path, widgets):
    try:
        lines = io.open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return ["缺少文件: %s" % path]
    issues = []
    for widget in widgets:
        idx = next(
            (i for i, line in enumerate(lines) if widget + " =" in line or widget + " = " in line),
            None,
        )
        if idx is None:
            issues.append("%s: 未找到 %s" % (path, widget))
            continue
        window = "\n".join(lines[idx : idx + 6])
        if "setToolTip" not in window and "setAccessibleName" not in window:
            issues.append("%s: %s 缺少 tooltip/accessibleName" % (path, widget))
    return issues


def run(root="."):
    issues = []
    for rel, widgets in CHECKS.items():
        issues.extend(check_file(os.path.join(root, rel), widgets))
    for rel, patterns in REQUIRES.items():
        try:
            text = io.open(os.path.join(root, rel), encoding="utf-8").read()
        except OSError:
            issues.append("缺少文件: %s" % rel)
            continue
        for pat in patterns:
            if pat not in text:
                issues.append("%s: 缺少 %s" % (rel, pat))
    return issues


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    issues = run(args.root)
    for issue in issues:
        print("[a11y] " + issue)
    print("[a11y] issues=%d" % len(issues))
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
