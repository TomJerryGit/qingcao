# -*- coding: utf-8 -*-
"""收集真实用户评分导出文件 → 社区聚合数据（v2.24）。

用法:
    python tools/collect_ratings.py submissions/*.json
    python tools/collect_ratings.py a.json b.json --out data/ratings_community.json

输入支持两种格式:
  1) 应用本地导出: {"version":1, "plugins": {name: {"stars": 1-5, "comment": ""}}}
  2) 已有聚合:     {"version":1, "plugins": {name: {"average": 4.5, "count": 2}}}
输出: {"version":1, "source":"community-submissions", "plugins": {name: {average,count,sources}}}
"""

import argparse
import io
import json
import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "ratings_community.json")


def merge(files):
    acc = {}
    sources = []
    for path in files:
        try:
            data = json.load(io.open(path, encoding="utf-8"))
        except Exception as e:
            print("[collect] 跳过无效文件 %s: %s" % (path, e))
            continue
        plugins = data.get("plugins") if isinstance(data, dict) else None
        if not isinstance(plugins, dict):
            continue
        source = os.path.basename(path)
        sources.append(source)
        for name, rec in plugins.items():
            if not isinstance(rec, dict):
                continue
            try:
                if "average" in rec:
                    avg = max(1.0, min(5.0, float(rec["average"])))
                    cnt = max(1, int(rec.get("count", 1)))
                else:
                    avg = max(1.0, min(5.0, float(rec.get("stars", 0))))
                    cnt = 1
            except Exception:
                continue
            cur = acc.setdefault(name, {"weighted": 0.0, "count": 0, "sources": []})
            cur["weighted"] += avg * cnt
            cur["count"] += cnt
            if source not in cur["sources"]:
                cur["sources"].append(source)
    plugins = {}
    for name, cur in acc.items():
        if cur["count"]:
            plugins[name] = {
                "average": round(cur["weighted"] / cur["count"], 2),
                "count": cur["count"],
                "sources": cur["sources"],
            }
    return plugins, sources


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    plugins, sources = merge(args.files)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    io.open(args.out, "w", encoding="utf-8", newline="\n").write(
        json.dumps(
            {
                "version": 1,
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source": "community-submissions",
                "plugins": plugins,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    print("[collect] 提交文件 %d，插件 %d 条 -> %s" % (len(sources), len(plugins), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
