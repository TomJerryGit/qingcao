# -*- coding: utf-8 -*-
"""插件子进程沙箱 RPC（B-1/B-2）测试"""
import time


PLUGIN = '''# -*- coding: utf-8 -*-
import os
import time


class Plugin:
    NAME = "sandbox_demo"
    VERSION = "1.0.0"

    def symbols(self, text, filepath="", language=""):
        return [{"name": "sym1", "type": "function", "line": 0}]

    def completion(self, prefix, language="", filepath=""):
        return [prefix + "_x"]

    def hover(self, line, col, filepath="", language=""):
        time.sleep(2.0)
        return "slow"

    def crash(self):
        os._exit(3)
'''

CRASH = '''# -*- coding: utf-8 -*-
import os


class Plugin:
    NAME = "crash_demo"
    VERSION = "1.0.0"

    def symbols(self, text, filepath="", language=""):
        os._exit(3)
'''


def _make_plugin(tmp_path, code=PLUGIN, name="sandbox_demo"):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "__init__.py").write_text(code, encoding="utf-8")
    (d / "plugin.json").write_text('{"name": "%s"}' % name,
                                   encoding="utf-8")
    return str(d)


def test_rpc_symbols_and_describe(tmp_path):
    from infrastructure.plugin_sandbox_rpc import SandboxProcess
    p = SandboxProcess(_make_plugin(tmp_path), timeout=5)
    try:
        assert p.is_alive()
        desc = p.describe()
        assert desc["name"] == "sandbox_demo"
        syms = p.call("symbols", {"text": "x", "filepath": "",
                                  "language": ""})
        assert syms and syms[0]["name"] == "sym1"
        assert p.call("completion", {"prefix": "a"}) == ["a_x"]
    finally:
        p.close()


def test_timeout_is_isolated(tmp_path):
    from infrastructure.plugin_sandbox_rpc import SandboxProcess, SandboxTimeout
    p = SandboxProcess(_make_plugin(tmp_path), timeout=5)
    try:
        t0 = time.monotonic()
        try:
            p.call("hover", {"line": 0, "col": 0}, timeout=0.3)
            assert False, "应超时"
        except SandboxTimeout:
            pass
        assert time.monotonic() - t0 < 2.0
        assert p.is_alive(), "超时不应杀死进程"
    finally:
        p.close()


def test_forbidden_method_rejected(tmp_path):
    from infrastructure.plugin_sandbox_rpc import SandboxError, SandboxProcess
    p = SandboxProcess(_make_plugin(tmp_path), timeout=5)
    try:
        try:
            p.call("crash")
            assert False, "未在客户端拦截非法方法"
        except SandboxError as e:
            assert "不允许" in str(e)
    finally:
        p.close()


def test_crash_and_restart(tmp_path):
    from infrastructure.plugin_sandbox_rpc import SandboxError, SandboxProcess
    d = _make_plugin(tmp_path, CRASH, name="crash_demo")
    p = SandboxProcess(d, timeout=3)
    try:
        try:
            p.call("symbols", {"text": "x"})
            assert False, "崩溃时应抛错"
        except SandboxError:
            pass
        assert not p.is_alive()
        p.restart()
        assert p.is_alive()
    finally:
        p.close()