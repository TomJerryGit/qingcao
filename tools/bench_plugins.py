# -*- coding: utf-8 -*-
"""插件性能基准：导入耗时/模块规模

用法: python tools/bench_plugins.py [--json OUT]
"""
import argparse
import importlib.util
import io
import json
import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def warmup():
    """预热宿主公共模块，避免把宿主首次导入算进插件耗时"""
    for mod in ("PyQt5.QtWidgets", "PyQt5.QtGui", "app.plugins",
                "core.ai_client", "core.ollama_client",
                "core.problems", "infrastructure.theme_loader"):
        try:
            __import__(mod)
        except Exception:
            pass


def bench(with_warmup=True):
    if with_warmup:
        warmup()
    base = os.path.join(ROOT, "plugins")
    rows = []
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name, "__init__.py")
        if not os.path.exists(path):
            continue
        spec = importlib.util.spec_from_file_location(
            "qc_bench_plugin_%s" % name.replace("-", "_"), path)
        mod = importlib.util.module_from_spec(spec)
        t0 = time.perf_counter()
        try:
            spec.loader.exec_module(mod)
            err = ""
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, e)
        dt = (time.perf_counter() - t0) * 1000.0
        rows.append({"plugin": name, "import_ms": round(dt, 1),
                     "warmup": bool(with_warmup),
                     "init_bytes": os.path.getsize(path), "error": err})
    rows.sort(key=lambda r: r["import_ms"], reverse=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--no-warmup", action="store_true")
    args = ap.parse_args()
    rows = bench(with_warmup=not args.no_warmup)
    print("%-22s %10s %10s" % ("plugin", "import_ms", "bytes"))
    for r in rows:
        print("%-22s %10.1f %10d %s" % (
            r["plugin"], r["import_ms"], r["init_bytes"],
            ("ERR " + r["error"][:60]) if r["error"] else ""))
    out = args.json or os.path.join(ROOT, "data", "plugin_bench.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    io.open(out, "w", encoding="utf-8", newline="\n").write(
        json.dumps(rows, ensure_ascii=False, indent=2))
    print("[bench] %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())