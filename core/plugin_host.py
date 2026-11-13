# -*- coding: utf-8 -*-
"""插件宿主（B0 原型）：在子进程内加载插件，通过 JSON-RPC 调用主进程能力。"""

import argparse
import importlib.util
import json
import os
import sys

from core.sandbox_rpc import (
    ERROR_LIMIT,
    ERROR_PERMISSION_DENIED,
    ERROR_TIMEOUT,
    RpcError,
    decode,
    encode,
    error,
    notification,
    request,
    response,
)


METHOD_PERMISSIONS = {
    "log": None,
    "get_current_text": "editor_read",
    "set_current_text": "editor_write",
    "show_message": "dialog",
    "add_menu": "dialog",
    "add_status_item": "dialog",
    "get_config": None,
    "set_config": None,
    "register_settings_schema": None,
    "read_file": "filesystem",
    "write_file": "filesystem",
    "register_remote_panel": "dialog",
    "show_remote_panel": "dialog",
    "http_request": "network",
    "register_hover_provider": "editor_read",
    "register_code_action_provider": "editor_write",
    "add_editor_context_menu": None,
    "run_command": "process",
    "run_python": "process",
}
HIGH_RISK = {"process", "terminal", "debugger"}


class CapabilityBroker:
    """主进程侧：按 manifest 权限校验并转发到宿主 API。"""

    NETWORK_MAX_PER_MIN = 60
    NETWORK_MAX_BYTES = 1024 * 1024

    def __init__(self, permissions, host_api, allow_high_risk=False, policy=None):
        self.permissions = set(permissions or [])
        self.host_api = host_api
        self.allow_high_risk = allow_high_risk
        self.policy = policy
        self._net_times = []
        self.network_denials = []

    def dispatch(self, name, args):
        perm = METHOD_PERMISSIONS.get(name)
        if name not in METHOD_PERMISSIONS:
            raise RpcError(-32601, "unknown api: %s" % name)
        if perm and perm not in self.permissions:
            raise RpcError(ERROR_PERMISSION_DENIED, "permission denied: %s" % perm)
        if perm in HIGH_RISK and not self.allow_high_risk:
            raise RpcError(ERROR_PERMISSION_DENIED, "high-risk api disabled: %s" % name)
        if name in ("read_file", "write_file"):
            path = (args or [None])[0]
            if self.policy is None or not self.policy.check_path(path):
                raise RpcError(ERROR_PERMISSION_DENIED, "path denied: %s" % path)
        if name == "http_request":
            return self._http_request(*(args or []))
        try:
            return getattr(self.host_api, name)(*(args or []))
        except RpcError:
            raise
        except Exception as e:
            raise RpcError(-32000, "host api failed: %s" % e)

    def _http_request(self, url, method="GET", headers=None, data=None, timeout=10):
        import time
        import urllib.parse
        import urllib.request

        try:
            parsed = urllib.parse.urlparse(str(url))
        except Exception:
            parsed = None
        host = (parsed.hostname or "") if parsed else ""
        if (
            parsed is None
            or parsed.scheme not in ("http", "https")
            or self.policy is None
            or not self.policy.check_host(host)
        ):
            self.network_denials.append({"url": str(url), "reason": "host", "host": host})
            raise RpcError(ERROR_PERMISSION_DENIED, "domain denied: %s" % host)
        now = time.time()
        self._net_times = [t for t in self._net_times if now - t < 60]
        if len(self._net_times) >= self.NETWORK_MAX_PER_MIN:
            self.network_denials.append({"url": str(url), "reason": "rate"})
            raise RpcError(ERROR_LIMIT, "network rate limit exceeded")
        self._net_times.append(now)
        body = None
        if data is not None:
            body = data.encode("utf-8") if isinstance(data, str) else data
        req = urllib.request.Request(
            str(url), data=body, method=str(method or "GET").upper(), headers=dict(headers or {})
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(self.NETWORK_MAX_BYTES + 1)
                truncated = len(raw) > self.NETWORK_MAX_BYTES
                return {
                    "status": getattr(resp, "status", 200),
                    "headers": dict(getattr(resp, "headers", {}).items()),
                    "body": raw[: self.NETWORK_MAX_BYTES].decode("utf-8", "replace"),
                    "truncated": truncated,
                }
        except Exception as e:
            self.network_denials.append({"url": str(url), "reason": "error", "error": str(e)})
            raise RpcError(-32000, "network error: %s" % e)


class RemoteAPI:
    """子进程侧：插件看到的受限 API。"""

    is_isolated = True

    def __init__(self, write, read_response):
        self._write = write
        self._next_id = 1
        self._read_response = read_response
        self._callbacks = {}
        self.plugin_name = ""

    def _call(self, name, *args):
        req_id = self._next_id
        self._next_id += 1
        self._write(request("api.call", {"name": name, "args": list(args)}, req_id))
        msg = self._read_response(req_id)
        if "error" in msg:
            raise RpcError(
                msg["error"].get("code", -32000), msg["error"].get("message", "rpc error")
            )
        return msg.get("result")

    def log(self, message, level="info"):
        """日志走通知通道（不阻塞、不污染 RPC 响应）。"""
        try:
            self._write(notification("plugin.log", {"level": level, "message": str(message)}))
        except Exception:
            pass

    def get_current_text(self):
        return self._call("get_current_text") or ""

    def set_current_text(self, text):
        return self._call("set_current_text", text)

    def show_message(self, title, text):
        return self._call("show_message", title, text)

    def add_menu(self, path, callback, **kwargs):
        cb_id = len(self._callbacks)
        self._callbacks[cb_id] = callback
        # B1.5：shortcut 等宿主侧属性暂不透传
        return self._call("add_menu", path, cb_id)

    def subscribe(self, event, handler=None):
        """B1.5：事件订阅尚未跨进程（B2 实现事件桥）。"""
        self.log("[sandbox] subscribe(%s) not bridged yet" % event, "warning")
        return True

    def current_editor(self):
        return None

    def get_main_window(self):
        return None

    def show_status(self, text, timeout=0, level="info"):
        return self.log(text, level)

    def _new_callback(self, fn):
        cb_id = len(self._callbacks)
        self._callbacks[cb_id] = fn
        return cb_id

    def register_hover_provider(self, provider, language_ids=None, **kw):
        return self._call(
            "register_hover_provider",
            self._new_callback(provider),
            language_ids or [],
            self.plugin_name,
        )

    def register_code_action_provider(self, provider, language_ids=None, **kw):
        return self._call(
            "register_code_action_provider",
            self._new_callback(provider),
            language_ids or [],
            self.plugin_name,
        )

    def register_completion_provider(self, provider, language_ids=None, **kw):
        self.log("[sandbox] completion provider not bridged yet", "warning")
        return True

    def add_editor_context_menu(self, label, callback=None, **kw):
        if callback is None:
            return False
        return self._call(
            "add_editor_context_menu", label, self._new_callback(callback), self.plugin_name
        )

    def clear_diagnostics(self):
        return True

    def publish_diagnostics(self, items):
        return 0

    def add_status_item(self, text):
        return self._call("add_status_item", text)

    def set_config(self, key, value):
        return self._call("set_config", key, value, self.plugin_name)

    def get_config(self, key, default=None):
        return self._call("get_config", key, default, self.plugin_name)

    def register_settings_schema(self, schema):
        return self._call("register_settings_schema", schema, self.plugin_name)

    def register_remote_panel(self, title, fields, refresh):
        cb_id = len(self._callbacks)
        self._callbacks[cb_id] = refresh
        return self._call("register_remote_panel", title, fields, cb_id)

    def show_remote_panel(self, panel_id=0):
        return self._call("show_remote_panel", panel_id)

    def http_request(self, url, method="GET", headers=None, data=None, timeout=10):
        return self._call("http_request", url, method, headers or {}, data, timeout)

    def read_file(self, path):
        return self._call("read_file", path)

    def write_file(self, path, text):
        return self._call("write_file", path, text)


def load_plugin(plugin_dir):
    init = os.path.join(plugin_dir, "__init__.py")
    if not os.path.isfile(init):
        raise RuntimeError("插件缺少 __init__.py: %s" % plugin_dir)
    spec = importlib.util.spec_from_file_location(
        "qc_isolated_plugin",
        init,
        submodule_search_locations=[plugin_dir],
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cls = getattr(mod, "Plugin", None)
    if cls is None:
        raise RuntimeError("插件缺少 Plugin 类")
    return cls()


def _readline(stream):
    line = stream.readline()
    if not line:
        raise EOFError("host closed stdin")
    return decode(line)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("plugin_dir")
    args = ap.parse_args(argv)
    real_out = sys.stdout
    sys.stdout = sys.stderr  # 插件 print 不得污染协议流

    def write(obj):
        real_out.write(encode(obj))
        real_out.flush()

    pending = {}
    events = []

    def read_response(req_id):
        while True:
            msg = _readline(sys.stdin)
            if msg.get("id") == req_id:
                return msg
            if msg.get("method") == "host.shutdown":
                events.append(msg)
                continue
            events.append(msg)

    manifest_path = os.path.join(args.plugin_dir, "plugin.json")
    manifest = {}
    try:
        manifest = json.load(open(manifest_path, encoding="utf-8"))
    except Exception:
        pass
    write(
        request(
            "host.hello",
            {
                "name": manifest.get("name", os.path.basename(args.plugin_dir)),
                "version": manifest.get("version", "0.0.0"),
                "permissions": manifest.get("permissions", []),
            },
            0,
        )
    )
    # 等待 host.ready（响应父进程 id=0 的 hello）
    while True:
        msg = _readline(sys.stdin)
        if msg.get("method") == "host.ready":
            break
    plugin = load_plugin(args.plugin_dir)
    api = RemoteAPI(write, read_response)
    api.plugin_name = manifest.get("name", os.path.basename(args.plugin_dir))
    plugin.api = api
    plugin.on_activate()
    write(notification("host.activated"))
    while True:
        try:
            msg = _readline(sys.stdin)
        except EOFError:
            break
        method = msg.get("method")
        if method == "host.shutdown":
            break
        if method == "host.callback":
            req_id = msg.get("id")
            params = msg.get("params") or {}
            cb = api._callbacks.get(params.get("id"))
            try:
                result = cb(*(params.get("args") or [])) if cb else None
                if isinstance(result, list):
                    out = []
                    for item in result:
                        if isinstance(item, dict) and callable(item.get("callback")):
                            item = dict(item)
                            item["action_id"] = api._new_callback(item["callback"])
                            item["callback"] = None
                        out.append(item)
                    result = out
                write(response(req_id, result))
            except Exception as e:
                write(error(req_id, -32000, str(e)))
    try:
        plugin.on_deactivate()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
