# -*- coding: utf-8 -*-
"""清理崩溃恢复草稿 / 陈旧备份（默认预览，--yes 才移动）

移动目标：data/_trash_<日期>/（可手动恢复）
"""
import argparse
import os
import shutil
import sys
from datetime import datetime


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS = ["backup/autosave", "backup/drafts", "data/crashes"]


def collect_targets():
    items = []
    for rel in TARGETS:
        path = os.path.join(ROOT, rel)
        if os.path.isdir(path):
            for name in os.listdir(path):
                items.append((rel, os.path.join(path, name)))
    return items


def main():
    ap = argparse.ArgumentParser(description="清理崩溃恢复草稿")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--trash")
    args = ap.parse_args()
    items = collect_targets()
    if not items:
        print("[clean] 没有需要清理的草稿")
        return 0
    for rel, path in items:
        print("  待清理: %s/%s" % (rel, os.path.basename(path)))
    if not args.yes:
        print("[clean] 仅预览；加 --yes 执行移动")
        return 0
    trash = args.trash or os.path.join(
        ROOT, "data", "_trash_%s" % datetime.now().strftime("%Y%m%d"))
    os.makedirs(trash, exist_ok=True)
    moved = 0
    for rel, path in items:
        try:
            shutil.move(path, os.path.join(trash, os.path.basename(path)))
            moved += 1
        except Exception as e:
            print("  移动失败:", path, e)
    print("[clean] 已移动 %d 项 -> %s" % (moved, trash))
    return 0


if __name__ == "__main__":
    sys.exit(main())