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
        if method == "debug.continue":
            self.session.continue_()
            return {"ok": True}
        if method == "debug.step":
            getattr(self.session, "step_" + values["kind"])()
            return {"ok": True}
        if method == "debug.locals":
            self.session.request_locals()
            return {"ok": True}
        if method == "debug.stack":
            self.session.request_stack()
            return {"ok": True}
        if method == "debug.eval":
            result = self.session.evaluate(values["expr"])
            return {"ok": True, "value": result}
        raise DebugRpcError(-32601, method)

    def _start(self, values):
        if self.session is not None:
            self._stop()
        if self._factory is not None:
            session = self._factory()
        else:
            from plugins.python_debugger.session import DebugSession

            session = DebugSession()
        self.session = session
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

    def _emit_break(self, payload):
        self.last_break = payload
        self.event.emit({"event": "debug.break", "data": payload})
