# -*- coding: utf-8 -*-
"""功能可达性普查 v2：区分"真孤立"与"运行时动态加载"

v1 的静态 import 闭包把两类误判为不可达：
  * 插件（由 PluginLoader 用 importlib 动态导入）
  * 构建/发布脚本（build.py / release.py 等，本就不是运行时入口）
本版把它们分开，只把"既非动态加载、也非构建脚本"的模块算作真孤立。
"""
import io
import os
import re
import sys


sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.chdir(r"D:\QingCaoEditor")

SKIP = ("dist", "build", "__pycache__", ".git", "_archive", "tests", "tools",
        "1.0 QingCaoEditor_Others")

src = {}
for root, dirs, fs in os.walk("."):
    dirs[:] = [d for d in dirs if d not in SKIP]
    for f in fs:
        if f.endswith(".py"):
            p = os.path.relpath(os.path.join(root, f)).replace("\\", "/")
            src[p] = io.open(os.path.join(root, f),
                             encoding="utf-8", errors="replace").read()


def to_mod(path):
    return path[:-3].replace("/", ".")


def imports_of(text):
    out = set()
    for m in re.finditer(r"^\s*from\s+([\w\.]+)\s+import\s+([^\n]+)", text, re.M):
        out.add(m.group(1))
        for name in re.split(r"[,\(\)\s]+", m.group(2)):
            name = name.strip()
            if name and name != "*" and not name.startswith("#"):
                out.add(m.group(1) + "." + name)
    for m in re.finditer(r"^\s*import\s+([^\n]+)", text, re.M):
        for name in re.split(r"[,\s]+", m.group(1)):
            name = name.strip().split(" as ")[0]
            if name:
                out.add(name)
    return out


mod2file = {to_mod(p): p for p in src}

reach = set()
queue, seen = ["main"], set()
while queue:
    mod = queue.pop()
    if mod in seen:
        continue
    seen.add(mod)
    f = mod2file.get(mod)
    if f is None:
        continue
    reach.add(f)
    for dep in imports_of(src[f]):
        if dep in mod2file:
            queue.append(dep)
        else:
            for cand in mod2file:
                if cand == dep or cand.startswith(dep + "."):
                    queue.append(cand)

# 插件由 PluginLoader 用 importlib 动态加载（静态闭包看不到），
# 但它们内部用**绝对导入**引用 core.*/ui.*，因此把插件也纳入遍历起点，
# 这样"经插件可达"的 core 模块不会被误判为孤立。
plugin_roots = [p for p in src if p.startswith("plugins/")]
for p in plugin_roots:
    queue.append(to_mod(p))
while queue:
    mod = queue.pop()
    if mod in seen:
        continue
    seen.add(mod)
    f = mod2file.get(mod)
    if f is None:
        continue
    reach.add(f)
    for dep in imports_of(src[f]):
        if dep in mod2file:
            queue.append(dep)
        else:
            for cand in mod2file:
                if cand == dep or cand.startswith(dep + "."):
                    queue.append(cand)

# --- 分类 ---
BUILD_SCRIPTS = {
    "build.py", "build_installer.py", "build_linux.py", "build_macos.py",
    "release.py", "archive_scripts.py", "fix_batch_final.py",
    "fix_fix_b1b.py", "__init__.py",
}

unreach = sorted(set(src) - reach)
dyn_plugin, build, orphan = [], [], []
for p in unreach:
    base = os.path.basename(p)
    if p.startswith("plugins/"):
        dyn_plugin.append(p)
    elif base in BUILD_SCRIPTS or base == "__init__.py":
        build.append(p)
    else:
        orphan.append(p)

print("=" * 78)
print("统计概览")
print("=" * 78)
print("  生产代码文件总数        : %d" % len(src))
print("  静态可达（main 闭包）   : %d" % len(reach))
print("  运行时动态加载（插件）  : %d" % len(dyn_plugin))
print("  构建/发布脚本           : %d" % len(build))
print("  ★ 真孤立（非上述两类）  : %d" % len(orphan))
print()

print("=" * 78)
print("★ 真孤立模块（完整实现但无任何静态引用，也不是插件/脚本）")
print("=" * 78)
for p in sorted(orphan, key=lambda x: -src[x].count("\n")):
    n = src[p].count("\n")
    names = re.findall(r"^class\s+(\w+)", src[p], re.M)
    print("  %-42s %5d 行  %s" % (p, n, ", ".join(names[:3]) if names else ""))

print()
print("=" * 78)
print("运行时动态加载（插件，属正常）")
print("=" * 78)
for p in dyn_plugin:
    names = re.findall(r"^class\s+(\w+)", src[p], re.M)
    if "Plugin" in names or "PluginBase" in src[p]:
        print("  %-42s %5d 行" % (p, src[p].count("\n")))
