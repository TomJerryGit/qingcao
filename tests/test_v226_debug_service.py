# -*- coding: utf-8 -*-
"""v2.26 B3-D1：DebugService RPC schema/骨架"""

import os

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _Session:
    def __init__(self):
        self.started = None
        self.stopped = False
        self.calls = []

    def start(self, script, args=None, cwd=None):
        self.started = (script, args, cwd)
        return True

    def stop(self):
        self.stopped = True

    def continue_(self):
        self.calls.append("continue")

    def step_over(self):
        self.calls.append("over")

    def step_into(self):
        self.calls.append("into")

    def step_out(self):
        self.calls.append("out")

    def request_locals(self):
        self.calls.append("locals")

    def request_stack(self):
        self.calls.append("stack")

    def evaluate(self, expr):
        self.calls.append(("eval", expr))
        return 42


def test_schema_covers_methods_and_events():
    from core.debug_service import EVENTS, RPC_SCHEMA

    assert "debug.start" in RPC_SCHEMA and "debug.eval" in RPC_SCHEMA
    assert "debug.break" in EVENTS


def test_untrusted_denied():
    from core.debug_service import DebugRpcError, DebugService

    with pytest.raises(DebugRpcError):
        DebugService(trusted=False).handle("debug.start", {"script": "a.py"})


def test_start_continue_stop_permission():
    from core.debug_service import DebugService

    svc = DebugService(trusted=True, session_factory=_Session)
    assert svc.handle("debug.start", {"script": "a.py", "args": ["x"]})["ok"]
    assert svc.handle("debug.continue")["ok"]
    assert svc.handle("debug.step", {"kind": "over"})["ok"]
    assert svc.handle("debug.locals")["ok"]
    assert svc.handle("debug.eval", {"expr": "1+1"})["value"] == 42
    assert svc.handle("debug.stop")["ok"]
    assert svc.session is None


def test_invalid_params():
    from core.debug_service import DebugRpcError, DebugService

    svc = DebugService(trusted=True, session_factory=_Session)
    with pytest.raises(DebugRpcError):
        svc.handle("debug.step", {"kind": "bad"})
    with pytest.raises(DebugRpcError):
        svc.handle("debug.nope", {})


def test_start_stop_real_session_no_orphan(tmp_path):
    from core.debug_service import DebugService

    script = tmp_path / "sleeper.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    svc = DebugService(trusted=True)
    try:
        result = svc.handle("debug.start", {"script": str(script)})
        assert result["ok"], result
        proc = svc.session._proc
        assert proc is not None and proc.poll() is None
        assert svc.is_running()
        assert svc.handle("debug.stop")["ok"]
        assert svc.session is None and not svc.is_running()
        proc.wait(timeout=10)
        assert proc.poll() is not None
    finally:
        svc.shutdown()


def test_start_failure_cleans_state(tmp_path):
    from core.debug_service import DebugService

    svc = DebugService(trusted=True)
    result = svc.handle("debug.start", {"script": str(tmp_path / "missing.py")})
    assert result["ok"] is False
    assert svc.session is None and svc.state == "idle"


def test_break_event_and_step_commands():
    from PyQt5.QtCore import QObject, pyqtSignal

    from core.debug_service import DebugService

    class SignalSession(_Session, QObject):
        break_hit = pyqtSignal(str, int)
        finished = pyqtSignal(int)
        failed = pyqtSignal(str)
        output_received = pyqtSignal(str, str)

        def __init__(self):
            QObject.__init__(self)
            _Session.__init__(self)

        def set_breakpoints(self, files):
            self.calls.append(("breakpoints", files))
            return True

    svc = DebugService(trusted=True, session_factory=SignalSession)
    events = []
    svc.event.connect(events.append)
    assert svc.handle("debug.start", {"script": "a.py"})["ok"]
    session = svc.session
    assert svc.handle("debug.set_breakpoints", {"files": {"a.py": [2]}})["count"] == 1
    session.break_hit.emit("a.py", 2)
    assert events and events[-1]["event"] == "debug.break"
    assert svc.state == "paused"
    assert svc.handle("debug.continue")["ok"]
    assert svc.handle("debug.step", {"kind": "into"})["ok"]
    assert "into" in session.calls
    session.finished.emit(0)
    assert svc.state == "idle" and svc.session is None
