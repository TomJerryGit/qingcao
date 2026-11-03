# -*- coding: utf-8 -*-
"""性能趋势报告（v2.18 P2）

用法:
    python tools/bench_optimization.py --json data/perf_latest.json (省略 --check)
    python tools/perf_trend_report.py --record
    python tools/perf_trend_report.py --report

历史文件默认 data/perf_history.jsonl，可用 QINGCAO_PERF_HISTORY 覆盖
（CI 建议指向 Runner 持久路径）。
"""

import argparse
import datetime
import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LATEST = os.path.join(ROOT, "data", "perf_latest.json")
DEFAULT_HISTORY = os.path.join(ROOT, "data", "perf_history.jsonl")


def history_path():
    return os.environ.get("QINGCAO_PERF_HISTORY") or DEFAULT_HISTORY


def record(latest_path=LATEST):
    if not os.path.isfile(latest_path):
        return (False, "缺少 latest 结果: %s" % latest_path)
    data = json.load(io.open(latest_path, encoding="utf-8"))
    results = data.get("results") or data
    item = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "commit": os.environ.get("GITHUB_SHA", ""),
        "results": results,
    }
    path = history_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return (True, path)


def load_history():
    path = history_path()
    rows = []
    if os.path.isfile(path):
        for line in io.open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def render(rows, thresholds=None):
    thresholds = thresholds or {}
    lines = [
        "# 性能趋势报告（v2.18）",
        "",
        "> 数据：`%s`（%d 次记录）" % (history_path(), len(rows)),
        "",
    ]
    if not rows:
        lines.append("暂无历史记录。")
        return "\n".join(lines) + "\n"
    names = sorted({k for r in rows for k in (r.get("results") or {})})
    lines += ["| 指标 | 最新 | 历史最小 | 历史最大 | 阈值 | 趋势 |", "|---|---|---|---|---|---|"]
    for name in names:
        vals = [
            r["results"][name]
            for r in rows
            if isinstance(r.get("results"), dict)
            and isinstance(r["results"].get(name), (int, float))
        ]
        if not vals:
            continue
        first, last = vals[0], vals[-1]
        trend = "→"
        if last > first * 1.15:
            trend = "↑ 劣化"
        elif last < first * 0.85:
            trend = "↓ 改善"
        thr = thresholds.get(name)
        lines.append(
            "| %s | %.3f | %.3f | %.3f | %s | %s |"
            % (name, last, min(vals), max(vals), ("%.2f" % thr) if thr else "-", trend)
        )
    lines += [
        "",
        "## 说明",
        "",
        "- 阈值来自 `tools/bench_optimization.py::THRESHOLDS`；",
        "- 趋势对比首末两次记录，±15% 内视为稳定；",
        "- CI 每次跑完性能门禁后自动记录（Runner 持久历史文件）。",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "perf_trend_report.md"))
    args = ap.parse_args()
    if args.record:
        ok, msg = record()
        print("[perf-trend] record:", msg)
    if args.report:
        try:
            from tools.bench_optimization import THRESHOLDS
        except Exception:
            THRESHOLDS = {}
        rows = load_history()
        io.open(args.out, "w", encoding="utf-8", newline="\n").write(render(rows, THRESHOLDS))
        print("[perf-trend] report:", args.out, "records:", len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
