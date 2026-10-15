# -*- coding: utf-8 -*-
"""空壳功能审计：找出"看起来有、实际不实用"的功能

判据（可自动检测的几类）：
  1. 占位实现   —— 只有 pass / return None / return True 而无实际动作
  2. 显式未实现 —— NotImplementedError / TODO / FIXME / "尚未实现"
  3. 只报不做   —— 函数只发状态栏提示/日志，没有任何实际状态变更
  4. 定义无调用 —— 生产代码零调用点（写好了没人用）
  5. 伪成功     —— 无条件 return True 而不检查真实结果
"""
import io
import os
import re
import sys


sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.chdir(r"D:\QingCaoEditor")

SKIP_DIRS = {"dist", "build", "__pycache__", ".git", "_archive", "tests", "tools"}

files = []
for root, dirs, fs in os.walk("."):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for f in fs:
        if f.endswith(".py"):
            files.append(os.path.join(root, f).replace(".\\", ""))

src = {p: io.open(p, encoding="utf-8", errors="replace").read() for p in files}
all_src = "\n".join(src.values())

print("=" * 78)
print("1. 显式未实现标记")
print("=" * 78)
for p in sorted(src):
    for n, line in enumerate(src[p].split("\n"), 1):
        s = line.strip()
        if re.search(r"NotImplementedError|尚未实现|未实现|not implemented|"
                     r"TODO|FIXME|XXX|占位|placeholder|stub", s, re.I):
            if s.startswith("#") or '"""' in s or "'''" in s:
                continue
            print("  %-40s L%-5d %s" % (p, n, s[:72]))

print()
print("=" * 78)
print("2. 占位实现（函数体只有 pass / return None / return True / 仅 docstring）")
print("=" * 78)
for p in sorted(src):
    lines = src[p].split("\n")
    for n, line in enumerate(lines):
        m = re.match(r"(\s*)def (\w+)\(([^)]*)\)", line)
        if not m:
            continue
        indent, name = m.group(1), m.group(2)
        # 跳过装饰器与多行签名
        body = []
        i = n + 1
        while i < len(lines) and (not lines[i].strip() or
                                  lines[i].strip().startswith(('"""', "'''", "#", ")", ":", "@")) or
                                  len(lines[i]) - len(lines[i].lstrip()) > len(indent) or
                                  lines[i].strip().startswith(")")):
            s = lines[i].strip()
            if s and not s.startswith(("#", '"""', "'''", ")", "@")):
                body.append(s)
            i += 1
            if i - n > 12:
                break
        if len(body) == 1 and body[0] in ("pass", "return None", "return True",
                                          "return", "return False"):
            print("  %-40s L%-5d def %s(...) -> %s"
                  % (p, n + 1, name, body[0]))

print()
print("=" * 78)
print("3. 伪成功：只 print / 只 showMessage / 只 logger 就 return True")
print("=" * 78)
for p in sorted(src):
    lines = src[p].split("\n")
    for n, line in enumerate(lines):
        m = re.match(r"(\s*)def (\w+)", line)
        if not m:
            continue
        seg = "\n".join(lines[n:n + 25])
        if re.search(r"return True", seg) and not re.search(
                r"\b(set|save|write|apply|emit|insert|delete|clear|update|"
                r"connect|start|open|close|send|call|invoke|run|exec)\w*\s*\(", seg):
            if re.search(r"print\(|showMessage|logger|status", seg):
                print("  %-40s L%-5d def %s" % (p, n + 1, m.group(2)))

print()
print("=" * 78)
print("4. 生产代码零调用的公开方法（写好了没人用）")
print("=" * 78)
# 收集所有 def 名
defs = {}
for p in src:
    for m in re.finditer(r"^\s+def (\w+)\s*\(", src[p], re.M):
        defs.setdefault(m.group(1), []).append(p)

# 只关心"像功能入口"的名字
INTERESTING = re.compile(
    r"^(apply_|do_|show_|open_|toggle_|enable_|disable_|request_|export_|"
    r"import_|install_|uninstall_|run_|execute_|format_|merge_|sync_|"
    r"recover_|restore_|backup_|preview_|publish_|build_|generate_)"
)
for name in sorted(defs):
    if not INTERESTING.match(name):
        continue
    if len(defs[name]) > 1:
        continue          # 重名（可能是覆盖）另行处理
    # 统计全仓调用点（排除定义处）
    calls = 0
    for q in src:
        for mm in re.finditer(r"[.\s]" + re.escape(name) + r"\s*\(", src[q]):
            line_start = src[q].rfind("\n", 0, mm.start()) + 1
            line = src[q][line_start:src[q].find("\n", mm.start())]
            if re.match(r"\s*def\s+" + re.escape(name), line):
                continue
            calls += 1
    if calls == 0:
        print("  %-40s def %s  (0 调用点)" % (defs[name][0], name))
