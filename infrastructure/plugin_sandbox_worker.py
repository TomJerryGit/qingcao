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
        raise RuntimeError("插件未实现方法: %s" % method)
    if method == "symbols":
        return fn(params.get("text", ""), params.get("filepath", ""),
                  params.get("language", ""))
    if method == "hover":
        return fn(params.get("line", 0), params.get("col", 0),
                  params.get("filepath", ""), params.get("language", ""))
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