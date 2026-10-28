# -*- coding: utf-8 -*-
"""插件全面分析：功能/性能/UI/沙箱就绪度"""
import ast
import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEAVY = {"numpy", "pandas", "matplotlib", "scipy", "requests",
         "PyQt5.QtWebEngineWidgets", "torch", "PIL"}
EXT_PREFIXES = ("register_", "add_", "publish_", "clear_")


def analyze_plugin(path):
    info = {"dir": os.path.basename(path)}
    manifest = os.path.join(path, "plugin.json")
    if os.path.exists(manifest):
        try:
            m = json.load(io.open(manifest, encoding="utf-8"))
            info["name"] = m.get("name") or m.get("id")
            info["version"] = m.get("version")
            info["enabled"] = m.get("enabled", True)
            info["sandbox"] = bool(m.get("sandbox"))
            info["permissions"] = m.get("permissions") or []
        except Exception:
            pass
    info.setdefault("name", info["dir"])
    loc = 0
    imports = set()
    ext = set()
    api_calls = set()
    methods = set()
    hard_qss = 0
    timers = 0
    threads = 0
    file_ops = 0
    net = 0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if not f.endswith(".py"):
                continue
            fp = os.path.join(root, f)
            try:
                src = io.open(fp, encoding="utf-8").read()
                tree = ast.parse(src)
            except Exception:
                continue
            loc += src.count("\n") + 1
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        root_mod = a.name.split(".")[0]
                        if a.name in HEAVY or root_mod in HEAVY:
                            imports.add(a.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        root_mod = node.module.split(".")[0]
                        if node.module in HEAVY or root_mod in HEAVY:
                            imports.add(node.module)
                elif isinstance(node, ast.FunctionDef):
                    if not node.name.startswith("_"):
                        methods.add(node.name)
                elif isinstance(node, ast.Attribute) and node.attr:
                    if node.attr.startswith(EXT_PREFIXES):
                        ext.add(node.attr)
                    if node.attr in ("api",):
                        pass
                elif isinstance(node, ast.Call):
                    fn = node.func
                    if isinstance(fn, ast.Attribute):
                        name = fn.attr
                        if name.startswith("register_") or name.startswith("add_"):
                            ext.add(name)
                        if name == "setStyleSheet":
                            hard_qss += 1
                        if name in ("singleShot", "start", "exec_"):
                            timers += 1
                        if name == "Thread":
                            threads += 1
                        if name in ("open", "write_text", "write_bytes", "save"):
                            file_ops += 1
                        if name in ("get", "post", "urlopen", "request"):
                            net += 1
                        if fn.value is not None and isinstance(
                                fn.value, ast.Name) and fn.value.id == "api":
                            api_calls.add(name)
    info.update({
        "loc": loc,
        "heavy_imports": sorted(imports),
        "extensions": sorted(ext),
        "api_calls": sorted(api_calls)[:12],
        "refresh_theme": "refresh_theme" in methods,
        "hard_qss": hard_qss,
        "timers": timers,
        "threads": threads,
        "file_ops": file_ops,
        "net": net,
        "sandbox_ready": "diagnostics" in methods or "symbols" in methods,
    })
    return info


def main():
    base = os.path.join(ROOT, "plugins")
    rows = []
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name)
        if not os.path.isdir(path) or name.startswith("_"):
            continue
        if not os.path.exists(os.path.join(path, "plugin.json")):
            continue
        rows.append(analyze_plugin(path))
    out_json = os.path.join(ROOT, "data", "plugin_analysis.json")
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    io.open(out_json, "w", encoding="utf-8", newline="\n").write(
        json.dumps(rows, ensure_ascii=False, indent=2))
    lines = ["# 插件全面分析（v2.13.0 基线）", "",
             "| 插件 | 版本 | 启用 | 沙箱 | LOC | 扩展点 | 重依赖 | refresh_theme | 硬编码QSS | 线程 | 文件IO | 网络 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %s | %s | %d | %s | %s | %s | %d | %d | %d | %d |"
                     % (r["name"], r.get("version"), "✓" if r.get("enabled") else "✗",
                        "✓" if r.get("sandbox") else "✗", r["loc"],
                        ",".join(r["extensions"])[:60] or "-",
                        ",".join(r["heavy_imports"]) or "-",
                        "✓" if r["refresh_theme"] else "✗",
                        r["hard_qss"], r["threads"], r["file_ops"], r["net"]))
    print("\n".join(lines))
    print("\n[JSON] %s" % out_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())