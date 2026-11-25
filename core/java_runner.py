# -*- coding: utf-8 -*-
"""Java 单文件运行（阶段 1）：javac + java，供内嵌控制台调用。"""

import os
import re
import shutil
import tempfile


PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)
CLASS_RE = re.compile(
    r"(?m)^\s*(public\s+)?(?:final\s+|abstract\s+)?"
    r"(class|interface|enum|record)\s+(\w+)"
)


def find_tools():
    javac = shutil.which("javac")
    java = shutil.which("java")
    return {"javac": javac, "java": java, "ok": bool(javac and java)}


def parse_java(text):
    package = ""
    m = PACKAGE_RE.search(text or "")
    if m:
        package = m.group(1)
    classes = list(CLASS_RE.finditer(text or ""))
    if not classes:
        return None
    public = [c for c in classes if c.group(1)]
    chosen = public[0] if public else classes[0]
    return package, chosen.group(3)


def build_batch(javac, java, src, out, full_class):
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        '"%s" -encoding UTF-8 -d "%s" "%s"' % (javac, out, src),
        "if errorlevel 1 exit /b 1",
        '"%s" -Dfile.encoding=UTF-8 -cp "%s" %s' % (java, out, full_class),
    ]
    return "\r\n".join(lines) + "\r\n"


def prepare(filepath):
    filepath = os.path.abspath(str(filepath))
    if not filepath.lower().endswith(".java"):
        return {"ok": False, "error": "仅支持 .java 文件"}
    if not os.path.isfile(filepath):
        return {"ok": False, "error": "文件不存在"}
    tools = find_tools()
    if not tools["ok"]:
        return {"ok": False, "error": "未找到 javac/java，请安装 JDK 并加入 PATH"}
    text = open(filepath, encoding="utf-8", errors="replace").read()
    parsed = parse_java(text)
    if parsed is None:
        return {"ok": False, "error": "未找到 Java 类定义"}
    package, cls = parsed
    full = (package + "." + cls) if package else cls
    out = tempfile.mkdtemp(prefix="qc_java_")
    batch = os.path.join(out, "run.bat")
    open(batch, "w", encoding="utf-8", newline="\r\n").write(
        build_batch(tools["javac"], tools["java"], filepath, out, full)
    )
    return {"ok": True, "batch": batch, "cwd": os.path.dirname(filepath), "out": out, "class": full}
