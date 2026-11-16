# -*- coding: utf-8 -*-
"""调试器宿主服务（B3-D1）：RPC schema + DebugService 骨架。

默认关闭：QINGCAO_DEBUGGER_HOST=1 时启用；插件通过 RPC 控制，
会话仍复用现有 DebugSession（被调试代码在 driver 子进程）。
"""

import os

from PyQt5.QtCore import QObject, pyqtSignal


RPC_SCHEMA = {
    "debug.start": {
        "params": {"script": "str", "args": "list", "cwd": "str?"},
        "returns": {"ok": "bool", "error": "str?"},
    },
    "debug.stop": {"params": {}, "returns": {"ok": "bool"}},
    "debug.set_breakpoints": {
        "params": {"files": "dict"},
        "returns": {"ok": "bool", "count": "int"},
    },
    "debug.continue": {"params": {}, "returns": {"ok": "bool"}},
    "debug.step": {
        "params": {"kind": "over|into|out"},
        "returns": {"ok": "bool"},
    },
    "debug.locals": {"params": {}, "returns": {"ok": "bool"}},
    "debug.stack": {"params": {}, "returns": {"ok": "bool"}},
    "debug.eval": {
        "params": {"expr": "str"},
        "returns": {"ok": "bool", "value": "any"},
    },
}

EVENTS = ("debug.break", "debug.locals", "debug.stack", "debug.error", "debug.exit")

HIGH_RISK_PERMISSION = "debugger"


def host_enabled():
    return os.environ.get("QINGCAO_DEBUGGER_HOST") == "1"


class DebugRpcError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def validate_request(method, params):
    spec = RPC_SCHEMA.get(method)
    if spec is None:
        raise DebugRpcError(-32601, "unknown debug method: %s" % method)
    expected = spec["params"]
    values = dict(params or {})
    for key in values:
        if key not in expected:
            raise DebugRpcError(-32602, "unexpected param: %s" % key)
    for key, typ in expected.items():
        if typ.endswith("?") or typ.endswith("|over|into|out"):
            continue
        if key in values and typ == "str" and not isinstance(values[key], str):
            raise DebugRpcError(-32602, "param %s must be str" % key)
        if key in values and typ == "list" and not isinstance(values[key], list):
            raise DebugRpcError(-32602, "param %s must be list" % key)
    if method == "debug.start" and not str(values.get("script") or "").strip():
        raise DebugRpcError(-32602, "start requires script")
    if method == "debug.step" and values.get("kind") not in ("over", "into", "out"):
        raise DebugRpcError(-32602, "step kind must be over/into/out")
    return values


class DebugService(QObject):
    """宿主侧调试会话服务；默认仅 trusted 插件可调用。"""

    event = pyqtSignal(dict)

    def __init__(self, trusted=False, session_factory=None, parent=None):
        super().__init__(parent)
        self.trusted = bool(trusted)
        self._factory = session_factory
        self.session = None
        self.state = "idle"
        self.last_break = None
        self.last_locals = None
        self.last_stack = None
        self.last_eval = None

    def _require_trusted(self):
        if not self.trusted:
            raise DebugRpcError(-32001, "debugger requires trusted plugin")

    def handle(self, method, params=None):
        self._require_trusted()
        values = validate_request(method, params)
        if method == "debug.start":
            return self._start(values)
        if method == "debug.stop":
            return self._stop()
        if self.session is None:
            raise DebugRpcError(-32002, "no debug session")
        if method == "debug.set_breakpoints":
            files = values.get("files") or {}
            self.session.set_breakpoints(files)
            return {"ok": True, "count": len(files)}
        if method == "debug.continue":
            self.state = "running"
            self.session.continue_()
            return {"ok": True}
        if method == "debug.step":
            self.state = "running"
            getattr(self.session, "step_" + values["kind"])()
            return {"ok": True}
        if method == "debug.locals":
            self.session.request_locals()
            return {"ok": True}
        if method == "debug.stack":
            self.session.request_stack()
            return {"ok": True}
        if method == "debug.eval":
            self.session.evaluate(values["expr"])
            return {"ok": True}
        raise DebugRpcError(-32601, method)

    def _start(self, values):
        if self.session is not None:
            self._stop()
        try:
            if self._factory is not None:
                session = self._factory()
            else:
                from plugins.python_debugger.session import DebugSession

                session = DebugSession()
        except Exception as e:
            return {"ok": False, "error": str(e)}
        self.session = session
        self._wire(session)
        self.state = "starting"
        try:
            ok = session.start(
                values["script"], values.get("args") or [], values.get("cwd") or None
            )
        except Exception as e:
            self.session = None
            self.state = "idle"
            return {"ok": False, "error": str(e)}
        if not ok:
            self.session = None
            self.state = "idle"
            return {"ok": False, "error": "session.start failed"}
        self.state = "running"
        return {"ok": True}

    def _stop(self):
        if self.session is not None:
            try:
                self.session.stop()
            except Exception:
                pass
        self.session = None
        self.state = "idle"
        return {"ok": True}

    def _wire(self, session):
        try:
            session.break_hit.connect(self._on_break)
            session.finished.connect(self._on_finished)
            session.failed.connect(self._on_failed)
            session.output_received.connect(self._on_output)
            session.event_received.connect(self._on_event)
        except Exception:
            pass

    def _on_break(self, filepath, line):
        self.state = "paused"
        payload = {"file": str(filepath), "line": int(line), "reason": "break"}
        self.last_break = payload
        self.event.emit({"event": "debug.break", "data": payload})

    def _on_finished(self, code):
        self.state = "idle"
        self.event.emit({"event": "debug.exit", "data": {"code": int(code)}})
        self.session = None

    def _on_failed(self, message):
        self.event.emit({"event": "debug.error", "data": {"message": str(message)}})

    def _on_event(self, payload):
        if not isinstance(payload, dict) or payload.get("event") != "result":
            return
        kind = payload.get("kind")
        value = payload.get("value")
        if kind == "locals":
            self.last_locals = value
            self.event.emit({"event": "debug.locals", "data": {"values": value}})
        elif kind == "stack":
            self.last_stack = value
            self.event.emit({"event": "debug.stack", "data": {"frames": value}})
        elif kind == "eval":
            self.last_eval = value
            self.event.emit({"event": "debug.eval", "data": {"value": value}})

    def _on_output(self, stream, text):
        self.event.emit(
            {"event": "debug.output", "data": {"stream": str(stream), "text": str(text)}}
        )

    def is_running(self):
        return self.session is not None and self.state in ("starting", "running", "paused")

    def shutdown(self):
        """退出/停用时的幂等清理，保证无孤儿调试进程。"""
        if self.session is None:
            self.state = "idle"
            return True
        return bool(self._stop().get("ok"))

    def _emit_break(self, payload):
        self.last_break = payload
        self.event.emit({"event": "debug.break", "data": payload})


_SERVICE = None


def get_debug_service():
    """宿主单例（仅用于宿主侧 PluginAPI；隔离插件经 broker 后续接入）。"""
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = DebugService(trusted=True)
    return _SERVICE
