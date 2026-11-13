# -*- coding: utf-8 -*-
"""v2.26 P2：条件断点 + 监视表达式"""

import queue
import types


def _fake_frame(path="f.py", line=3):
    return types.SimpleNamespace(
        f_code=types.SimpleNamespace(co_filename=path, co_name="fn"),
        f_lineno=line,
        f_globals={},
        f_locals={},
    )


def _debugger():
    from plugins.python_debugger.driver import JsonDebugger

    dbg = JsonDebugger(queue.Queue())
    dbg.canonic = lambda p: p
    dbg.break_here = lambda frame: True
    dbg.MODE_STEP = "step"
    return dbg


def test_condition_false_skips_breakpoint(monkeypatch):
    dbg = _debugger()
    dbg._conditions = {("f.py", 3): "i == 2"}
    dbg.safe_eval = lambda frame, expr: False
    dbg._mode = "continue"
    assert dbg._should_stop(_fake_frame()) is False


def test_condition_true_stops(monkeypatch):
    dbg = _debugger()
    dbg._conditions = {("f.py", 3): "i == 2"}
    dbg.safe_eval = lambda frame, expr: True
    dbg._mode = "continue"
    assert dbg._should_stop(_fake_frame()) is True


def test_session_payload_includes_conditions_watches():
    from plugins.python_debugger.session import DebugSession

    captured = {}
    sess = DebugSession()
    sess.send = lambda cmd: captured.update(cmd) or True
    sess.set_breakpoints({"a.py": [1]}, conditions={"a.py": {2: "x > 0"}}, watches=["x"])
    assert captured["cmd"] == "set_breakpoints"
    assert captured["conditions"] == {"a.py": {2: "x > 0"}}
    assert captured["watches"] == ["x"]


def test_plugin_has_conditional_and_watch_ui():
    src = open("plugins/python_debugger/__init__.py", encoding="utf-8").read()
    for text in ("设置条件断点", "添加监视表达式", "清除监视", "_conditions", "_watches"):
        assert text in src
