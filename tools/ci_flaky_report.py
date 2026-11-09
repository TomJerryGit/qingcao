# -*- coding: utf-8 -*-
"""CI 原生崩溃 fallback 频率报告 + 阶段面包屑（v2.23 D5）

python tools/ci_flaky_report.py                 # 生成报告
python tools/ci_flaky_report.py --check --max-7d 3
"""

import argparse
import io
import json
import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(ROOT, "data", "ci_flaky_history.jsonl")
BREADCRUMB = os.path.join(ROOT, "data", "test_shards", "last_stage.json")
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


def load_breadcrumb(path=BREADCRUMB):
    try:
        return json.load(io.open(path, encoding="utf-8"))
    except Exception:
        return None


def count_recent(rows, days=7, now=None):
    now = now or time.time()
    cutoff = now - days * 86400
    return sum(1 for r in rows if float(r.get("ts", 0)) >= cutoff)


def should_fail(rows, max_7d=3, now=None):
    """发布/CI 门禁：最近 7 天 fallback 次数超过阈值则失败。"""
    return count_recent(rows, 7, now) > max_7d


def suspects(rows):
    """汇总历史记录中的可疑文件（localized/crash_files）。"""
    counts = {}
    for r in rows:
        for name in (r.get("localized") or []) + (r.get("crash_files") or []):
            counts[name] = counts.get(name, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def render(rows, breadcrumb=None, now=None):
    now = now or time.time()
    total = len(rows)
    last7 = count_recent(rows, 7, now)
    lines = [
        "# CI 原生崩溃 fallback 频率报告（v2.23 D5）",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        "| 累计触发 fallback | %d 次 |" % total,
        "| 最近 7 天 | %d 次 |" % last7,
        "| 最近 24 小时 | %d 次 |" % count_recent(rows, 1, now),
        "",
    ]
    if breadcrumb:
        lines += [
            "## 最近阶段面包屑",
            "",
            "| 时间 | 阶段 | 详情 |",
            "|---|---|---|",
            "| %s | %s | %s |"
            % (
                breadcrumb.get("iso", ""),
                breadcrumb.get("stage", ""),
                ", ".join(
                    "%s=%s" % (k, v)
                    for k, v in breadcrumb.items()
                    if k not in ("ts", "iso", "pid", "stage")
                )[:120],
            ),
            "",
        ]
    else:
        lines += ["## 最近阶段面包屑", "", "暂无 `data/test_shards/last_stage.json`。", ""]
    top = suspects(rows)
    lines += ["## 可疑文件 Top", ""]
    if top:
        lines += ["| 文件 | 次数 |", "|---|---|"]
        lines += ["| %s | %d |" % (name, cnt) for name, cnt in top[:10]]
    else:
        lines.append("暂无可疑文件记录。")
    lines += ["", "## 最近记录", ""]
    if rows:
        lines += ["| 时间 | 崩溃码 | 文件数 | 结果 |", "|---|---|---|---|"]
        for r in rows[-15:]:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(r.get("ts", 0))))
            lines.append(
                "| %s | %s | %s | %s |"
                % (
                    ts,
                    ",".join(str(c) for c in r.get("crash_codes", [])),
                    r.get("files", "?"),
                    r.get("result", ""),
                )
            )
    else:
        lines.append("暂无触发记录。")
    lines += [
        "",
        "## 决策建议",
        "",
        "- 7 天 ≤3 次：保持并行与 fallback；",
        "- 7 天 >3 次：降并行（`--shards 2 --no-parallel`）并优先修复可疑文件；",
        "- 任何真实失败不会被 fallback 放行（逐文件复跑仍会失败）。",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="超过阈值时退出 1")
    ap.add_argument("--max-7d", type=int, default=3)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    rows = load_history()
    crumb = load_breadcrumb()
    io.open(args.out, "w", encoding="utf-8", newline="\n").write(render(rows, crumb))
    last7 = count_recent(rows, 7)
    print("[ci-flaky] 累计=%d 近7天=%d -> %s" % (len(rows), last7, args.out))
    if crumb:
        print("[ci-flaky] 最近阶段:", crumb.get("stage"), crumb.get("iso"))
    if args.check and should_fail(rows, args.max_7d):
        print("[ci-flaky] FAIL: 近 7 天 %d 次 > 阈值 %d，建议降并行" % (last7, args.max_7d))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
