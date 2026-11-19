# -*- coding: utf-8 -*-
"""Flaky 测试隔离清单管理（Sprint 4）。"""

import argparse
import io
import json
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "tests", "flaky_quarantine.json")


def load():
    try:
        data = json.load(io.open(PATH, encoding="utf-8"))
        return list(data.get("tests") or [])
    except Exception:
        return []


def save(items):
    io.open(PATH, "w", encoding="utf-8", newline="\n").write(
        json.dumps({"tests": sorted(set(items))}, ensure_ascii=False, indent=2)
    )


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", default="")
    ap.add_argument("--remove", default="")
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    items = load()
    if args.add:
        items.append(args.add)
        save(items)
    if args.remove:
        save([x for x in items if x != args.remove])
    if args.run:
        if not items:
            print("[flaky] 清单为空")
            return 0
        env = dict(os.environ)
        env["QINGCAO_RUN_FLAKY"] = "1"
        return subprocess.call([sys.executable, "-m", "pytest"] + items, cwd=ROOT, env=env)
    for item in load():
        print(item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
