# -*- coding: utf-8 -*-
"""插件沙箱阶段 A：静态审计报告。

python tools/plugin_sandbox_audit.py
输出：docs/plugin_sandbox_report.md + data/plugin_sandbox_report.json
"""

import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.plugin_guard import audit_all  # noqa: E402


def main():
    reports = audit_all()
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    io.open(
        os.path.join(ROOT, "data", "plugin_sandbox_report.json"),
        "w",
        encoding="utf-8",
        newline="\n",
    ).write(json.dumps(reports, ensure_ascii=False, indent=2))
    lines = ["# 插件沙箱阶段 A 审计报告", "", "| 插件 | 可信 | 高危 | 中危 |", "|---|---|---|---|"]
    high_total = 0
    for rep in reports:
        high = sum(1 for f in rep["findings"] if f["risk"] == "high" and not f["allowed"])
        med = sum(1 for f in rep["findings"] if f["risk"] == "medium" and not f["allowed"])
        high_total += high
        lines.append(
            "| %s | %s | %d | %d |" % (rep["plugin"], "✅" if rep["trusted"] else "—", high, med)
        )
    lines += ["", "## 明细（非可信插件的高危项）", ""]
    for rep in reports:
        bad = [f for f in rep["findings"] if f["risk"] == "high" and not f["allowed"]]
        for f in bad[:20]:
            lines.append(
                "- `%s` %s:%s %s `%s`"
                % (rep["plugin"], os.path.basename(f["file"]), f["line"], f["kind"], f["name"])
            )
    if high_total == 0:
        lines.append("- 无非可信插件高危发现（第一方插件均列入允许列表）。")
    io.open(
        os.path.join(ROOT, "docs", "plugin_sandbox_report.md"), "w", encoding="utf-8", newline="\n"
    ).write("\n".join(lines) + "\n")
    print(
        "[sandbox-a] plugins=%d high_untrusted=%d -> docs/plugin_sandbox_report.md"
        % (len(reports), high_total)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
