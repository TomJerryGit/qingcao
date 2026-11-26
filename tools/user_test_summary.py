# -*- coding: utf-8 -*-
"""用户测试 CSV 汇总：完成率、用时、P0/P1、回访意向。"""

import argparse
import csv
import io
import os
import statistics
import sys


TASKS = [
    ("task1_install", "安装启动"),
    ("task2_run", "打开并运行"),
    ("task3_save", "修改保存"),
    ("task4_search", "全局搜索"),
    ("task5_theme", "切换主题"),
    ("task6_reopen", "关闭重开"),
]


def load(path):
    rows = []
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("user_id") or "").strip():
                rows.append(row)
    return rows


def _done(value):
    v = (value or "").strip().lower()
    if not v:
        return False
    return not any(x in v for x in ("未完成", "失败", "no", "false", "0"))


def summarize(rows):
    total = len(rows)
    report = {"total": total, "tasks": {}, "p0": 0, "p1": 0, "would_use": 0, "times": []}
    for key, label in TASKS:
        done = sum(1 for r in rows if _done(r.get(key)))
        report["tasks"][label] = (done, total)
    for r in rows:
        sev = (r.get("severity") or "").upper()
        if "P0" in sev:
            report["p0"] += 1
        if "P1" in sev:
            report["p1"] += 1
        if (r.get("would_use_again") or "").strip().lower() in ("yes", "是", "y", "1"):
            report["would_use"] += 1
        try:
            report["times"].append(float(r.get("total_time_sec") or 0))
        except ValueError:
            pass
    return report


def render(report, version=""):
    lines = [
        "# 用户测试汇总",
        "",
        "- 版本：%s" % (version or "未知"),
        "- 有效样本：%d" % report["total"],
        "",
    ]
    lines += ["## 完成率", "", "| 任务 | 完成/总数 | 完成率 |", "|---|---:|---:|"]
    for label, (done, total) in report["tasks"].items():
        rate = (done / total * 100) if total else 0
        lines.append("| %s | %d/%d | %.0f%% |" % (label, done, total, rate))
    times = [t for t in report["times"] if t > 0]
    lines += ["", "## 指标", ""]
    lines.append("- P0 阻断：%d" % report["p0"])
    lines.append("- P1 困难：%d" % report["p1"])
    lines.append("- 愿意继续使用：%d/%d" % (report["would_use"], report["total"]))
    if times:
        lines.append("- 平均用时：%.0f 秒" % statistics.mean(times))
    lines += ["", "## 结论", "", "- [ ] 只修 P0", "- [ ] 更新下一版计划", ""]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="docs/user_test_package/05_record_template.csv")
    ap.add_argument("--out", default="docs/user_test_summary.md")
    ap.add_argument("--version", default="")
    args = ap.parse_args(argv)
    if not os.path.isfile(args.csv):
        print("[user-test] 缺少 CSV: %s" % args.csv)
        return 2
    report = summarize(load(args.csv))
    text = render(report, args.version)
    io.open(args.out, "w", encoding="utf-8", newline="\n").write(text + "\n")
    print("[user-test] -> %s (%d 样本)" % (args.out, report["total"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
