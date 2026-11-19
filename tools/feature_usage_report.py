# -*- coding: utf-8 -*-
"""功能使用 Top/低使用清单 → docs/feature_usage_report.md"""

import io
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.feature_usage import low, snapshot, top  # noqa: E402


def main():
    lines = ["# 功能使用统计（本地，匿名）", ""]
    lines += [
        "- 已记录动作：%d" % len(snapshot()),
        "",
        "## Top 使用",
        "",
        "| 功能 | 次数 |",
        "|---|---|",
    ]
    for name, rec in top(20):
        lines.append("| %s | %d |" % (name, int(rec.get("count") or 0)))
    lines += ["", "## 低使用（候选削减）", "", "| 功能 | 次数 |", "|---|---|"]
    for name, rec in low(20):
        lines.append("| %s | %d |" % (name, int(rec.get("count") or 0)))
    out = os.path.join(ROOT, "docs", "feature_usage_report.md")
    io.open(out, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print("[feature-usage] -> %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
