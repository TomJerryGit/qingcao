# -*- coding: utf-8 -*-
"""v2.26 P1：AI 超时/取消回归 + 插件文件体量守卫"""

import os
import types

import pytest
import requests


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Resp:
    status_code = 200
    text = "ok"
    content = b"ok"

    def json(self):
        return {"choices": [{"message": {"content": "hi"}}]}

    def raise_for_status(self):
        return None


def test_make_request_passes_timeout(monkeypatch):
    from core.ai_client import AIClient

    seen = {}

    def fake_post(url, **kwargs):
        seen.update(kwargs)
        return _Resp()

    monkeypatch.setattr(requests, "post", fake_post)
    client = AIClient(api_key="x", timeout=7)
    client._make_request("https://api.example.com", {"Authorization": "x"}, {"a": 1})
    assert seen.get("timeout") == 7


def test_make_request_timeout_raises(monkeypatch):
    from core.ai_client import AIClient, AIClientError

    def fake_post(url, **kwargs):
        raise requests.Timeout("timeout")

    monkeypatch.setattr(requests, "post", fake_post)
    client = AIClient(api_key="x", timeout=1)
    with pytest.raises(AIClientError):
        client._make_request("https://api.example.com", {}, {})


def test_plugin_files_within_architecture_limit():
    """ai_assistant/python_debugger 的每个文件必须 ≤1,300 行（R2 门禁）。"""
    for base in ("plugins/ai_assistant", "plugins/python_debugger"):
        for dp, _dn, files in os.walk(os.path.join(ROOT, base)):
            for f in files:
                if not f.endswith(".py"):
                    continue
                p = os.path.join(dp, f)
                n = sum(1 for _ in open(p, encoding="utf-8"))
                assert n <= 1300, "%s = %d 行（>1,300）" % (p, n)
