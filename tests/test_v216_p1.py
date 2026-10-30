# -*- coding: utf-8 -*-
"""v2.16 P1：Ed25519 签名 / 审计基线 / 调试器模式 / 市场状态"""
import base64
import importlib.util
import json
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_ed25519_verify(monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    from core.plugin_signature import verify_ed25519

    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    data = b"plugin-data"
    sig = base64.b64encode(priv.sign(data)).decode()
    ok, msg = verify_ed25519(data, sig, public_keys=[pub])
    assert ok is True, msg
    assert verify_ed25519(b"tampered", sig, public_keys=[pub])[0] is False
    bad = base64.b64encode(b"x" * 64).decode()
    assert verify_ed25519(data, bad, public_keys=[pub])[0] is False

    monkeypatch.delenv("QINGCAO_PLUGIN_PUBKEYS", raising=False)
    monkeypatch.delenv("QINGCAO_PLUGIN_PUBKEY", raising=False)
    ok, msg = verify_ed25519(data, sig)
    assert ok is False and "公钥" in msg


def test_plugin_signature_status_and_revoked(monkeypatch):
    from ui.plugin_store import PluginInfo, plugin_signature_status

    bare = PluginInfo(name="a", file_hash="h" * 64)
    assert "SHA256" in plugin_signature_status(bare)
    signed = PluginInfo(name="b", signature="sig", signature_algo="ed25519")
    assert plugin_signature_status(signed) == "Ed25519 签名"
    monkeypatch.setenv("QINGCAO_PLUGIN_REVOKED", "b")
    assert plugin_signature_status(signed) == "已吊销"


def test_plugin_store_ed25519_integration(monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    from ui.plugin_store import verify_plugin_signature

    priv = Ed25519PrivateKey.generate()
    pub_hex = priv.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw).hex()
    monkeypatch.setenv("QINGCAO_PLUGIN_PUBKEYS", pub_hex)
    data = b"zip-bytes"
    sig = base64.b64encode(priv.sign(data)).decode()
    ok, msg = verify_plugin_signature(data, "", sig, "ed25519")
    assert ok is True, msg
    assert verify_plugin_signature(b"other", "", sig, "ed25519")[0] is False


def test_audit_baseline_present_and_enforced(tmp_path):
    from ui.plugin_store import build_market_catalog  # noqa: F401
    base = os.path.join(ROOT, "tools", "baselines", "sandbox_rpc.json")
    assert os.path.exists(base)
    out = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools",
                                      "audit_sandbox_rpc.py"),
         "--strict", "--baseline", base],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr

    data = json.load(open(base, encoding="utf-8"))
    data["allowed"].append("evil_method")
    bad = tmp_path / "bad_baseline.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    out2 = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools",
                                      "audit_sandbox_rpc.py"),
         "--strict", "--baseline", str(bad)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120)
    assert out2.returncode == 1
    assert "白名单变更" in out2.stdout


def _load_driver():
    path = os.path.join(ROOT, "plugins", "python_debugger", "driver.py")
    spec = importlib.util.spec_from_file_location("qc_driver_mode", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_debugger_eval_mode(monkeypatch):
    mod = _load_driver()
    monkeypatch.setenv("QINGCAO_DEBUGGER_EVAL_MODE", "restricted")
    assert mod._safe_eval("globals()", {}, {}).startswith("<blocked")
    monkeypatch.setenv("QINGCAO_DEBUGGER_EVAL_MODE", "developer")
    res = mod._safe_eval("globals()", {}, {})
    assert not (isinstance(res, str) and res.startswith("<blocked")), res
    # developer 模式仍拦截 dunder
    assert mod._safe_eval("(1).__class__", {}, {}).startswith("<blocked")