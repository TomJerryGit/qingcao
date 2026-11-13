# -*- coding: utf-8 -*-
"""v2.25 插件沙箱 B0：JSON-RPC / 能力代理 / 孤立进程"""

import importlib
import json
import os

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _write_plugin(root, name, body, perms=None):
    d = os.path.join(root, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "plugin.json"), "w", encoding="utf-8") as f:
        json.dump(
            {"name": name, "version": "1.0.0", "permissions": perms or ["editor_read", "dialog"]}, f
        )
    with open(os.path.join(d, "__init__.py"), "w", encoding="utf-8") as f:
        f.write(body)
    return d


class _HostAPI:
    def __init__(self):
        self.calls = []
        self.menus = []

    def get_current_text(self):
        return "hello from host"

    def log(self, message, level="info"):
        self.calls.append(("log", message, level))
        return True

    def show_message(self, title, text):
        self.calls.append(("show", title, text))
        return True

    def add_menu(self, path, cb):
        self.menus.append((path, cb))
        return True

    def add_status_item(self, text):
        return True

    def get_config(self, key, default=None):
        return default

    def run_command(self, cmd):
        return "should-not-run"


def test_rpc_codec():
    from core import sandbox_rpc as r

    assert r.decode(r.encode(r.request("x", {"a": 1}, 2)))["id"] == 2
    assert r.decode(r.encode(r.notification("n")))["method"] == "n"
    err = r.error(1, r.ERROR_PERMISSION_DENIED, "no")
    assert r.decode(r.encode(err))["error"]["code"] == r.ERROR_PERMISSION_DENIED


def test_broker_permission_and_high_risk():
    from core.plugin_host import CapabilityBroker
    from core.sandbox_rpc import RpcError

    host = _HostAPI()
    broker = CapabilityBroker(["editor_read"], host)
    assert broker.dispatch("get_current_text", []) == "hello from host"
    with pytest.raises(RpcError) as e1:
        broker.dispatch("run_command", ["whoami"])
    assert e1.value.code == -32001
    with pytest.raises(RpcError) as e2:
        broker.dispatch("nope", [])
    assert e2.value.code == -32601


def test_isolation_end_to_end(tmp_path):
    from core.plugin_supervisor import PluginProcess

    d = _write_plugin(
        tmp_path,
        "iso_demo",
        """
class Plugin:
    def on_activate(self):
        self.text = self.api.get_current_text()
        self.api.log("activated:%s" % self.text)
    def on_deactivate(self):
        pass
""",
    )
    host = _HostAPI()
    proc = PluginProcess(d, host, timeout=15)
    try:
        proc.start()
        assert proc.is_alive()
        assert any(msg.startswith("activated:hello") for _lvl, msg in proc.logs)
    finally:
        proc.stop()
    assert not proc.is_alive()


def test_crash_isolated(tmp_path):
    from core.plugin_supervisor import PluginHostError, PluginProcess

    d = _write_plugin(
        tmp_path,
        "iso_crash",
        """
import os
class Plugin:
    def on_activate(self):
        os._exit(3)
    def on_deactivate(self):
        pass
""",
    )
    proc = PluginProcess(d, _HostAPI(), timeout=3)
    with pytest.raises(PluginHostError):
        proc.start()
    proc.stop()


def test_sandbox_policy_paths_and_hosts(tmp_path):
    from core.plugin_sandbox_policy import SandboxPolicy

    root = tmp_path / "proj"
    root.mkdir()
    policy = SandboxPolicy([str(root)], ["api.example.com"])
    assert policy.check_path(str(root / "a.txt"))
    assert not policy.check_path(str(tmp_path / "outside.txt"))
    assert policy.check_host("API.example.com")
    assert not policy.check_host("evil.example.com")


def test_menu_callback_end_to_end(tmp_path):
    from core.plugin_supervisor import PluginProcess

    d = _write_plugin(
        tmp_path,
        "iso_menu",
        """
class Plugin:
    def on_activate(self):
        self.api.add_menu("工具/测试", self.run)
    def run(self):
        self.api.log("cb-called")
    def on_deactivate(self):
        pass
""",
    )
    host = _HostAPI()
    proc = PluginProcess(d, host, timeout=15)
    try:
        proc.start()
        assert host.menus, "菜单未注册"
        proc.invoke_callback(host.menus[0][1])
        deadline = __import__("time").time() + 5
        while __import__("time").time() < deadline:
            if any("cb-called" in m for _l, m in proc.logs):
                break
            __import__("time").sleep(0.05)
        assert any("cb-called" in m for _l, m in proc.logs), proc.logs
    finally:
        proc.stop()


def test_isolation_flag_helpers(monkeypatch):
    from app.plugin_isolation import isolation_mode, should_isolate

    monkeypatch.setenv("QINGCAO_PLUGIN_ISOLATION", "off")
    assert isolation_mode() == "off" and not should_isolate("demo")
    monkeypatch.setenv("QINGCAO_PLUGIN_ISOLATION", "demo")
    assert should_isolate("demo") and should_isolate("wordcount")
    assert not should_isolate("python_debugger")
    monkeypatch.setenv("QINGCAO_PLUGIN_ISOLATION", "all")
    assert should_isolate("wordcount")
    assert not should_isolate("git_deep")


def test_isolated_names_only_compatible(monkeypatch):
    from app.plugin_isolation import ISOLATABLE_PLUGINS, isolated_plugin_names

    monkeypatch.setenv("QINGCAO_PLUGIN_ISOLATION", "all")
    names = isolated_plugin_names()
    assert names <= ISOLATABLE_PLUGINS
    assert "demo" in names and "wordcount" in names
    assert "git_deep" not in names and "python_debugger" not in names
