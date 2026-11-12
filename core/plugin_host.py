# -*- coding: utf-8 -*-
"""插件宿主（B0 原型）：在子进程内加载插件，通过 JSON-RPC 调用主进程能力。"""

import argparse
import importlib.util
import json
import os
import sys

from core.sandbox_rpc import (
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
    "run_command": "process",
    "run_python": "process",
}
HIGH_RISK = {"process", "terminal", "debugger"}


class CapabilityBroker:
    """主进程侧：按 manifest 权限校验并转发到宿主 API。"""

    def __init__(self, permissions, host_api, allow_high_risk=False, policy=None):
        self.permissions = set(permissions or [])
        self.host_api = host_api
        self.allow_high_risk = allow_high_risk
        self.policy = policy

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
        try:
            return getattr(self.host_api, name)(*(args or []))
        except RpcError:
            raise
        except Exception as e:
            raise RpcError(-32000, "host api failed: %s" % e)


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

    def register_hover_provider(self, provider, language_ids=None, **kw):
        self.log("[sandbox] hover provider not bridged yet", "warning")
        return True

    def register_code_action_provider(self, provider, language_ids=None, **kw):
        self.log("[sandbox] code-action provider not bridged yet", "warning")
        return True

    def register_completion_provider(self, provider, language_ids=None, **kw):
        self.log("[sandbox] completion provider not bridged yet", "warning")
        return True

    def add_editor_context_menu(self, label, callback=None, **kw):
        self.log("[sandbox] editor context menu not bridged yet", "warning")
        return True

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
