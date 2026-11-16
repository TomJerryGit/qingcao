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
    assert svc.handle("debug.eval", {"expr": "1+1"})["ok"]
    assert ("eval", "1+1") in svc.session.calls
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


def test_result_events_for_locals_stack_eval():
    from PyQt5.QtCore import QObject, pyqtSignal

    from core.debug_service import DebugService

    class S(_Session, QObject):
        break_hit = pyqtSignal(str, int)
        finished = pyqtSignal(int)
        failed = pyqtSignal(str)
        output_received = pyqtSignal(str, str)
        event_received = pyqtSignal(dict)

        def __init__(self):
            QObject.__init__(self)
            _Session.__init__(self)

        def set_breakpoints(self, files):
            return True

    svc = DebugService(trusted=True, session_factory=S)
    events = []
    svc.event.connect(events.append)
    svc.handle("debug.start", {"script": "a.py"})
    session = svc.session
    session.event_received.emit({"event": "result", "kind": "locals", "value": {"x": 1}})
    session.event_received.emit({"event": "result", "kind": "stack", "value": [{"name": "f"}]})
    session.event_received.emit({"event": "result", "kind": "eval", "value": 42})
    names = [e["event"] for e in events]
    assert "debug.locals" in names and "debug.stack" in names
    assert "debug.eval" in names
    assert svc.last_locals == {"x": 1} and svc.last_eval == 42
    svc.shutdown()


def test_real_breakpoint_with_process_events(tmp_path):
    import time

    from PyQt5.QtWidgets import QApplication

    from core.debug_service import DebugService

    app = QApplication.instance() or QApplication([])
    script = tmp_path / "bp2.py"
    script.write_text(
        "import time\nx = 0\nfor i in range(10):\n    x = i\n    time.sleep(0.05)\n",
        encoding="utf-8",
    )
    svc = DebugService(trusted=True)
    try:
        assert svc.handle("debug.start", {"script": str(script)})["ok"]
        svc.handle("debug.set_breakpoints", {"files": {str(script): [3]}})
        svc.handle("debug.continue")
        deadline = time.time() + 10
        while time.time() < deadline and svc.last_break is None:
            app.processEvents()
            time.sleep(0.02)
        assert svc.last_break is not None, "未命中真实断点"
        svc.handle("debug.locals")
        deadline = time.time() + 8
        while time.time() < deadline and svc.last_locals is None:
            app.processEvents()
            time.sleep(0.02)
        assert svc.last_locals is not None
        assert "x" in svc.last_locals or "i" in svc.last_locals
    finally:
        svc.shutdown()


def test_factory_failure_and_stop_failure():
    from core.debug_service import DebugService

    def boom():
        raise RuntimeError("factory boom")

    svc = DebugService(trusted=True, session_factory=boom)
    result = svc.handle("debug.start", {"script": "a.py"})
    assert result["ok"] is False and svc.session is None

    class BadStop(_Session):
        def stop(self):
            raise RuntimeError("stop boom")

    svc2 = DebugService(trusted=True, session_factory=BadStop)
    assert svc2.handle("debug.start", {"script": "a.py"})["ok"]
    assert svc2.shutdown() is True
    assert svc2.session is None


def test_failed_signal_emits_error():
    from PyQt5.QtCore import QObject, pyqtSignal

    from core.debug_service import DebugService

    class S(_Session, QObject):
        break_hit = pyqtSignal(str, int)
        finished = pyqtSignal(int)
        failed = pyqtSignal(str)
        output_received = pyqtSignal(str, str)
        event_received = pyqtSignal(dict)

        def __init__(self):
            QObject.__init__(self)
            _Session.__init__(self)

    svc = DebugService(trusted=True, session_factory=S)
    events = []
    svc.event.connect(events.append)
    svc.handle("debug.start", {"script": "a.py"})
    svc.session.failed.emit("boom")
    assert events and events[-1]["event"] == "debug.error"
    assert events[-1]["data"]["message"] == "boom"
