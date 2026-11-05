# -*- coding: utf-8 -*-
"""网络调用超时审计（v2.22 稳定性）

扫描 ui/core 中的 requests 与 urllib 调用，要求显式 timeout。
    python tools/audit_network_threads.py
    python tools/audit_network_threads.py --check
"""

import argparse
import io
import os
import re
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "network_thread_audit.md")
SCAN_DIRS = ("ui", "core")
REQ_ATTRS = {"get", "post", "put", "patch", "delete", "head"}
URL_FUNCS = {"urlopen", "urlretrieve"}


def _iter_calls(tree):
    import ast

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            yield node


def scan():
    """AST 扫描真实网络调用，要求显式 timeout 关键字。"""
    import ast

    violations = []
    for d in SCAN_DIRS:
        base = os.path.join(ROOT, d)
        for name in sorted(os.listdir(base)):
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            try:
                tree = ast.parse(io.open(path, encoding="utf-8", errors="replace").read())
            except SyntaxError:
                continue
            for node in _iter_calls(tree):
                fn = node.func
                call = None
                if isinstance(fn, ast.Attribute) and fn.attr in REQ_ATTRS:
                    root = fn.value
                    if isinstance(root, ast.Name) and root.id == "requests":
                        call = "requests." + fn.attr
                elif isinstance(fn, ast.Name) and fn.id in URL_FUNCS:
                    call = fn.id
                if call is None:
                    continue
                if not any(k.arg == "timeout" for k in node.keywords):
                    violations.append((os.path.relpath(path, ROOT), node.lineno, call))
    return violations


def render(violations):
    lines = ["# 网络调用超时审计（v2.22）", "", "| 文件 | 行 | 调用 |", "|---|---|---|"]
    for f, ln, call in violations:
        lines.append("| %s | %d | %s |" % (f, ln, call))
    lines += ["", "违规数：%d" % len(violations), ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    v = scan()
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(render(v))
    print("[net-audit] 违规: %d -> %s" % (len(v), OUT))
    if args.check and v:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
