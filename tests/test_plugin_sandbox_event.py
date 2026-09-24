# -*- coding: utf-8 -*-
"""plugin_sandbox 事件处理测试（P1-A2 / P1-3）

覆盖:
    - _handle_message 对 READY 消息的处理
      （P1-A2: 就绪信号由接收线程处理，主线程通过 Event 等待）
    - _handle_message 对 LOG 消息的处理
    - _handle_message 对 EVENT 消息的处理
    - _handle_message 对 PONG 消息的处理
    - _handle_message 对未知消息的容错
    - _wait_for_ready 的超时与就绪行为

设计说明:
    - 用真实 PluginSandbox 实例，但不调用 start()，因此不
      启动子进程。安全且快。
    - READY 相关的状态（_ready_event / _ready_ok）只在 start()
      里创建，本测试在 fixture 里手动补上。
    - 信号派发是同线程同步的（Qt.AutoConnection），
      不需要 qtbot.waitSignal。
"""
import threading
import time

import pytest


# ============================================================
# Fixture
# ============================================================
@pytest.fixture
def sandbox(qapp):
    """
    创建一个不启动子进程的 PluginSandbox 实例。

    说明:
        PluginSandbox.__init__ 不会启动进程（进程在 start() 里），
        因此直接实例化是安全的。但 __init__ 不创建 _ready_event /
        _ready_ok，这里手动补上，模拟 start() 之后的状态。
    """
    try:
        from infrastructure.plugin_sandbox import (
            PluginSandbox, SandboxConfig,
        )
    except ImportError:
        pytest.skip("plugin_sandbox 不可用")

    sb = PluginSandbox("/tmp/fake_plugin", SandboxConfig())

    # 补上 start() 才会创建的属性
    sb._ready_event = threading.Event()
    sb._ready_ok = False

    yield sb

    # 清理定时器
    try:
        sb._heartbeat_timer.stop()
    except Exception:
        pass
    try:
        sb._restart_timer.stop()
    except Exception:
        pass


# ============================================================
# READY 消息（P1-A2 核心）
# ============================================================
class TestReadyEvent:
    """READY 消息应触发 _ready_event.set() 并记录成功状态"""

    def test_ready_success_sets_event(self, sandbox):
        from infrastructure.plugin_sandbox import MSG_TYPE_READY

        # 前置：未就绪
        assert not sandbox._ready_event.is_set()
        assert sandbox._ready_ok is False

        # 派发 READY 消息
        sandbox._handle_message({
            'type': MSG_TYPE_READY,
            'success': True,
        })

        # 断言
        assert sandbox._ready_ok is True
        assert sandbox._ready_event.is_set()

    def test_ready_failure_sets_event_but_ok_false(self, sandbox):
        """即使 success=False，也要 set() 让主线程解除等待"""
        from infrastructure.plugin_sandbox import MSG_TYPE_READY

        sandbox._handle_message({
            'type': MSG_TYPE_READY,
            'success': False,
        })

        assert sandbox._ready_ok is False
        assert sandbox._ready_event.is_set()

    def test_wait_for_ready_returns_after_event(self, sandbox):
        """_wait_for_ready 应在 _ready_event 被 set 后立即返回"""
        from infrastructure.plugin_sandbox import MSG_TYPE_READY

        # 后台线程延迟触发 READY（模拟接收线程）
        def delayed_ready():
            time.sleep(0.05)
            sandbox._handle_message({
                'type': MSG_TYPE_READY,
                'success': True,
            })

        t = threading.Thread(target=delayed_ready, daemon=True)
        t.start()

        start = time.time()
        ok = sandbox._wait_for_ready(timeout=2.0)
        elapsed = time.time() - start

        assert ok is True
        assert elapsed < 1.0, f"等待过久: {elapsed:.3f}s"

    def test_wait_for_ready_timeout(self, sandbox):
        """未收到 READY 时应超时返回 False"""
        start = time.time()
        ok = sandbox._wait_for_ready(timeout=0.2)
        elapsed = time.time() - start

        assert ok is False
        assert 0.15 < elapsed < 1.0, f"超时行为异常: {elapsed:.3f}s"

    def test_wait_for_ready_without_event_attr(self, qapp):
        """_ready_event 未初始化时应安全返回 False（防御）"""
        try:
            from infrastructure.plugin_sandbox import (
                PluginSandbox, SandboxConfig,
            )
        except ImportError:
            pytest.skip("plugin_sandbox 不可用")

        sb = PluginSandbox("/tmp/fake", SandboxConfig())
        # 不补 _ready_event
        try:
            result = sb._wait_for_ready(timeout=0.1)
            assert result is False
        finally:
            try:
                sb._heartbeat_timer.stop()
                sb._restart_timer.stop()
            except Exception:
                pass


