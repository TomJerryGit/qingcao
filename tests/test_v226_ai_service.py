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


def test_sessions_isolated_history():
    from core.ai_service import AIService

    class C:
        def __init__(self):
            self.seen = []

        def chat(self, prompt, system="", messages=None, use_history=False, **kwargs):
            self.seen.append(list(messages or []))
            return "ok"

    c = C()
    svc = AIService(client=c)
    svc.run("a", session="s1")
    svc.run("b", session="s2")
    svc.run("c", session="s1")
    assert len(c.seen[2]) == 3  # s1 历史 2 条 + 本轮 user
    assert c.seen[1] == [{"role": "user", "content": "b"}]
    svc.reset_history("s1")
    svc.run("d", session="s1")
    assert len(c.seen[-1]) == 1
