# -*- coding: utf-8 -*-
"""v2.25 R1.3：插件网络白名单/限流/拒绝审计"""

import json
import os
import urllib.request

import pytest


class _FakeResp:
    status = 200
    headers = {"Content-Type": "text/plain"}

    def __init__(self, body=b"ok"):
        self._body = body

    def read(self, n=-1):
        return self._body[:n] if n and n > 0 else self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _broker(policy, perms=("network",), max_per_min=60):
    from core.plugin_host import CapabilityBroker

    class Host:
        pass

    b = CapabilityBroker(list(perms), Host(), policy=policy)
    b.NETWORK_MAX_PER_MIN = max_per_min
    return b


def test_network_whitelist_and_body(monkeypatch):
    from core.plugin_sandbox_policy import SandboxPolicy

    broker = _broker(SandboxPolicy([], ["api.example.com"]))
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10: _FakeResp(b"hello"))
    out = broker.http_request if hasattr(broker, "http_request") else None
    res = broker._http_request("https://api.example.com/x")
    assert res["status"] == 200 and "hello" in res["body"]


def test_network_denied_and_audited():
    from core.plugin_sandbox_policy import SandboxPolicy
    from core.sandbox_rpc import ERROR_PERMISSION_DENIED, RpcError

    broker = _broker(SandboxPolicy([], []))
    with pytest.raises(RpcError) as e:
        broker._http_request("https://evil.example.com/x")
    assert e.value.code == ERROR_PERMISSION_DENIED
    assert broker.network_denials and broker.network_denials[0]["reason"] == "host"


def test_network_rate_limited(monkeypatch):
    from core.plugin_sandbox_policy import SandboxPolicy
    from core.sandbox_rpc import ERROR_LIMIT, RpcError

    broker = _broker(SandboxPolicy([], ["api.example.com"]), max_per_min=2)
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=10: _FakeResp())
    broker._http_request("https://api.example.com/1")
    broker._http_request("https://api.example.com/2")
    with pytest.raises(RpcError) as e:
        broker._http_request("https://api.example.com/3")
    assert e.value.code == ERROR_LIMIT
    assert broker.network_denials[-1]["reason"] == "rate"


def test_child_request_denied_end_to_end(tmp_path):
    from core.plugin_supervisor import PluginProcess

    d = tmp_path / "net_plugin"
    d.mkdir()
    (d / "plugin.json").write_text(
        json.dumps({"name": "net_plugin", "version": "1.0.0", "permissions": ["network"]}),
        encoding="utf-8",
    )
    (d / "__init__.py").write_text(
        """
class Plugin:
    def on_activate(self):
        try:
            self.api.http_request("https://evil.example.com/x")
        except Exception as e:
            self.api.log("denied:%s" % e)
    def on_deactivate(self):
        pass
""",
        encoding="utf-8",
    )

    class Host:
        pass

    proc = PluginProcess(str(d), Host(), timeout=15)
    try:
        proc.start()
        assert proc.broker.network_denials
        assert any("denied" in m for _l, m in proc.logs)
    finally:
        proc.stop()
