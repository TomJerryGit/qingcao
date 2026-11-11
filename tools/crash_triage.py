# -*- coding: utf-8 -*-
"""Qt/原生崩溃聚合：faulthandler 转储 + flaky 历史 → 归组报告。

python tools/crash_triage.py --report docs/crash_triage_report.md
python tools/crash_triage.py --json data/crash_triage.json
"""

import argparse
import glob
import io
import json
import os
import re
import sys
from collections import defaultdict


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_EXC_RE = re.compile(r"(Windows fatal exception: [^\n]+|Fatal Python error: [^\n]+)")
_FILE_RE = re.compile(r'File "([^"]+)", line (\d+) in (\S+)')


def _iter_text(path):
    try:
        return io.open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return ""


def collect_dumps(extra_dirs=None):
    """收集 faulthandler 日志：logs/crash_dump_*.log、data/crash.log、crashed_*.log。"""
    paths = []
    for pat in (
        os.path.join(ROOT, "logs", "crash_dump_*.log"),
        os.path.join(ROOT, "data", "crash.log"),
        os.path.join(ROOT, "data", "test_shards", "crashed_*.log"),
    ):
        paths.extend(glob.glob(pat))
    for d in extra_dirs or []:
        paths.extend(glob.glob(os.path.join(d, "*.log")))
    return sorted(set(paths))


def parse_dump(text, source=""):
    """从一个 faulthandler 文本提取 (异常类型, 顶层帧, 文件名)。"""
    exc = "unknown"
    m = _EXC_RE.search(text)
    if m:
        exc = m.group(1).strip()
    frames = _FILE_RE.findall(text)
    top = ""
    if frames:
        top = "%s:%s" % (os.path.basename(frames[0][0]), frames[0][2])
    return exc, top, source


def collect_flaky(path=None):
    path = path or os.path.join(ROOT, "data", "ci_flaky_history.jsonl")
    rows = []
    if not os.path.isfile(path):
        return rows
    for line in io.open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def aggregate(extra_dirs=None):
    groups = defaultdict(lambda: {"count": 0, "sources": [], "top_frames": ""})
    files = collect_dumps(extra_dirs)
    for p in files:
        exc, top, _ = parse_dump(_iter_text(p), p)
        key = "%s | %s" % (exc, top or "?")
        g = groups[key]
        g["count"] += 1
        g["sources"].append(os.path.basename(p))
        if not g["top_frames"]:
            g["top_frames"] = top
    flaky = collect_flaky()
    for row in flaky:
        name = str(row.get("file") or row.get("test") or "")
        if not name:
            continue
        key = "CI flaky | %s" % os.path.basename(name)
        g = groups[key]
        g["count"] += 1
        g["sources"].append("ci_flaky_history")
    return {
        "generated_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
        "dump_files": len(files),
        "flaky_rows": len(flaky),
        "groups": dict(sorted(groups.items(), key=lambda kv: -kv[1]["count"])),
    }


def render_markdown(data):
    lines = [
        "# 崩溃聚合报告（crash triage）",
        "",
        "- 生成时间：%s" % data["generated_at"],
        "- faulthandler/dump 文件：%d" % data["dump_files"],
        "- CI flaky 记录：%d" % data["flaky_rows"],
        "",
        "| 次数 | 签名 | 来源 |",
        "|---|---|---|",
    ]
    for key, g in data["groups"].items():
        lines.append(
            "| %d | %s | %s |" % (g["count"], key, ", ".join(sorted(set(g["sources"]))[:3]))
        )
    if not data["groups"]:
        lines.append("| 0 | （无崩溃记录） | - |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=os.path.join(ROOT, "docs", "crash_triage_report.md"))
    ap.add_argument("--json", default=os.path.join(ROOT, "data", "crash_triage.json"))
    ap.add_argument("--extra-dir", action="append", default=[])
    args = ap.parse_args(argv)
    data = aggregate(args.extra_dir)
    md = render_markdown(data)
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    io.open(args.report, "w", encoding="utf-8", newline="\n").write(md)
    os.makedirs(os.path.dirname(args.json), exist_ok=True)
    io.open(args.json, "w", encoding="utf-8", newline="\n").write(
        json.dumps(data, ensure_ascii=False, indent=2)
    )
    print(
        "[crash-triage] groups=%d dumps=%d flaky=%d -> %s"
        % (len(data["groups"]), data["dump_files"], data["flaky_rows"], args.report)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
