# -*- coding: utf-8 -*-
"""插件沙箱阶段 A：静态审计 + 运行时告警 + 可信允许列表（只告警不阻断）。

设计见 docs/plugin_sandbox_stage_a.md。
"""

import ast
import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HIGH_RISK_MODULES = {"ctypes", "subprocess", "multiprocessing", "_winapi", "winreg"}
MEDIUM_RISK_MODULES = {"socket", "pickle", "marshal", "shutil", "sqlite3"}
DANGEROUS_CALLS = {
    "os.system": "high",
    "os.popen": "high",
    "os.exec": "high",
    "os.spawn": "high",
    "subprocess": "high",
    "ctypes": "high",
    "eval": "high",
    "exec": "high",
    "pickle.load": "high",
    "marshal.loads": "high",
    "shutil.rmtree": "medium",
}

_TRUSTED_CACHE = None
_WARNED = set()


def trusted_plugins(path=None):
    """读取可信插件允许列表（resources/trusted_plugins.json）。"""
    global _TRUSTED_CACHE
    if path is None and _TRUSTED_CACHE is not None:
        return _TRUSTED_CACHE
    p = path or os.path.join(ROOT, "resources", "trusted_plugins.json")
    names = set()
    try:
        data = json.load(io.open(p, encoding="utf-8"))
        for item in data.get("plugins", []):
            if isinstance(item, str):
                names.add(item)
            elif isinstance(item, dict) and item.get("name"):
                names.add(item["name"])
    except Exception:
        pass
    if path is None:
        _TRUSTED_CACHE = names
    return names


def _call_name(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def audit_source(path):
    """静态扫描单个 .py：危险 import / 调用。"""
    findings = []
    try:
        tree = ast.parse(io.open(path, encoding="utf-8", errors="ignore").read())
    except Exception:
        return findings
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                base = a.name.split(".")[0]
                if base in HIGH_RISK_MODULES:
                    findings.append(
                        {
                            "kind": "import",
                            "name": base,
                            "risk": "high",
                            "file": path,
                            "line": node.lineno,
                        }
                    )
                elif base in MEDIUM_RISK_MODULES:
                    findings.append(
                        {
                            "kind": "import",
                            "name": base,
                            "risk": "medium",
                            "file": path,
                            "line": node.lineno,
                        }
                    )
        elif isinstance(node, ast.ImportFrom):
            base = (node.module or "").split(".")[0]
            if base in HIGH_RISK_MODULES:
                findings.append(
                    {
                        "kind": "import",
                        "name": base,
                        "risk": "high",
                        "file": path,
                        "line": node.lineno,
                    }
                )
            elif base in MEDIUM_RISK_MODULES:
                findings.append(
                    {
                        "kind": "import",
                        "name": base,
                        "risk": "medium",
                        "file": path,
                        "line": node.lineno,
                    }
                )
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            for prefix, risk in DANGEROUS_CALLS.items():
                if name == prefix or name.startswith(prefix + "."):
                    findings.append(
                        {
                            "kind": "call",
                            "name": name,
                            "risk": risk,
                            "file": path,
                            "line": node.lineno,
                        }
                    )
                    break
    return findings


def audit_plugin(plugin_dir, name=None):
    """审计插件目录；可信插件 findings 标记 allowed（不告警）。"""
    name = name or os.path.basename(os.path.normpath(plugin_dir))
    findings = []
    for dp, _dn, files in os.walk(plugin_dir):
        if "__pycache__" in dp:
            continue
        for f in files:
            if f.endswith(".py"):
                findings.extend(audit_source(os.path.join(dp, f)))
    trusted = name in trusted_plugins()
    for item in findings:
        item["plugin"] = name
        item["risk"] = "high" if item.get("risk") == "high" else "medium"
        item["allowed"] = trusted
    return {"plugin": name, "trusted": trusted, "findings": findings}


def audit_all(plugin_root=None):
    root = plugin_root or os.path.join(ROOT, "plugins")
    reports = []
    for entry in sorted(os.listdir(root)):
        d = os.path.join(root, entry)
        if os.path.isdir(d) and os.path.isfile(os.path.join(d, "plugin.json")):
            reports.append(audit_plugin(d, entry))
    return reports


def install_audit_guard(logger=None):
    """运行时告警（仅告警）：插件栈内 import 高危模块/调用危险 API 时记录一次。"""
    import logging
    import traceback

    log = logger or logging.getLogger("QingCao.PluginGuard")

    def _from_plugin():
        try:
            for frame in traceback.extract_stack(limit=12):
                p = frame.filename.replace("\\", "/")
                if "/plugins/" in p:
                    return True
        except Exception:
            pass
        return False

    def _hook(event, args):
        try:
            if event == "import" and args and str(args[0]).split(".")[0] in HIGH_RISK_MODULES:
                mod = str(args[0]).split(".")[0]
                key = ("import", mod)
                if key not in _WARNED and _from_plugin():
                    _WARNED.add(key)
                    log.warning("[sandbox-A] 插件导入高危模块 %s（仅告警）", mod)
            elif event in ("os.system", "subprocess.Popen", "ctypes.dlopen"):
                key = ("event", event)
                if key not in _WARNED and _from_plugin():
                    _WARNED.add(key)
                    log.warning("[sandbox-A] 插件调用高危 API %s（仅告警）", event)
        except Exception:
            pass

    try:
        sys.addaudithook(_hook)
        return True
    except Exception:
        return False
