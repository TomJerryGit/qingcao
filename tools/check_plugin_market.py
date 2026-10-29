# -*- coding: utf-8 -*-
"""插件市场元数据校验：category/license/homepage/keywords"""
import glob
import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIRED = ("category", "license", "homepage", "keywords", "description")


def check():
    problems = []
    for mf in sorted(glob.glob(os.path.join(ROOT, "plugins", "*",
                                            "plugin.json"))):
        try:
            m = json.load(io.open(mf, encoding="utf-8"))
        except Exception as e:
            problems.append("%s: JSON 解析失败 %s" % (mf, e))
            continue
        name = m.get("name") or os.path.basename(os.path.dirname(mf))
        miss = [k for k in REQUIRED if k not in m]
        if miss:
            problems.append("%s: 缺少 %s" % (name, ",".join(miss)))
    return problems


def main():
    ap_strict = "--strict" in sys.argv
    problems = check()
    for p in problems:
        print("  [market]", p)
    print("[market] 检查 %d 个插件，问题 %d 项"
          % (len(glob.glob(os.path.join(ROOT, "plugins", "*",
                                        "plugin.json"))), len(problems)))
    return 1 if (ap_strict and problems) else 0


if __name__ == "__main__":
    sys.exit(main())
