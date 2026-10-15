# -*- coding: utf-8 -*-
"""找出"完整实现但没有任何引用"的模块（按类名/模块名双向判定）

判据：
  * 模块 > 80 行且含 class/def（有实质实现）
  * 全仓（生产代码）中既没有 `import <mod>`，
    也没有任何一处出现该模块里的**公开类名**
"""
import io
import os
import re
import sys


sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.chdir(r"D:\QingCaoEditor")

SKIP = ("dist", "build", "__pycache__", ".git", "_archive", "tests", "tools")

proc = {}
for root, dirs, fs in os.walk("."):
    dirs[:] = [d for d in dirs if d not in SKIP]
    for f in fs:
        if f.endswith(".py"):
            p = os.path.relpath(os.path.join(root, f)).replace("\\", "/")
            proc[p] = io.open(
                os.path.join(root, f), encoding="utf-8", errors="replace"
            ).read()

allt = "\n".join(proc.values())

rows = []
for p, t in sorted(proc.items()):
    if not (p.startswith("core/") or p.startswith("ui/") or
            p.startswith("plugins/")):
        continue
    nlines = t.count("\n")
    if nlines < 80:
        continue
    classes = re.findall(r"^class\s+(\w+)", t, re.M)
    if not classes:
        continue
    mod = p[:-3].replace("/", ".")
    short = p[:-3].split("/")[-1]

    # 模块级 import
    imported = bool(
        re.search(r"(import\s+" + re.escape(mod) + r"\b)", allt)
        or re.search(r"(from\s+" + re.escape(mod) + r"\s+import)", allt)
        or re.search(r"(from\s+\S+\s+import\s+" + re.escape(short) + r"\b)", allt)
    )
    if imported:
        continue

    # 类名引用（排除定义所在文件自身）
    used = []
    for c in classes:
        pat = re.compile(r"\b" + re.escape(c) + r"\b")
        for q, qt in proc.items():
            if q == p:
                continue
            if pat.search(qt):
                used.append((c, q))
                break
    kind = "部分引用（类被用到）" if used else "完全无引用"
    rows.append((p, nlines, classes[:4], used[:2], kind))

print("=" * 78)
print("完整实现但无引用的模块（按行数降序）")
print("=" * 78)
for p, n, classes, used, kind in sorted(rows, key=lambda r: -r[1]):
    print("  %-40s %4d 行  %s" % (p, n, kind))
    print("      类: %s" % ", ".join(classes))
    if used:
        print("      被引用于: %s" % ", ".join("%s@%s" % u for u in used))
print()
print("合计 %d 个模块" % len(rows))
