"""plugin_sandbox._ready_event 测试（P1-A2）"""
import threading
import pytest


class TestReadyEvent:
    def test_handle_message_sets_event(self, qapp):
        """收到 READY 消息时，_ready_event 应被 set"""
        try:
            from infrastructure.plugin_sandbox import (
                PluginSandbox, SandboxConfig, MSG_TYPE_READY
            )
        except ImportError:
            pytest.skip("plugin_sandbox 不可用")

        # 用 __new__ 绕过 __init__（避免真起进程）
        # 但我们需要一些内部状态
        # 更好的方式：构造最小实例
        sandbox = PluginSandbox.__new__(PluginSandbox)
        # 手动初始化最小状态
        sandbox._ready_event = threading.Event()
        sandbox._ready_ok = False
        sandbox._last_pong = 0.0
        sandbox.log_received = ...  # 需要信号... 麻烦