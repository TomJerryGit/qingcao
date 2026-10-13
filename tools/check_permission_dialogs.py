# -*- coding: utf-8 -*-
"""检查哪些插件会触发权限确认对话框（启动时阻塞加载的主因）"""
import io
import json
import os
import re
import sys


sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

t = io.open("app/plugin_manager.py", encoding="utf-8").read()
m = re.search(r"DANGEROUS_PERMISSIONS\s*=\s*[\[({](.*?)[\])}]", t, re.S)
block = m.group(1) if m else ""
danger = set(re.findall(r"""["']([a-z_]+)["']""", block))
print("危险权限集合:", sorted(danger))
print()

print("各插件权限与是否弹确认框：")
need = []
for d in sorted(os.listdir("plugins")):
    f = os.path.join("plugins", d, "plugin.json")
    if not os.path.isfile(f):
        continue
    j = json.load(io.open(f, encoding="utf-8"))
    perms = set(j.get("permissions") or [])
    hit = sorted(perms & danger)
    if hit:
        need.append((d, j.get("display_name", d), hit))
        print("  %-18s 弹确认框  <<<  危险权限=%s" % (d, hit))
    else:
        print("  %-18s 自动放行        权限=%s" % (d, sorted(perms) or "无"))
print()

print("需要在启动时逐个确认的插件数:", len(need))
for n, disp, hit in need:
    print("   - %s (%s): %s" % (n, disp, hit))
print()

# auto_confirm_dangerous 的默认值
for ln in t.split("\n"):
    if "auto_confirm_dangerous" in ln:
        print("auto_confirm_dangerous:", ln.strip())
