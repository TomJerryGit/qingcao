# -*- coding: utf-8 -*-
"""对比内置主题定义 vs themes/*.json，找出缺失/不一致的键"""
import io
import json
import os
import re
import sys


sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\QingCaoEditor")
os.chdir(r"D:\QingCaoEditor")
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtWidgets import QApplication  # noqa: E402


app = QApplication([])

from infrastructure.theme_loader import BuiltinThemes  # noqa: E402


print("=" * 70)
print("内置主题定义 vs themes/*.json 差异")
print("=" * 70)

for fname in sorted(os.listdir("themes")):
    if not fname.endswith(".json"):
        continue
    with io.open(os.path.join("themes", fname), encoding="utf-8") as fh:
        data = json.load(fh)
    name = data.get("name")
    json_colors = data.get("colors", {})

    builtin = BuiltinThemes.get(name)
    print()
    print("【%s】 (%s)" % (name, fname))
    if builtin is None:
        print("  内置定义: 无（只能用 JSON）")
        continue
    bc = builtin.colors
    # 数据类字段
    fields = set(bc.__dataclass_fields__.keys()) if hasattr(
        bc, "__dataclass_fields__") else set(vars(bc))

    # JSON 有但内置未显式设置的键
    explicit = set()
    src = io.open("infrastructure/theme_loader.py", encoding="utf-8").read()
    # 粗略提取该方法体内出现的键名
    m = re.search(r"def %s\(\)\s*->\s*Theme:(.*?)(?=\n    @staticmethod|\nclass )"
                  % name, src, re.S)
    if m:
        explicit = set(re.findall(r"(\w+)\s*=", m.group(1)))
    explicit &= fields

    missing = sorted(set(json_colors) - explicit)
    print("  JSON 键数: %d   内置显式设置: %d" % (len(json_colors), len(explicit)))
    print("  内置**未设置**（会回退到默认值）的键: %d 个" % len(missing))
    for k in missing:
        print("      %-26s JSON=%-10s 实际默认=%s"
              % (k, json_colors[k], getattr(bc, k, "?")))

    # type 是否一致
    jt = data.get("type")
    bt = builtin.type
    if jt != bt:
        print("  !! type 不一致: JSON=%r 内置=%r" % (jt, bt))
