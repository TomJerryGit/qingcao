# -*- coding: utf-8 -*-
"""本地评分 → 静态 ratings.json 聚合（v2.23 P1-2，零服务端）。

python tools/build_ratings_aggregate.py
python tools/build_ratings_aggregate.py --out data/registry_github/ratings.json
"""

import argparse
import io
import json
import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "plugin_ratings.json")
OUT = os.path.join(ROOT, "data", "registry_github", "ratings.json")


def aggregate(local_path=SRC):
    data = {
        "version": 1,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "local-export",
        "plugins": {},
    }
    try:
        local = json.load(io.open(local_path, encoding="utf-8"))
    except Exception:
        local = {}
    for name, rec in (local.get("plugins") or {}).items():
        try:
            stars = max(1, min(5, int(rec.get("stars", 0))))
        except Exception:
            continue
        data["plugins"][name] = {"average": float(stars), "count": 1, "sources": ["local"]}
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    data = aggregate(args.src)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    io.open(args.out, "w", encoding="utf-8", newline="\n").write(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    )
    print("[ratings] 插件 %d 条 -> %s" % (len(data["plugins"]), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
