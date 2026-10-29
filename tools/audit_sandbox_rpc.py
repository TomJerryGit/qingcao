# -*- coding: utf-8 -*-
"""沙箱 RPC 方法白名单自动化审计（v2.15.x P3）

校验：
  1. ALLOWED_METHODS 中的每个方法都有 worker 处理分支；
  2. worker 处理的所有方法都在 ALLOWED_METHODS 内；
  3. manager 代理方法（_safe_call/_call）覆盖白名单（缺失仅警告）。

用法: python tools/audit_sandbox_rpc.py [--strict] [--json OUT]
"""
import argparse
import ast
import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RPC = os.path.join(ROOT, "infrastructure", "plugin_sandbox_rpc.py")
WORKER = os.path.join(ROOT, "infrastructure", "plugin_sandbox_worker.py")
MANAGER = os.path.join(ROOT, "infrastructure", "plugin_sandbox_manager.py")


def _allowed_methods():
    tree = ast.parse(io.open(RPC, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "ALLOWED_METHODS"
                for t in node.targets):
            call = node.value
            if isinstance(call, ast.Call) and call.args:
                arg = call.args[0]
                if isinstance(arg, ast.Set):
                    return {e.value for e in arg.elts
                            if isinstance(e, ast.Constant)
                            and isinstance(e.value, str)}
    return set()


def _worker_handlers():
    tree = ast.parse(io.open(WORKER, encoding="utf-8").read())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            left = node.left
            if isinstance(left, ast.Name) and left.id == "method":
                for op, comp in zip(node.ops, node.comparators):
                    if isinstance(op, ast.Eq) and isinstance(comp, ast.Constant) \
                            and isinstance(comp.value, str):
                        out.add(comp.value)
    return out


def _manager_proxies():
    tree = ast.parse(io.open(MANAGER, encoding="utf-8").read())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr in (
                    "_safe_call", "_call"):
                if node.args and isinstance(node.args[0], ast.Constant) \
                        and isinstance(node.args[0].value, str):
                    out.add(node.args[0].value)
    return out


def audit_sets(allowed, handlers, proxies):
    missing_handler = sorted(set(allowed) - set(handlers))
    unlisted_handler = sorted(set(handlers) - set(allowed))
    return {
        "allowed": sorted(allowed),
        "handlers": sorted(handlers),
        "missing_handler": missing_handler,
        "unlisted_handler": unlisted_handler,
        "missing_proxy": sorted(set(allowed) - set(proxies)),
        "ok": not (missing_handler or unlisted_handler),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    result = audit_sets(_allowed_methods(), _worker_handlers(),
                        _manager_proxies())
    result["ok"] = not (result["missing_handler"] or result["unlisted_handler"])
    print("[sandbox-rpc] 白名单 %d 个方法" % len(result["allowed"]))
    if result["missing_handler"]:
        print("  缺少 handler:", result["missing_handler"])
    if result["unlisted_handler"]:
        print("  未登记 handler:", result["unlisted_handler"])
    if result["missing_proxy"]:
        print("  缺少 manager 代理:", result["missing_proxy"])
    print("[sandbox-rpc] %s" % ("审计通过" if result["ok"] else "审计失败"))
    if args.json:
        with io.open(args.json, "w", encoding="utf-8", newline="\n") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    return 0 if result["ok"] else (1 if args.strict else 0)


if __name__ == "__main__":
    sys.exit(main())