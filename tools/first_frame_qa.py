# -*- coding: utf-8 -*-
"""真机首帧 QA（v2.25 阶段 3.5）：多次运行 measure_first_paint 并统计。

python tools/first_frame_qa.py --runs 5
输出：data/first_frame_qa.json + docs/first_frame_qa_v2.25.md
"""

import argparse
import json
import os
import re
import statistics
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEASURE = os.path.join(ROOT, "tools", "measure_first_paint.py")
OUT_MD = os.path.join(ROOT, "docs", "first_frame_qa_v2.25.md")
OUT_JSON = os.path.join(ROOT, "data", "first_frame_qa.json")
_RE = re.compile(r"\[paint\] MainWindow ([0-9.]+)s 首帧 ([0-9.]+)s paint500=(\d+) polish500=(\d+)")
THRESHOLD_P95 = 0.8


def run_once():
    env = dict(os.environ)
    env.pop("QT_QPA_PLATFORM", None)  # 真机 Windows 平台
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, MEASURE],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        env=env,
        timeout=180,
        cwd=ROOT,
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    m = _RE.search(text)
    if not m:
        raise RuntimeError("未解析到 [paint] 输出: %s" % text[-300:])
    return {
        "mainwindow": float(m.group(1)),
        "first_paint": float(m.group(2)),
        "paint500": int(m.group(3)),
        "polish500": int(m.group(4)),
    }


def p95(values):
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))
    return ordered[idx]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    args = ap.parse_args(argv)
    samples = []
    for i in range(args.runs):
        sample = run_once()
        samples.append(sample)
        print(
            "[qa] run%d first_paint=%.3fs mainwindow=%.3fs"
            % (i + 1, sample["first_paint"], sample["mainwindow"])
        )
    first = [s["first_paint"] for s in samples]
    build = [s["mainwindow"] for s in samples]
    summary = {
        "runs": args.runs,
        "first_paint_median": round(statistics.median(first), 4),
        "first_paint_p95": round(p95(first), 4),
        "first_paint_min": round(min(first), 4),
        "first_paint_max": round(max(first), 4),
        "mainwindow_median": round(statistics.median(build), 4),
        "threshold_p95": THRESHOLD_P95,
        "pass": p95(first) < THRESHOLD_P95,
        "samples": samples,
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    md = [
        "# 真机首帧 QA（v2.25 阶段 3.5）",
        "",
        "- 样本数：%d（Windows 平台，非 offscreen）" % args.runs,
        "- 首帧中位数：**%.3fs**" % summary["first_paint_median"],
        "- 首帧 P95：**%.3fs**（阈值 < %.1fs）" % (summary["first_paint_p95"], THRESHOLD_P95),
        "- MainWindow 构造中位数：%.3fs" % summary["mainwindow_median"],
        "- 结论：%s" % ("PASS" if summary["pass"] else "未达标（记录环境波动，需复测）"),
        "",
        "## 原始样本",
        "",
    ]
    for i, s in enumerate(samples):
        md.append(
            "- run%d：first_paint=%.3fs，mainwindow=%.3fs，paint500=%d，polish500=%d"
            % (i + 1, s["first_paint"], s["mainwindow"], s["paint500"], s["polish500"])
        )
    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(md) + "\n")
    print(
        "[qa] P95=%.3fs -> %s（%s）"
        % (summary["first_paint_p95"], "PASS" if summary["pass"] else "FAIL", OUT_MD)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
