# -*- coding: utf-8 -*-
"""插件宿主监督者（B0 原型）：spawn 子进程、握手、能力代理转发。"""

import json
import os
import subprocess
import sys
import threading

from core import sandbox_rpc as rpc
from core.plugin_host import CapabilityBroker


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PluginHostError(RuntimeError):
    pass


def load_manifest(plugin_dir):
    try:
        return json.load(open(os.path.join(plugin_dir, "plugin.json"), encoding="utf-8"))
    except Exception:
        return {}


class PluginProcess:
    """管理单个插件子进程；主进程侧执行权限校验。"""

    def __init__(self, plugin_dir, host_api, timeout=10.0, allow_high_risk=False, policy=None):
        self.plugin_dir = os.path.abspath(plugin_dir)
        self.manifest = load_manifest(self.plugin_dir)
        self.permissions = self.manifest.get("permissions", [])
        self.broker = CapabilityBroker(self.permissions, host_api, allow_high_risk, policy)
        self.timeout = timeout
        self.proc = None
        self._thread = None
        self._hello = threading.Event()
        self._activated = threading.Event()
        self._dead = threading.Event()
        self._error = None
        self.logs = []
        self._stopping = False
        self._reply_lock = threading.Lock()
        self._pending = {}
        self._next_id = 1

    # ---------- 生命周期 ----------
    def start(self):
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONPATH"] = ROOT + os.pathsep + env.get("PYTHONPATH", "")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "core.plugin_host", self.plugin_dir],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=ROOT,
            env=env,
        )
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
        self._wait(self._hello, "handshake")
        # 同意握手并放行激活
        self._send(rpc.response(0, {"ok": True}))
        self._send(rpc.notification("host.ready"))
        self._wait(self._activated, "activate")
        return self

    def stop(self):
        self._stopping = True
        if self.proc is None:
            return
        try:
            self._send(rpc.notification("host.shutdown"))
        except Exception:
            pass
        try:
            self.proc.wait(timeout=2)
        except Exception:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except Exception:
                self.proc.kill()
        self._dead.set()

    def is_alive(self):
        return self.proc is not None and self.proc.poll() is None

    def request_child(self, method, params=None, timeout=None):
        """主进程 → 子进程请求（用于 invoke_callback 等）。"""
        req_id = self._next_id
        self._next_id += 1
        ev = threading.Event()
        box = {"response": None, "event": ev}
        self._pending[req_id] = box
        self._send(rpc.request(method, params or {}, req_id))
        if not ev.wait(timeout if timeout is not None else self.timeout):
            self._pending.pop(req_id, None)
            raise rpc.RpcError(rpc.ERROR_TIMEOUT, "child request timeout")
        msg = box["response"] or {}
        if "error" in msg:
            err = msg["error"]
            raise rpc.RpcError(err.get("code", -32000), err.get("message", "error"))
        return msg.get("result")

    def invoke_callback(self, callback_id, *args):
        return self.request_child("host.callback", {"id": callback_id, "args": list(args)})

    # ---------- 内部 ----------
    def _wait(self, event, stage):
        if not event.wait(self.timeout):
            self.stop()
            if self._error:
                raise PluginHostError("%s failed: %s" % (stage, self._error))
            raise PluginHostError("%s timeout" % stage)
        if self._error:
            raise PluginHostError("%s failed: %s" % (stage, self._error))

    def _send(self, obj):
        if self.proc is None or self.proc.stdin is None:
            raise PluginHostError("plugin host not running")
        with self._reply_lock:
            self.proc.stdin.write(rpc.encode(obj))
            self.proc.stdin.flush()

    def _reader(self):
        try:
            for line in self.proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = rpc.decode(line)
                except Exception:
                    continue
                self._dispatch(msg)
        except Exception as e:
            self._error = str(e)
        finally:
            self._dead.set()
            if not self._stopping and self._error is None:
                self._error = "plugin host exited (rc=%s)" % (
                    self.proc.poll() if self.proc else "?"
                )
            self._hello.set()
            self._activated.set()

    def _dispatch(self, msg):
        if "id" in msg and "method" not in msg:
            box = self._pending.pop(msg.get("id"), None)
            if box is not None:
                box["response"] = msg
                box["event"].set()
            return
        method = msg.get("method")
        if method == "host.hello":
            self._hello.set()
            return
        if method == "host.activated":
            self._activated.set()
            return
        if method == "plugin.log":
            params = msg.get("params") or {}
            self.logs.append((params.get("level", "info"), params.get("message", "")))
            return
        if method == "api.call":
            params = msg.get("params") or {}
            req_id = msg.get("id")
            try:
                result = self.broker.dispatch(params.get("name", ""), params.get("args", []))
                self._send(rpc.response(req_id, result))
            except rpc.RpcError as e:
                self._send(rpc.error(req_id, e.code, e.message))
            except Exception as e:
                self._send(rpc.error(req_id, -32000, str(e)))
