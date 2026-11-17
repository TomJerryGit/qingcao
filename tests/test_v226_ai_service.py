# -*- coding: utf-8 -*-
"""v2.26 B3：AI 宿主服务/ broker ai_run"""

import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _Client:
    def chat(self, prompt, system="", use_history=False, **kwargs):
        return "reply:" + prompt


def test_ai_service_run_with_injected_client():
    from core.ai_service import AIService

    svc = AIService(client=_Client())
    out = svc.run("hello", "sys")
    assert out["ok"] and out["text"] == "reply:hello"
    assert svc.run("")["ok"] is False


def test_broker_ai_run_permission():
    from core.plugin_host import CapabilityBroker
    from core.sandbox_rpc import RpcError

    class Host:
        def ai_run(self, prompt, system="", max_tokens=None):
            return {"ok": True, "text": "x"}

    broker = CapabilityBroker([], Host(), trusted=True)
    with pytest.raises(RpcError):
        broker.dispatch("ai_run", ["p", "", None])
    ok = CapabilityBroker(["network"], Host(), trusted=True)
    assert ok.dispatch("ai_run", ["p", "", None])["text"] == "x"


def test_broker_has_ai_run():
    from core.plugin_host import METHOD_PERMISSIONS

    assert METHOD_PERMISSIONS.get("ai_run") == "network"