# ============================================================
# LOG 消息
# ============================================================
class TestLogMessage:
    """LOG 消息应触发 log_received 信号"""

    def test_log_emits_signal(self, sandbox):
        from infrastructure.plugin_sandbox import MSG_TYPE_LOG

        received = []
        sandbox.log_received.connect(
            lambda level, text: received.append((level, text))
        )

        sandbox._handle_message({
            'type': MSG_TYPE_LOG,
            'level': 'error',
            'message': 'test error',
        })

        assert len(received) == 1
        assert received[0] == ('error', 'test error')

    def test_log_default_level_is_info(self, sandbox):
        from infrastructure.plugin_sandbox import MSG_TYPE_LOG

        received = []
        sandbox.log_received.connect(
            lambda level, text: received.append((level, text))
        )

        sandbox._handle_message({
            'type': MSG_TYPE_LOG,
            'message': 'no level',
        })

        assert received[0][0] == 'info'

    def test_log_with_traceback_emits_output(self, sandbox):
        """error 级 + traceback → output_received 也应触发"""
        from infrastructure.plugin_sandbox import MSG_TYPE_LOG

        outputs = []
        sandbox.output_received.connect(
            lambda typ, text: outputs.append((typ, text))
        )

        sandbox._handle_message({
            'type': MSG_TYPE_LOG,
            'level': 'error',
            'message': 'crash',
            'traceback': 'Traceback (most recent call last): ...',
        })

        assert any(t[0] == 'traceback' for t in outputs)

    def test_info_with_traceback_no_output(self, sandbox):
        """info 级 + traceback → 不应触发 output_received"""
        from infrastructure.plugin_sandbox import MSG_TYPE_LOG

        outputs = []
        sandbox.output_received.connect(
            lambda typ, text: outputs.append((typ, text))
        )

        sandbox._handle_message({
            'type': MSG_TYPE_LOG,
            'level': 'info',
            'message': 'hello',
            'traceback': 'should be ignored',
        })

        assert len(outputs) == 0


# ============================================================
# EVENT 消息
# ============================================================
class TestEventMessage:
    """EVENT 消息应以 'event:<name>' 前缀转发"""

    def test_event_emits_output(self, sandbox):
        from infrastructure.plugin_sandbox import MSG_TYPE_EVENT

        outputs = []
        sandbox.output_received.connect(
            lambda typ, text: outputs.append((typ, text))
        )

        sandbox._handle_message({
            'type': MSG_TYPE_EVENT,
            'name': 'progress',
            'data': {'percent': 50},
        })

        assert len(outputs) == 1
        typ, text = outputs[0]
        assert typ == 'event:progress'
        assert '50' in text


# ============================================================
# PONG 消息
# ============================================================
class TestPongMessage:
    """PONG 消息应更新 _last_pong 时间戳"""

    def test_pong_updates_timestamp(self, sandbox):
        from infrastructure.plugin_sandbox import MSG_TYPE_PONG

        sandbox._last_pong = 0.0
        before = time.time()

        sandbox._handle_message({'type': MSG_TYPE_PONG})

        after = time.time()
        assert before <= sandbox._last_pong <= after


# ============================================================
# 未知消息
# ============================================================
class TestUnknownMessage:
    """未知消息类型应被静默忽略，不抛异常"""

    def test_unknown_type_no_exception(self, sandbox):
        sandbox._handle_message({'type': 'unknown_xyz'})

    def test_missing_type_no_exception(self, sandbox):
        sandbox._handle_message({})

    def test_none_type_no_exception(self, sandbox):
        sandbox._handle_message({'type': None})

    def test_empty_dict_no_exception(self, sandbox):
        sandbox._handle_message({})

    def test_unknown_log_level_passes_through(self, sandbox):
        """未知日志级别不应被过滤，应原样转发"""
        from infrastructure.plugin_sandbox import MSG_TYPE_LOG

        received = []
        sandbox.log_received.connect(
            lambda level, text: received.append((level, text))
        )

        sandbox._handle_message({
            'type': MSG_TYPE_LOG,
            'level': 'custom_level',
            'message': 'custom',
        })

        assert received[0] == ('custom_level', 'custom')