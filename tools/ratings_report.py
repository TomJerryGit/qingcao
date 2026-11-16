# -*- coding: utf-8 -*-
"""插件评分报告（P4 评分运营）：本地评分 + 社区评分汇总。"""

import argparse
import io
import json
import os


def load_local(path):
    try:
        data = json.load(io.open(path, encoding="utf-8"))
    except Exception:
        return {}
    return data.get("plugins") or {}


def _community_entry(value):
    if isinstance(value, dict):
        count = value.get("count") or value.get("votes") or 0
        avg = value.get("average") or value.get("avg") or 0
        return int(count), float(avg)
    if isinstance(value, (int, float)):
        return 1, float(value)
    return 0, 0.0


def load_community(path):
    try:
        data = json.load(io.open(path, encoding="utf-8"))
    except Exception:
        return {}
    raw = data.get("plugins") or {}
    return {k: _community_entry(v) for k, v in raw.items()}


def is_seed(record):
    """维护者种子评分：comment 含“种子/seed”。"""
    comment = ""
    if isinstance(record, dict):
        comment = str(record.get("comment") or "").lower()
    return ("种子" in comment) or ("seed" in comment)


def build_rows(local, community):
    names = sorted(set(local) | set(community))
    rows = []
    for name in names:
        local_stars = 0
        if isinstance(local.get(name), dict):
            local_stars = int(local[name].get("stars") or 0)
        entry = community.get(name, (0, 0.0))
        if isinstance(entry, (dict, int, float)):
            count, avg = _community_entry(entry)
        else:
            count, avg = entry
        rows.append(
            {
                "plugin": name,
                "local_stars": local_stars,
                "seed": bool(is_seed(local.get(name))),
                "community_count": count,
                "community_avg": round(avg, 2),
            }
        )
    return rows


def render(rows, out):
    total_local = sum(1 for r in rows if r["local_stars"] > 0)
    seeds = sum(1 for r in rows if r.get("seed"))
    real_local = total_local - seeds
    total_community = sum(r["community_count"] for r in rows)
    lines = [
        "# 插件评分报告",
        "",
        "- 有本地评分的插件：%d（维护者种子 %d，真实本地 %d）" % (total_local, seeds, real_local),
        "- 社区评分样本：%d" % total_community,
        "",
        "| 插件 | 本地星级 | 来源 | 社区人数 | 社区均分 |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            "| %s | %s | %s | %d | %.2f |"
            % (
                r["plugin"],
                r["local_stars"] or "-",
                "种子" if r.get("seed") else "用户",
                r["community_count"],
                r["community_avg"],
            )
        )
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    return total_local, total_community


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", default="data/plugin_ratings.json")
    ap.add_argument("--community", default="data/registry_github/ratings.json")
    ap.add_argument("--out", default="docs/ratings_report.md")
    args = ap.parse_args(argv)
    rows = build_rows(load_local(args.local), load_community(args.community))
    local, community = render(rows, args.out)
    print(
        "[ratings] plugins=%d local=%d community=%d -> %s" % (len(rows), local, community, args.out)
    )
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
