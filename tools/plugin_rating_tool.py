# -*- coding: utf-8 -*-
"""本地评分导入/导出 CLI（v2.20.x P2）

python tools/plugin_rating_tool.py --export ratings.json
python tools/plugin_rating_tool.py --import ratings.json [--replace]
python tools/plugin_rating_tool.py --stats
"""

import argparse
import sys

from ui.plugin_rating import LocalRatings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default="")
    ap.add_argument("--import", dest="import_path", default="")
    ap.add_argument("--replace", action="store_true", help="导入时覆盖而非合并")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()
    store = LocalRatings()
    if args.export:
        n = store.export_data(args.export)
        print("[rating] 已导出 %d 条 -> %s" % (n, args.export))
    if args.import_path:
        n = store.import_data(args.import_path, merge=not args.replace)
        print("[rating] 已导入 %d 条（%s）" % (n, "覆盖" if args.replace else "合并"))
    if args.stats:
        for name, rec in sorted(store.all().items()):
            print("  %-32s %d★ %s" % (name, rec.get("stars", 0), (rec.get("comment") or "")[:40]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
