# -*- coding: utf-8 -*-
"""独立验证 diff 引擎在**真实代码场景**下的正确性

不使用任何人为构造的 "lineN" 样本 —— 那些短行在 difflib 下本质不可分辨
（"line4" vs "line5" 的相似度 0.800，反而高于 "line3" vs
"line3-changed" 的 0.556）。本脚本用真实风格的代码/文本断言语义。
"""
import os
import sys


os.chdir(r"D:\QingCaoEditor")
sys.path.insert(0, r"D:\QingCaoEditor")
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from ui.file_merge_dialog import (  # noqa: E402
    KIND_ADD,
    KIND_DELETE,
    KIND_MODIFY,
    compute_diff,
    diff_summary,
)


PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %-52s %s" % ("OK " if cond else "FAIL", name, detail))


def kinds_of(a, b):
    return [r.kind for r in compute_diff(a, b)]


def stats_of(a, b):
    return diff_summary(compute_diff(a, b))


print("=" * 100)
print("diff 引擎 · 真实代码场景验证")
print("=" * 100)

# ---- 场景 1：改一行（真实代码风格）----
print()
print("[1] 修改一行（真实代码）")
a = "def f(a):\n    return a + 1\n\ndef g(b):\n    return b * 2\n"
b = "def f(a):\n    return a + 2\n\ndef g(b):\n    return b * 2\n"
s = stats_of(a, b)
check("1a 修改数 == 1", s.modified == 1, "modified=%d" % s.modified)
check("1b 无新增", s.added == 0, "added=%d" % s.added)
check("1c 无删除", s.deleted == 0, "deleted=%d" % s.deleted)
k = kinds_of(a, b)
check("1d 对齐序列正确",
      k == ["equal", "modify", "equal", "equal", "equal"], str(k))

# ---- 场景 2：删一行 + 增一行（各自独立，无对应行）----
print()
print("[2] 删一行 + 增一行（互不对应）")
a = "alpha\nbravo\ncharlie\ndelta\n"
b = "alpha\ncharlie\ndelta\necho\n"
s = stats_of(a, b)
check("2a 删除数 == 1", s.deleted == 1, "deleted=%d" % s.deleted)
check("2b 新增数 == 1", s.added == 1, "added=%d" % s.added)
check("2c 修改数 == 0", s.modified == 0, "modified=%d" % s.modified)

# ---- 场景 3：纯新增 ----
print()
print("[3] 纯新增（无任何删除）")
a = "one\ntwo\n"
b = "one\ntwo\nthree\nfour\n"
s = stats_of(a, b)
check("3a 新增数 == 2", s.added == 2, "added=%d" % s.added)
check("3b 无删除/修改", s.deleted == 0 and s.modified == 0,
      "del=%d mod=%d" % (s.deleted, s.modified))

# ---- 场景 4：纯删除 ----
print()
print("[4] 纯删除")
a = "one\ntwo\nthree\nfour\n"
b = "one\ntwo\n"
s = stats_of(a, b)
check("4a 删除数 == 2", s.deleted == 2, "deleted=%d" % s.deleted)
check("4b 无新增/修改", s.added == 0 and s.modified == 0,
      "add=%d mod=%d" % (s.added, s.modified))

# ---- 场景 5：改一行 + 中间插一行（两者相邻）----
print()
print("[5] 改一行 + 中间插一行（相邻，考验对齐）")
a = ("import os\n"
     "def run():\n"
     "    value = 1\n"
     "    return value\n")
b = ("import os\n"
     "def run():\n"
     "    log = None\n"
     "    value = 2\n"
     "    return value\n")
s = stats_of(a, b)
check("5a 新增 1 行（log = None）", s.added == 1, "added=%d" % s.added)
check("5b 修改 1 行（value = 1 → 2）", s.modified == 1,
      "modified=%d" % s.modified)
