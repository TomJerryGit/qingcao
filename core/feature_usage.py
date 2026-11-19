# -*- coding: utf-8 -*-
"""功能使用本地统计（匿名、可关闭、不采集内容）。"""

import io
import json
import os
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH = None


def set_path(path):
    global _PATH
    _PATH = path


def _path():
    return _PATH or os.path.join(ROOT, "data", "feature_usage.json")


def enabled():
    return os.environ.get("QINGCAO_FEATURE_USAGE", "1") != "0"


def _load():
    try:
        return json.load(io.open(_path(), encoding="utf-8"))
    except Exception:
        return {"version": 1, "actions": {}}


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


def record(name):
    if not enabled():
        return False
    name = str(name or "").strip()[:120]
    if not name:
        return False
    data = _load()
    actions = data.setdefault("actions", {})
    rec = actions.setdefault(name, {"count": 0, "last": 0})
    rec["count"] = int(rec.get("count") or 0) + 1
    rec["last"] = time.time()
    return _save(data)


def snapshot():
    return _load().get("actions") or {}


def top(n=10):
    rows = sorted(snapshot().items(), key=lambda kv: int(kv[1].get("count") or 0), reverse=True)
    return rows[: max(1, int(n))]


def low(n=10):
    rows = sorted(snapshot().items(), key=lambda kv: int(kv[1].get("count") or 0))
    return rows[: max(1, int(n))]


def instrument_action(action, name):
    try:
        action.setObjectName("usage:" + str(name)[:80])
        action.triggered.connect(lambda _=False, n=name: record(n))
        return True
    except Exception:
        return False
