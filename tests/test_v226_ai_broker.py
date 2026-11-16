# -*- coding: utf-8 -*-
"""v2.26 B3：AI 网络宿主代理"""

import json

import pytest


def test_ai_transport_used_for_non_stream(monkeypatch):
    from core.ai_client import AIClient

    calls = {}

    def transport(**kwargs):
        calls.update(kwargs)
        return {"status": 200, "text": json.dumps({"choices": [{"message": {"content": "hi"}}]})}

    AIClient.set_http_transport(transport)
    try:
        client = AIClient(api_key="x")
        resp = client._make_request("https://api.example.com/chat", {}, {"a": 1})
        assert resp.status_code == 200 and resp.json()["choices"]
        assert calls["url"].startswith("https://api.example.com")
    finally:
        AIClient.set_http_transport(None)


def test_stream_rejected_when_transport_active():
    from core.ai_client import AIClient, AIClientError

    AIClient.set_http_transport(lambda **kwargs: {"status": 200, "text": "{}"})
    try:
        client = AIClient(api_key="x")
        with pytest.raises(AIClientError):
            client.chat_stream(prompt="x")
    finally:
        AIClient.set_http_transport(None)


def test_plugin_api_has_ai_http_request():
    src = open("app/plugin_api_data.py", encoding="utf-8").read()
    assert "def ai_http_request" in src


def test_broker_ai_http_permission():
    from core.plugin_host import CapabilityBroker
    from core.sandbox_rpc import RpcError

    class Host:
        def ai_http_request(self, *a, **k):
            return {"status": 200, "text": "{}"}

    broker = CapabilityBroker([], Host(), trusted=True)
    with pytest.raises(RpcError):
        broker.dispatch("ai_http_request", ["https://x", {}, None, 10])
    ok = CapabilityBroker(["network"], Host(), trusted=True)
    assert ok.dispatch("ai_http_request", ["https://x", {}, None, 10])["status"] == 200
