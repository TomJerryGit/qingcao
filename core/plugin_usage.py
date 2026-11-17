# -*- coding: utf-8 -*-
"""插件使用统计（本地、隐私安全）。

仅记录插件名/计数/时间戳，不记录文件路径、文本或任何用户内容；
默认启用，可通过环境变量 QINGCAO_PLUGIN_USAGE=0 关闭。
"""

import io
import json
import os
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_PATH = os.path.join(ROOT, "data", "plugin_usage.json")
_PATH = None


def _path():
    return _PATH or _DEFAULT_PATH


def set_path(path):
    global _PATH
    _PATH = path


def enabled():
    return os.environ.get("QINGCAO_PLUGIN_USAGE", "1") != "0"


def _load():
    try:
        return json.load(io.open(_path(), encoding="utf-8"))
    except Exception:
        return {"version": 1, "plugins": {}}


def _save(data):
    try:
        path = _path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        io.open(tmp, "w", encoding="utf-8", newline="\n").write(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        )
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def record(plugin_name, event="activate"):
    if not enabled():
        return False
    name = str(plugin_name or "").strip()[:60]
    if not name or event not in ("activate", "deactivate"):
        return False
    data = _load()
    plugins = data.setdefault("plugins", {})
    rec = plugins.setdefault(
        name,
        {
            "activations": 0,
            "deactivations": 0,
            "first_seen": time.time(),
        },
    )
    rec["activations"] = int(rec.get("activations") or 0) + (1 if event == "activate" else 0)
    rec["deactivations"] = int(rec.get("deactivations") or 0) + (1 if event == "deactivate" else 0)
    rec["last_" + event] = time.time()
    return _save(data)


def snapshot():
    return _load().get("plugins") or {}


def reset():
    return _save({"version": 1, "plugins": {}})
