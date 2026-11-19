# -*- coding: utf-8 -*-
"""性能门禁：读取 perf_history.jsonl 最近窗口中位数，超阈值失败。"""

import argparse
import io
import json
import statistics
import sys


THRESHOLDS = {"mainwindow": 1.5, "plugins_fully_ready": 3.0, "open_50mb": 8.0}


def load(path):
    rows = []
    for line in io.open(path, encoding="utf-8", errors="ignore"):
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def evaluate(path, window=20):
    rows = load(path)
    results = [r.get("results") or {} for r in rows[-max(1, window) :]]
    report = []
    failed = []
    for metric, limit in THRESHOLDS.items():
        values = [float(r[metric]) for r in results if metric in r]
        if not values:
            report.append((metric, None, limit, "MISSING"))
            failed.append(metric)
            continue
        med = statistics.median(values)
        ok = med <= limit
        report.append((metric, med, limit, "OK" if ok else "FAIL"))
        if not ok:
            failed.append(metric)
    return report, failed


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", default="data/perf_history.jsonl")
    ap.add_argument("--window", type=int, default=20)
    args = ap.parse_args(argv)
    try:
        report, failed = evaluate(args.history, args.window)
    except OSError as e:
        print("[perf-gate] 无法读取历史: %s" % e)
        return 1
    for metric, med, limit, state in report:
        shown = "%.3fs" % med if med is not None else "-"
        print("[perf-gate] %-24s %8s / <= %.1fs  %s" % (metric, shown, limit, state))
    print("[perf-gate] %s" % ("FAIL " + ",".join(failed) if failed else "PASS"))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
