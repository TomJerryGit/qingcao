# -*- coding: utf-8 -*-
"""v2.15.x P3：沙箱 RPC 审计 + 市场签名校验 + 调试器求值 RPC 校验"""
import hashlib
import hmac
import importlib.util
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_tool():
    path = os.path.join(ROOT, "tools", "audit_sandbox_rpc.py")
    spec = importlib.util.spec_from_file_location("qc_rpc_audit", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sandbox_rpc_audit_strict_pass():
    out = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools",
                                      "audit_sandbox_rpc.py"), "--strict"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "审计通过" in out.stdout


def test_audit_sets_detects_mismatch():
    mod = _load_tool()
    r = mod.audit_sets({"a", "b"}, {"a"}, {"a"})
    assert r["missing_handler"] == ["b"]
    assert r["ok"] is False
    r2 = mod.audit_sets({"a"}, {"a", "x"}, {"a"})
    assert r2["unlisted_handler"] == ["x"]
    assert r2["ok"] is False


def test_market_signature_verification(monkeypatch):
    from ui.plugin_store import plugin_bytes_sha256, verify_plugin_signature
    data = b"plugin-bytes"
    h = plugin_bytes_sha256(data)
    assert verify_plugin_signature(data, h)[0] is True
    assert verify_plugin_signature(data, "0" * 64)[0] is False

    monkeypatch.setenv("QINGCAO_PLUGIN_SIGNING_KEY", "secret")
    sig = hmac.new(b"secret", h.encode("ascii"), hashlib.sha256).hexdigest()
    ok, msg = verify_plugin_signature(data, h, sig)
    assert ok is True, msg
    assert verify_plugin_signature(data, h, "bad")[0] is False

    monkeypatch.delenv("QINGCAO_PLUGIN_SIGNING_KEY", raising=False)
    ok, msg = verify_plugin_signature(data, h, sig)
    assert ok is False and "签名密钥" in msg


def test_install_plugin_uses_signature_check():
    src = open(os.path.join(ROOT, "ui", "plugin_store.py"),
               encoding="utf-8").read()
    assert "verify_plugin_signature(" in src
    assert "signature: str" in src


def test_debugger_eval_rpc_validation():
    from plugins.python_debugger.session import validate_eval_expression
    ok, val = validate_eval_expression("x + 1")
    assert ok and val == "x + 1"
    ok, msg = validate_eval_expression("")
    assert not ok and "空" in msg
    ok, msg = validate_eval_expression("a" * 4001)
    assert not ok and "过长" in msg
    src = open(os.path.join(ROOT, "plugins", "python_debugger",
                            "session.py"), encoding="utf-8").read()
    assert "validate_eval_expression" in src