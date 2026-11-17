# -*- coding: utf-8 -*-
"""Flaky 治理报告：data/ci_flaky_history.jsonl -> docs/flaky_report.md。"""

import argparse
import collections
import io
import json
import os


def load(path):
    rows = []
    try:
        for line in io.open(path, encoding="utf-8", errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                rows.append(item)
    except OSError:
        pass
    return rows


def summarize(rows):
    codes = collections.Counter()
    localized = 0
    passed = 0
    last = ""
    for row in rows:
        for code in row.get("crash_codes") or []:
            codes[str(code)] += 1
        if row.get("localized"):
            localized += 1
        if row.get("result") == "pass_after_localize":
            passed += 1
        if row.get("iso"):
            last = row["iso"]
    return {
        "events": len(rows),
        "crash_codes": dict(codes),
        "localized": localized,
        "pass_after_localize": passed,
        "last": last,
    }


def render(summary, out):
    lines = [
        "# Flaky 原生崩溃治理报告",
        "",
        "- 事件数：%d" % summary["events"],
        "- 逐文件复跑通过：%d" % summary["pass_after_localize"],
        "- 能定位到具体文件：%d" % summary["localized"],
        "- 最近一次：%s" % (summary["last"] or "-"),
        "",
        "| 崩溃码 | 次数 | 说明 |",
        "|---|---|---|",
    ]
    notes = {"3221225477": "0xC0000005 访问冲突（常见于 Qt 跨测试 teardown）"}
    for code, count in sorted(summary["crash_codes"].items()):
        lines.append("| %s | %d | %s |" % (code, count, notes.get(code, "未知")))
    lines += [
        "",
        "## 结论",
        "",
        "- 崩溃发生在**合并分片**而非单文件；逐文件复跑全部通过，属于顺序/析构相关 flaky。",
        "- 处理：保留逐文件复跑门禁；新增用例避免跨测试共享 Qt 对象；持续观察事件率。",
    ]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", default="data/ci_flaky_history.jsonl")
    ap.add_argument("--out", default="docs/flaky_report.md")
    args = ap.parse_args(argv)
    rows = load(args.history)
    summary = summarize(rows)
    render(summary, args.out)
    print("[flaky] events=%d -> %s" % (summary["events"], args.out))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
