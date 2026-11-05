# -*- coding: utf-8 -*-
"""mmap 数据决策（v2.21 P2）"""

import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(ROOT, "data", "mmap_eval.jsonl")
OUT = os.path.join(ROOT, "docs", "mmap_data_decision.md")


def load_events(path=HIST):
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


def is_synthetic(e):
    t = str(e.get("target", "")).lower()
    return "pytest" in t or "\\temp\\" in t or "/tmp/" in t


def summarize(events):
    real = [e for e in events if e.get("target") and not is_synthetic(e)]
    unknown = [e for e in events if not e.get("target") and not is_synthetic(e)]

    def s(rows):
        ev = [r.get("event") for r in rows]
        eligible = sum(1 for x in ev if x in ("success", "fallback", "noop"))
        fb = ev.count("fallback")
        return {
            "total": len(rows),
            "eligible": eligible,
            "success": ev.count("success"),
            "fallback": fb,
            "noop": ev.count("noop"),
            "ineligible": ev.count("ineligible"),
            "recovery": ev.count("recovery"),
            "fallback_rate": (fb / eligible * 100) if eligible else 0.0,
        }

    return {
        "all": s(events),
        "real": s(real),
        "synthetic": s([e for e in events if is_synthetic(e)]),
        "unknown": s(unknown),
    }


def decide(stats):
    r = stats["real"]
    if r["eligible"] < 20:
        return "数据不足：继续默认关闭（灰度），继续收集真实保存数据"
    if r["fallback_rate"] < 5 and r["success"] > 0:
        return "建议 v2.22 默认开启（保留设置页回退开关）"
    return "回退率偏高：保持默认关闭并排查失败原因"


def render(stats, decision):
    lines = [
        "# mmap 默认开启：数据决策报告（v2.21 P2）",
        "",
        "| 指标 | 全部 | 真实 | 测试 | 未知 |",
        "|---|---|---|---|---|",
    ]
    for k in ("total", "eligible", "success", "fallback", "noop", "ineligible", "recovery"):
        lines.append(
            "| %s | %d | %d | %d | %d |"
            % (
                k,
                stats["all"][k],
                stats["real"][k],
                stats["synthetic"][k],
                stats["unknown"][k],
            )
        )
    lines.append(
        "| fallback_rate | %.2f%% | %.2f%% | %.2f%% | %.2f%% |"
        % (
            stats["all"]["fallback_rate"],
            stats["real"]["fallback_rate"],
            stats["synthetic"]["fallback_rate"],
            stats["unknown"]["fallback_rate"],
        )
    )
    lines += [
        "",
        "## 决策",
        "",
        "**%s**" % decision,
        "",
        "> 未知=无 target 字段的事件（旧埋点无法区分真实/测试）；"
        "> 门槛：真实 eligible≥20 且回退率<5%。",
        "",
    ]
    return "\n".join(lines)


def main():
    events = load_events()
    stats = summarize(events)
    decision = decide(stats)
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(render(stats, decision))
    print(
        "[mmap-data] 全部=%d 真实=%d 测试=%d"
        % (stats["all"]["total"], stats["real"]["total"], stats["synthetic"]["total"])
    )
    print("[mmap-data] 决策:", decision)
    return 0


if __name__ == "__main__":
    sys.exit(main())
