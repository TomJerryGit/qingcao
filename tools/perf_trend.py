# -*- coding: utf-8 -*-
"""性能趋势：perf_history.jsonl 最近 vs 上期，输出 docs/perf_trend.md。"""

import argparse
import io
import json
import os
import statistics


METRICS = (
    ("mainwindow", "启动 MainWindow", 1.5),
    ("plugin_ready_after", "插件就绪", 3.0),
    ("open_50mb", "打开 50MB", 8.0),
    ("theme_reapply", "主题重复应用", 0.5),
)


def load(path):
    rows = []
    for line in io.open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item.get("results"), dict):
            rows.append(item)
    rows.sort(key=lambda r: str(r.get("ts", "")))
    return rows


def _median(rows, key):
    vals = [r["results"][key] for r in rows if isinstance(r["results"].get(key), (int, float))]
    return statistics.median(vals) if vals else None


def summarize(rows, window=20):
    recent = rows[-window:]
    previous = rows[-2 * window : -window]
    out = []
    for key, label, limit in METRICS:
        cur = _median(recent, key)
        prev = _median(previous, key)
        delta = ((cur - prev) / prev * 100.0) if (cur is not None and prev) else None
        out.append(
            {
                "key": key,
                "label": label,
                "current": cur,
                "previous": prev,
                "delta_pct": delta,
                "limit": limit,
            }
        )
    return out


def render(rows, stats, out):
    lines = [
        "# 性能趋势",
        "",
        "- 样本：%d 条 · 最近窗口：20 · 对比窗口：前 20" % len(rows),
        "",
        "| 指标 | 最近中位数 | 上期中位数 | 变化 | 上限 | 状态 |",
        "|---|---|---|---|---|---|",
    ]
    for s in stats:
        cur = "-" if s["current"] is None else "%.4fs" % s["current"]
        prev = "-" if s["previous"] is None else "%.4fs" % s["previous"]
        delta = "-" if s["delta_pct"] is None else "%+.1f%%" % s["delta_pct"]
        status = "—"
        if s["current"] is not None:
            status = "✅" if s["current"] <= s["limit"] else "⚠️ 超限"
        lines.append(
            "| %s | %s | %s | %s | %.2fs | %s |"
            % (s["label"], cur, prev, delta, s["limit"], status)
        )
    if rows:
        lines += ["", "最新样本：%s" % rows[-1].get("ts", "")]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", default="data/perf_history.jsonl")
    ap.add_argument("--out", default="docs/perf_trend.md")
    args = ap.parse_args(argv)
    rows = load(args.history)
    stats = summarize(rows)
    render(rows, stats, args.out)
    print("[perf-trend] rows=%d -> %s" % (len(rows), args.out))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
