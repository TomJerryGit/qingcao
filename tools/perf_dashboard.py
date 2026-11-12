# -*- coding: utf-8 -*-
"""性能看板：perf_history.jsonl → 单文件 HTML（内联 SVG，零依赖）。

python tools/perf_dashboard.py
python tools/perf_dashboard.py --extra-history D:\actions-runner\perf_history.jsonl --limit 120
"""

import argparse
import html
import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METRICS = (
    ("mainwindow", "启动 MainWindow (s)", 1.5),
    ("plugin_ready_after", "插件就绪 (s)", 3.0),
    ("open_50mb", "打开 50MB (s)", 8.0),
    ("theme_reapply", "主题重复应用 (s)", 0.5),
)


def load_history(path):
    rows = []
    if not path or not os.path.isfile(path):
        return rows
    for line in io.open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict) and isinstance(item.get("results"), dict):
            rows.append(item)
    return rows


def _svg(series, threshold, width=640, height=140):
    values = [v for v in series if isinstance(v, (int, float))]
    if not values:
        return "<p>无数据</p>"
    maxv = max(max(values), threshold or 0) * 1.15 or 1.0
    pad = 24
    n = max(1, len(values) - 1)
    pts = []
    for i, v in enumerate(values):
        x = pad + (width - 2 * pad) * i / n
        y = height - pad - (height - 2 * pad) * (v / maxv)
        pts.append("%.1f,%.1f" % (x, y))
    ty = height - pad - (height - 2 * pad) * ((threshold or 0) / maxv)
    return (
        '<svg viewBox="0 0 %d %d" width="100%%" height="%d" role="img">'
        '<rect x="0" y="0" width="%d" height="%d" fill="#1e1e1e"/>'
        '<polyline fill="none" stroke="#61afef" stroke-width="2" points="%s"/>'
        '<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#e06c75" '
        'stroke-dasharray="4,3"/></svg>'
        % (width, height, height, width, height, " ".join(pts), pad, ty, width - pad, ty)
    )


def build_html(rows, limit=120):
    rows = rows[-limit:]
    latest = rows[-1] if rows else {}
    parts = [
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>",
        "<title>青草编辑器性能看板</title><style>",
        "body{background:#1e1e1e;color:#d4d4d4;font-family:Segoe UI,sans-serif;margin:24px}",
        "h1{color:#7ec850}h2{color:#61afef;margin-top:28px}",
        "table{border-collapse:collapse;margin-top:8px}",
        "td,th{border:1px solid #3c3c3c;padding:6px 10px;font-size:13px}",
        ".meta{color:#888;font-size:12px}",
        "</style></head><body>",
        "<h1>青草编辑器性能看板</h1>",
        "<p class='meta'>样本 %d 条 · 最新 %s · 阈值线为红色虚线（硬上限）</p>"
        % (len(rows), html.escape(str(latest.get("ts", "-")))),
    ]
    if not rows:
        parts.append("<p>暂无性能历史数据。</p>")
    else:
        for key, label, threshold in METRICS:
            series = [r["results"].get(key) for r in rows]
            parts.append("<h2>%s</h2>" % html.escape(label))
            parts.append(_svg(series, threshold))
        last = latest.get("results", {})
        parts.append("<h2>最新指标</h2><table><tr><th>指标</th><th>值</th></tr>")
        for key, label, _ in METRICS:
            parts.append(
                "<tr><td>%s</td><td>%s</td></tr>"
                % (html.escape(label), html.escape(str(last.get(key, "-"))))
            )
        parts.append("</table>")
    parts.append(
        "<p class='meta'>由 tools/perf_dashboard.py 生成；数据源 data/perf_history.jsonl。</p>"
    )
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", default=os.path.join(ROOT, "data", "perf_history.jsonl"))
    ap.add_argument("--extra-history", default="")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "perf_dashboard.html"))
    ap.add_argument("--limit", type=int, default=120)
    args = ap.parse_args(argv)
    rows = load_history(args.history)
    if args.extra_history:
        rows.extend(load_history(args.extra_history))
    rows.sort(key=lambda r: str(r.get("ts", "")))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    io.open(args.out, "w", encoding="utf-8", newline="\n").write(build_html(rows, args.limit))
    print("[perf-dashboard] rows=%d -> %s" % (len(rows), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
