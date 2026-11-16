# -*- coding: utf-8 -*-
"""AI HTTP 宿主代理（B3 试点）：网络请求从插件代码移到宿主受控函数。"""

import json
import urllib.parse
import urllib.request


class AIHTTPError(RuntimeError):
    pass


def request_json(url, headers=None, json_data=None, timeout=60):
    """POST JSON，返回 {status, text, json}；仅允许 http/https。"""
    parsed = urllib.parse.urlparse(str(url))
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise AIHTTPError("invalid AI URL: %s" % url)
    data = None
    hdrs = dict(headers or {})
    if json_data is not None:
        data = json.dumps(json_data).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(str(url), data=data, method="POST", headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(4 * 1024 * 1024)
            text = raw.decode("utf-8", "replace")
            return {"status": getattr(resp, "status", 200), "text": text}
    except Exception as e:
        raise AIHTTPError("AI HTTP 请求失败: %s" % e)
