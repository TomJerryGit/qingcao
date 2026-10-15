# -*- coding: utf-8 -*-
"""列出主窗口已占用的快捷键，用于挑选无冲突的新键"""
import io
import os
import re
import sys


sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.chdir(r"D:\QingCaoEditor")

src = io.open("ui/main_window.py", encoding="utf-8").read()

keys = set()
# setShortcut(QKeySequence("Ctrl+X"))
for m in re.finditer(r'setShortcut\(QKeySequence\("([^"]+)"\)\)', src):
    keys.add(m.group(1))
# _add_action(menu, "标题", "Ctrl+X", slot)
for m in re.finditer(r'_add_action\([^,]+,\s*"[^"]*",\s*"([^"]+)"', src):
    keys.add(m.group(1))

print("已占用 %d 个快捷键：" % len(keys))
for k in sorted(keys):
    print("   ", k)

# 候选新键
candidates = [
    "Ctrl+Alt+H", "Ctrl+Alt+F", "Ctrl+Alt+S", "Ctrl+Alt+N",
    "Ctrl+Shift+H", "Ctrl+Shift+R", "Alt+F12", "Ctrl+F12",
    "Ctrl+Alt+K", "Ctrl+Alt+J", "Ctrl+Alt+P", "Ctrl+Shift+I",
    "Ctrl+Shift+K", "Ctrl+Alt+O", "Ctrl+Alt+U", "Ctrl+Alt+Y",
]
print()
print("候选键占用情况：")
for c in candidates:
    used = c.lower() in {k.lower() for k in keys}
    print("   %-16s %s" % (c, "已占用" if used else "可用"))
