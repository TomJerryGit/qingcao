# -*- coding: utf-8 -*-
"""本地反馈报告（v2.21.x）

汇总 data/feedback/feedback.jsonl + 本机客观数据（崩溃/运行时日志/mmap/flaky），
生成 docs/user_feedback_report.md。
    python tools/feedback_report.py
"""

import importlib.util
import io
import json
import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEEDBACK = os.path.join(ROOT, "data", "feedback", "feedback.jsonl")
OUT = os.path.join(ROOT, "docs", "user_feedback_report.md")


def load_feedback(path=FEEDBACK):
    rows = []
    if os.path.isfile(path):
        for line in io.open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


def _load_module(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def local_evidence():
    ev = {}
    try:
        mod = _load_module("qc_mmap_dec2", "tools/mmap_data_decision.py")
        events = mod.load_events()
        ev["mmap"] = mod.summarize(events)
    except Exception as e:
        ev["mmap"] = {"error": str(e)}
    crash_dir = os.path.join(ROOT, "logs")
    crash_files = []
    if os.path.isdir(crash_dir):
        crash_files = [f for f in os.listdir(crash_dir) if f.startswith("crash")]
    ev["crash_logs"] = len(crash_files)
    hist = os.path.join(ROOT, "data", "ci_flaky_history.jsonl")
    ev["flaky"] = 0
    if os.path.isfile(hist):
        ev["flaky"] = sum(1 for _ in io.open(hist, encoding="utf-8"))
    return ev


def render(rows, ev, generated=None):
    lines = [
        "# 用户反馈报告（v2.21.2 体验基线）",
        "",
        "> 生成时间：%s" % (generated or time.strftime("%Y-%m-%d %H:%M")),
        "> 数据来源：本机反馈 JSONL + 崩溃/运行日志 + mmap/flaky 记录；不上传。",
        "",
    ]
    lines += ["## 一、已收集反馈", ""]
    if not rows:
        lines += ["暂无本地反馈记录（data/feedback/feedback.jsonl）。", ""]
    else:
        lines += ["| 时间 | 类型 | 内容摘要 |", "|---|---|---|"]
        for r in rows[-30:]:
            lines.append(
                "| %s | %s | %s |"
                % (
                    r.get("iso", ""),
                    r.get("category", ""),
                    str(r.get("text", ""))[:60].replace("|", "\\|"),
                )
            )
        lines.append("")
    lines += [
        "## 二、客观数据",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        "| 崩溃日志文件数 | %s |" % ev.get("crash_logs", 0),
        "| CI flaky 记录 | %s |" % ev.get("flaky", 0),
    ]
    mm = ev.get("mmap", {})
    if "all" in mm:
        lines.append(
            "| mmap 事件（全部/真实） | %d / %d |" % (mm["all"]["total"], mm["real"]["total"])
        )
    lines += [
        "",
        "## 三、优先级建议（规则）",
        "",
        "- 问题反馈（Bug）→ 优先修复；",
        "- 功能建议 → 按影响面/成本排序；",
        "- 稳定性数据（崩溃/flaky）异常 → 优先稳定性专项；",
        "- 暂无真实反馈时：先做体验回访与冒烟测试，不盲目开工。",
        "",
    ]
    return "\n".join(lines)


def main():
    rows = load_feedback()
    ev = local_evidence()
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(render(rows, ev))
    print("[feedback] 反馈 %d 条 -> %s" % (len(rows), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
