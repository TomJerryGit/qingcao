# -*- coding: utf-8 -*-
"""插件使用统计报告（本地）→ docs/plugin_usage_report.md。"""

import argparse
import io
import os
import time


def render(snapshot, out):
    rows = sorted(snapshot.items(), key=lambda kv: int(kv[1].get("activations") or 0), reverse=True)
    lines = [
        "# 插件使用统计（本地）",
        "",
        "- 插件数：%d" % len(rows),
        "- 采集内容：插件名/激活次数/时间戳（不含路径或文本）",
        "",
        "| 插件 | 激活 | 停用 | 最近使用 |",
        "|---|---|---|---|",
    ]
    for name, rec in rows:
        last = rec.get("last_activate") or rec.get("last_activation") or 0
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(last)) if last else "-"
        lines.append(
            "| %s | %d | %d | %s |"
            % (name, int(rec.get("activations") or 0), int(rec.get("deactivations") or 0), when)
        )
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/plugin_usage_report.md")
    args = ap.parse_args(argv)
    from core.plugin_usage import snapshot

    render(snapshot(), args.out)
    print("[usage] -> %s" % args.out)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
