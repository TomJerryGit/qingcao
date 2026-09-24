# -*- coding: utf-8 -*-
"""修复 fix_p1_char_byte.py 的 4 元组解包问题"""
import shutil
from pathlib import Path

TARGET = Path(__file__).resolve().parent / "fix_p1_char_byte.py"

OLD = "        for i, (marker, old, _) in enumerate(SECTIONS, 1):"
NEW = "        for i, (marker, old, _, _) in enumerate(SECTIONS, 1):"

if not TARGET.exists():
    print(f"[FAIL] 未找到 {TARGET}")
    raise SystemExit(1)

content = TARGET.read_text(encoding='utf-8')

if NEW in content:
    print("[SKIP] 已修复")
    raise SystemExit(0)

if OLD not in content:
    print("[FAIL] 未找到目标行")
    raise SystemExit(1)

# 备份
bak = TARGET.with_suffix('.py.bak.unpack')
if not bak.exists():
    shutil.copy2(TARGET, bak)
    print(f"[OK]   已备份: {bak.name}")

content = content.replace(OLD, NEW, 1)
TARGET.write_text(content, encoding='utf-8', newline='\n')
print("[OK]   已修复")