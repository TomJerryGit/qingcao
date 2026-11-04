# -*- coding: utf-8 -*-
"""CI 原生崩溃 fallback 频率报告（v2.20.x P2）

    python tools/ci_flaky_report.py
读取 data/ci_flaky_history.jsonl，输出频率与决策建议。
"""

import io
import json
import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(ROOT, "data", "ci_flaky_history.jsonl")
OUT = os.path.join(ROOT, "docs", "ci_flaky_report.md")


def load_history(path=HIST):
    rows = []
    if os.path.isfile(path):
        for line in io.open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def render(rows):
    total = len(rows)
    last7 = [r for r in rows if time.time() - float(r.get("ts", 0)) <= 7 * 86400]
    lines = [
        "# CI 原生崩溃 fallback 频率报告（v2.20.x）",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        "| 累计触发 fallback | %d 次 |" % total,
        "| 最近 7 天 | %d 次 |" % len(last7),
        "",
    ]
    if not rows:
        lines += ["暂无触发记录：CI 全量分片均一次通过（或新代码尚未遇到原生崩溃）。", ""]
    else:
        lines += ["| 时间 | 崩溃码 | 文件数 |", "|---|---|---|"]
        for r in rows[-20:]:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(r.get("ts", 0))))
            lines.append(
                "| %s | %s | %s |"
                % (ts, ",".join(str(c) for c in r.get("crash_codes", [])), r.get("files", "?"))
            )
        lines.append("")
    lines += [
        "## 决策建议",
        "",
        "- 触发 ≤1 次/3 天：保持并行与 fallback；",
        "- 触发 ≥2 次/3 天：改为 `--shards 2` 或对高发片禁用 parallel；",
        "- 任何真实失败不会被 fallback 放行（逐文件复跑仍会失败）。",
        "",
    ]
    return "\n".join(lines)


def main():
    rows = load_history()
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(render(rows))
    print("[ci-flaky] 记录 %d 条 -> %s" % (len(rows), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