check("5c 无删除", s.deleted == 0, "deleted=%d" % s.deleted)
rows = compute_diff(a, b)
add_row = [r for r in rows if r.kind == KIND_ADD]
mod_row = [r for r in rows if r.kind == KIND_MODIFY]
check("5d 新增行内容正确",
      add_row and add_row[0].right.strip() == "log = None",
      "%r" % (add_row[0].right if add_row else None))
check("5e 修改行左右内容正确",
      mod_row and mod_row[0].left.strip() == "value = 1"
      and mod_row[0].right.strip() == "value = 2",
      "%r -> %r" % (mod_row[0].left if mod_row else None,
                    mod_row[0].right if mod_row else None))

# ---- 场景 6：对齐不变式（左右行号递增、非空槽对应）----
print()
print("[6] 对齐不变式")
rows = compute_diff(a, b)
left_ok = True
right_ok = True
for r in rows:
    if r.kind != KIND_ADD and r.left is None:
        left_ok = False
    if r.kind != KIND_DELETE and r.right is None:
        right_ok = False
check("6a 非 ADD 行左槽非空", left_ok)
check("6b 非 DELETE 行右槽非空", right_ok)
check("6c 左栏非空槽数 == A 行数",
      sum(1 for r in rows if r.left is not None) == len(a.splitlines()),
      "%d vs %d" % (sum(1 for r in rows if r.left is not None),
                    len(a.splitlines())))
check("6d 右栏非空槽数 == B 行数",
      sum(1 for r in rows if r.right is not None) == len(b.splitlines()),
      "%d vs %d" % (sum(1 for r in rows if r.right is not None),
                    len(b.splitlines())))
lnos = [r.left_no for r in rows if r.left_no is not None]
rnos = [r.right_no for r in rows if r.right_no is not None]
check("6e 左行号严格递增", lnos == sorted(lnos) and len(set(lnos)) == len(lnos),
      str(lnos))
check("6f 右行号严格递增", rnos == sorted(rnos) and len(set(rnos)) == len(rnos),
      str(rnos))
check("6g 左行号最大值 == A 行数",
      (not lnos) or max(lnos) == len(a.splitlines()), str(lnos[-3:]))
check("6h 右行号最大值 == B 行数",
      (not rnos) or max(rnos) == len(b.splitlines()), str(rnos[-3:]))

# ---- 场景 7：空文件边界 ----
print()
print("[7] 边界")
check("7a 两空 → 0 行", len(compute_diff("", "")) == 0,
      "%d" % len(compute_diff("", "")))
s = stats_of("", "a\nb\n")
check("7b 空 → 2 行 = 新增 2", s.added == 2, "added=%d" % s.added)
s = stats_of("a\nb\n", "")
check("7c 2 行 → 空 = 删除 2", s.deleted == 2, "deleted=%d" % s.deleted)

# ---- 场景 8：末尾无换行 ----
print()
print("[8] 末尾无换行")
s = stats_of("a\nb", "a\nb\n")
check("8a 末尾换行差异 → 不产生虚假修改",
      s.modified == 0 and s.added <= 1 and s.deleted <= 1,
      "add=%d del=%d mod=%d" % (s.added, s.deleted, s.modified))

# ---- 场景 9：真实中文代码 ----
print()
print("[9] 中文内容")
a = "def 计算(数值):\n    return 数值 * 2\n"
b = "def 计算(数值):\n    return 数值 * 3\n"
s = stats_of(a, b)
check("9a 中文行修改识别为 1 处", s.modified == 1, "modified=%d" % s.modified)
rows = compute_diff(a, b)
m = [r for r in rows if r.kind == KIND_MODIFY]
check("9b 中文行字符区间非空", m and m[0].left_ranges and m[0].right_ranges,
      "left=%s right=%s" % (m[0].left_ranges if m else None,
                            m[0].right_ranges if m else None))

print()
print("=" * 100)
print("结果：%d 通过 / %d 失败" % (len(PASS), len(FAIL)))
print("=" * 100)
if FAIL:
    print("失败项：")
    for n in FAIL:
        print("  - " + n)
