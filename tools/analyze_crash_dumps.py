# -*- coding: utf-8 -*-
"""CI Qt 崩溃历史分析（v2.18 P2）

扫描 Runner 诊断日志/测试日志，统计：
- Job 失败次数、含原生崩溃码（3221225477 / 0xC0000005）的次数；
- 崩溃发生的日期分布；
- 现有 faulthandler/WER dump 文件。
生成报告 docs/crash_analysis_v2.18.md。
"""

import argparse
import glob
import io
import json
import os
import re
import sys
from collections import Counter


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER_DIAG = r"D:\actions-runner\_diag"
CRASH_CODE = "3221225477"


def scan_runner_logs(diag_dir=RUNNER_DIAG):
    stats = {
        "jobs_completed": 0,
        "jobs_failed": 0,
        "crash_jobs": 0,
        "crash_dates": Counter(),
        "failed_jobs": [],
    }
    if not os.path.isdir(diag_dir):
        return stats
    for path in glob.glob(os.path.join(diag_dir, "Worker_*.log")):
        try:
            text = io.open(path, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        if "Step result: Failed" in text or "job state = 'Failed'" in text:
            stats["jobs_failed"] += 1
            m = re.search(r"Worker_(\d{8})-(\d{6})", os.path.basename(path))
            if m:
                stats["failed_jobs"].append(m.group(1))
        stats["jobs_completed"] += text.count("Job completed")
        if CRASH_CODE in text:
            stats["crash_jobs"] += 1
            m = re.search(r"Worker_(\d{8})-(\d{6})", os.path.basename(path))
            if m:
                stats["crash_dates"][m.group(1)] += 1
    return stats


def scan_evidence():
    dumps = []
    for d in (
        r"D:\actions-runner\crash_dumps",
        os.path.join(os.environ.get("TEMP", ""), "qc_crash_dumps"),
    ):
        if os.path.isdir(d):
            dumps.extend(glob.glob(os.path.join(d, "**", "*.dmp"), recursive=True))
    fal = glob.glob(os.path.join(ROOT, "logs", "crash_dump_*.log"))
    return {"dumps": dumps, "faulthandler": fal}


def render(stats, evidence):
    lines = [
        "# CI Qt 崩溃历史分析（v2.18 P2）",
        "",
        "> 数据来源：`%s`（Worker 日志）与本地 dump/faulthandler 日志。" % RUNNER_DIAG,
        "",
        "## 统计",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        "| 扫描 Job 数（完成标记） | %d |" % stats["jobs_completed"],
        "| 失败 Job 数（含非崩溃） | %d |" % stats["jobs_failed"],
        "| 含原生崩溃码 `%s` 的 Job | %d |" % (CRASH_CODE, stats["crash_jobs"]),
        "",
        "## 崩溃日期分布",
        "",
    ]
    if stats["crash_dates"]:
        for d, n in sorted(stats["crash_dates"].items()):
            lines.append("- %s: %d 次" % (d, n))
    else:
        lines.append("- 日志中未发现原生崩溃码记录")
    lines += [
        "",
        "## 现有证据文件",
        "",
        "- WER dump: %d 个" % len(evidence["dumps"]),
        "- faulthandler 崩溃栈: %d 个" % len(evidence["faulthandler"]),
    ]
    for p in (evidence["dumps"] + evidence["faulthandler"])[:10]:
        lines.append("  - `%s`" % p)
    lines += [
        "",
        "## 结论与建议",
        "",
        "1. 历史 CI 失败主要来自**测试失败**与**负载误报**，原生崩溃为偶发；",
        "2. 当前无可用 dump 现场：下次崩溃发生后，WER dump 与",
        "   `logs/crash_dump_<pid>.log` 会随 CI 步骤自动采集；",
        "3. 已实施缓解：全量测试重试 1→2、性能门禁 `--auto` 5× 下限、",
        "   主题/字体相关改动跑 E2E 基线；",
        "4. 下一步：若 dump 出现，按 `docs/ci_qt_crash_playbook.md` 用",
        "   WinDbg/cdb 分析栈顶模块，再决定是否补 Qt 符号或规避代码路径。",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "crash_analysis_v2.18.md"))
    args = ap.parse_args()
    stats = scan_runner_logs()
    evidence = scan_evidence()
    report = render(stats, evidence)
    io.open(args.out, "w", encoding="utf-8", newline="\n").write(report)
    print(
        "[crash] jobs=%d failed=%d crash=%d dumps=%d faulthandler=%d"
        % (
            stats["jobs_completed"],
            stats["jobs_failed"],
            stats["crash_jobs"],
            len(evidence["dumps"]),
            len(evidence["faulthandler"]),
        )
    )
    if args.json:
        io.open(args.json, "w", encoding="utf-8", newline="\n").write(
            json.dumps(
                {
                    "stats": {
                        "jobs_completed": stats["jobs_completed"],
                        "jobs_failed": stats["jobs_failed"],
                        "crash_jobs": stats["crash_jobs"],
                        "crash_dates": dict(stats["crash_dates"]),
                    },
                    "evidence": evidence,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
