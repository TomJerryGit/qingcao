# -*- coding: utf-8 -*-
"""i18n 英文 QA：术语统一检查（v2.20）

python tools/i18n_qa.py            # 报告
python tools/i18n_qa.py --check    # 违规时退出 1（CI）
"""

import argparse
import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EN = os.path.join(ROOT, "locale", "en_US", "strings.json")
OUT = os.path.join(ROOT, "docs", "i18n_qa_report.md")

# 中文关键词 -> 应使用的英文术语（值包含该术语）
RULE = {
    "插件市场": "Plugin Market",
    "首选项": "Preferences",
    "沙箱": "Sandbox",
    "大纲": "Outline",
    "主题": "Theme",
    "快捷键方案": "Shortcut Profile",
    "快捷键": "Shortcut",
    "工作区": "Workspace",
    "状态栏": "Status Bar",
    "工具栏": "Toolbar",
    "高对比度": "High Contrast",
    "无障碍": "Accessibility",
    "编辑器": "Editor",
    "面板": "Panel",
    "标签页": "Tab",
}
# 常见错误变体 -> 正确写法
VARIANTS = {
    "Marketplace": "Market",
    "Preference ": "Preferences ",
    "Shortcuts ": "Shortcut ",
    "Sandboxed": "Sandbox",
}


def check(en):
    violations = []
    for zh, value in en.items():
        if not isinstance(value, str):
            continue
        for key, term in RULE.items():
            if key not in zh:
                continue
            if term.lower() in value.lower():
                continue
            # 例外：命令面板 → Palette；面板 → Pane/Window
            if key == "面板" and any(
                    e in value.lower() for e in ("palette", "pane", "window")):
                continue
            violations.append(("术语", zh, value, term))
        for bad, good in VARIANTS.items():
            if bad in value:
                violations.append(("变体", zh, value, good))
    return violations


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    en = json.load(io.open(EN, encoding="utf-8"))
    violations = check(en)
    lines = [
        "# i18n 英文 QA 报告（v2.20）",
        "",
        "| 类型 | 中文 | 英文 | 期望 |",
        "|---|---|---|---|",
    ]
    for kind, zh, value, expect in violations[:200]:
        lines.append("| %s | %s | %s | %s |" % (kind, zh[:24], value[:48], expect))
    lines += ["", "违规条目：%d" % len(violations), ""]
    io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    print("[i18n-qa] 违规条目: %d -> %s" % (len(violations), OUT))
    if args.check and violations:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
