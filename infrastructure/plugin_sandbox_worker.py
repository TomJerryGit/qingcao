# -*- coding: utf-8 -*-
"""插件沙箱子进程 worker：JSON Lines over stdin/stdout

在子进程里导入插件并响应只读调用；主进程永不导入插件代码。
"""
import importlib.util
import json
import os
import sys


def _load_plugin(plugin_dir: str):
    init = os.path.join(plugin_dir, "__init__.py")
    if not os.path.exists(init):
        raise RuntimeError("插件缺少 __init__.py")
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)
    spec = importlib.util.spec_from_file_location(
        "sandbox_plugin", init)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cls = getattr(mod, "Plugin", None)
    if cls is None:
        raise RuntimeError("插件缺少 Plugin 类")
    return cls()


def _handle(plugin, method: str, params: dict):
    # describe 是协议内建方法，不要求插件实现
    if method == "describe":
        return {"name": getattr(plugin, "NAME", ""),
                "version": getattr(plugin, "VERSION", "")}
    fn = getattr(plugin, method, None)
    if not callable(fn):
        if method not in ("config_schema", "config_apply"):
            raise RuntimeError("插件未实现方法: %s" % method)
    if method == "symbols":
        return fn(params.get("text", ""), params.get("filepath", ""),
                  params.get("language", ""))
    if method == "hover":
        return fn(params.get("line", 0), params.get("col", 0),
                  params.get("filepath", ""), params.get("language", ""))
    if method == "diagnostics":
        fn = getattr(plugin, "diagnostics", None)
        if not callable(fn):
            raise RuntimeError("插件未实现方法: diagnostics")
        raw = fn(params.get("text", "")) or []
        out = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                diag = {
                    "line": max(0, int(item.get("line", 0))),
                    "col": max(0, int(item.get("col", 0))),
                    "severity": str(item.get("severity", "warning"))
                                .lower(),
                    "message": str(item.get("message", ""))[:500],
                    "code": str(item.get("code", ""))[:40],
                }
            except Exception:
                continue
            if diag["severity"] not in ("info", "warning", "error"):
                diag["severity"] = "warning"
            if not diag["message"]:
                continue
            out.append(diag)
            if len(out) >= 500:
                break
        return out

    if method == "add_ignore_word":
        fn = getattr(plugin, "add_ignore_word", None)
        if not callable(fn):
            raise RuntimeError("插件未实现方法: add_ignore_word")
        word = str(params.get("word") or "").strip()
        if not word or len(word) > 80:
            return False
        return bool(fn(word))

    if method == "menu_items":
        fn = getattr(plugin, "menu_items", None)
        if not callable(fn):
            return []
        raw = fn() or []
        out = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()[:80]
            mid = str(item.get("id") or "").strip()[:64]
            path = str(item.get("path") or "").strip()[:120]
            if not label or not mid:
                continue
            out.append({"id": mid, "label": label, "path": path})
            if len(out) >= 50:
                break
        return out

    if method == "invoke_menu":
        fn = getattr(plugin, "invoke_menu", None)
        if not callable(fn):
            raise RuntimeError("插件未实现方法: invoke_menu")
        mid = str(params.get("id") or "").strip()
        if not mid or len(mid) > 64:
            return False
        return bool(fn(mid))

    if method == "status_text":
        fn = getattr(plugin, "status_text", None)
        if not callable(fn):
            return ""
        try:
            text = params.get("text") or ""
            try:
                return str(fn(text) or "")[:120]
            except TypeError:
                return str(fn() or "")[:120]
        except Exception:
            return ""

    if method == "config_schema":
        fn = getattr(plugin, "config_schema", None)
        if not callable(fn):
            return {}
        raw = fn() or {}
        if not isinstance(raw, dict):
            return {}
        out = {}
        for key, spec in raw.items():
            key = str(key)[:40]
            if not key or not isinstance(spec, dict):
                continue
            typ = str(spec.get("type") or "str")
            if typ not in ("str", "int", "float", "bool", "str_list"):
                typ = "str"
            item = {"type": typ,
                    "label": str(spec.get("label") or key)[:80]}
            if "default" in spec:
                item["default"] = spec["default"]
            out[key] = item
            if len(out) >= 30:
                break
        return out

    if method == "config_apply":
        fn = getattr(plugin, "on_config", None)
        if not callable(fn):
            raise RuntimeError("插件未实现方法: on_config")
        values = params.get("values") or {}
        if not isinstance(values, dict) or len(values) > 30:
            return False
        clean = {}
        for k, v in values.items():
            k = str(k)[:40]
            if isinstance(v, (str, int, float, bool)) or (
                    isinstance(v, list)
                    and all(isinstance(x, str) for x in v)):
                clean[k] = v
        return bool(fn(clean))

    if method == "completion":
        return fn(params.get("prefix", ""), params.get("language", ""),
                  params.get("filepath", ""))
    raise RuntimeError("未知方法: %s" % method)


def main():
    if len(sys.argv) < 2:
        print("usage: plugin_sandbox_worker.py <plugin_dir>",
              file=sys.stderr)
        return 2
    try:
        plugin = _load_plugin(os.path.abspath(sys.argv[1]))
    except Exception as e:
        sys.stdout.write(json.dumps(
            {"ready": False, "error": "%s: %s" % (type(e).__name__, e)},
            ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return 3
    sys.stdout.write(json.dumps({"ready": True},
                                ensure_ascii=False) + "\n")
    sys.stdout.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        rid = req.get("id")
        try:
            result = _handle(plugin, req.get("method", ""),
                             req.get("params") or {})
            resp = {"id": rid, "ok": True, "result": result}
        except Exception as e:
            resp = {"id": rid, "ok": False,
                    "error": "%s: %s" % (type(e).__name__, e)}
        try:
            sys.stdout.write(
                json.dumps(resp, ensure_ascii=False, default=str) + "\n")
            sys.stdout.flush()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())