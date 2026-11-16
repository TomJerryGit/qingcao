# -*- coding: utf-8 -*-
"""v2.26 B3：高风险 API 仅可信插件可用"""

import pytest


class _Host:
    def run_command(self, command):
        return "ran"


def test_untrusted_plugin_cannot_use_high_risk():
    from core.plugin_host import CapabilityBroker
    from core.sandbox_rpc import RpcError

    broker = CapabilityBroker(["process"], _Host(), allow_high_risk=True, trusted=False)
    with pytest.raises(RpcError) as e:
        broker.dispatch("run_command", ["whoami"])
    assert "trusted" in e.value.message


def test_trusted_plugin_can_use_high_risk_with_confirmation():
    from core.plugin_host import CapabilityBroker

    broker = CapabilityBroker(["process"], _Host(), allow_high_risk=True, trusted=True)
    assert broker.dispatch("run_command", ["whoami"]) == "ran"


def test_trusted_but_not_allowed_still_denied():
    from core.plugin_host import CapabilityBroker
    from core.sandbox_rpc import RpcError

    broker = CapabilityBroker(["process"], _Host(), allow_high_risk=False, trusted=True)
    with pytest.raises(RpcError):
        broker.dispatch("run_command", ["whoami"])
