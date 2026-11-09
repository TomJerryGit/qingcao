# -*- coding: utf-8 -*-
"""v2.24 安全闭环：风险分级/安装确认/权限矩阵/评分验签"""

import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_risk_classification():
    from core.plugin_risk import classify_plugin_risk, risk_message

    assert classify_plugin_risk(["process"]) == "high"
    assert classify_plugin_risk(["process"], sandboxed=True) == "medium"
    assert classify_plugin_risk(["filesystem"]) == "medium"
    assert classify_plugin_risk(["filesystem"], sandboxed=True) == "low"
    assert classify_plugin_risk([]) == "low"
    assert classify_plugin_risk(["editor_read"]) == "low"


def test_confirm_risk_prompt(qapp, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox

    from ui.plugin_store import PluginInfo, PluginStoreDialog

    dlg = PluginStoreDialog.__new__(PluginStoreDialog)
    import ui.plugin_store as ps

    prompts = []

    def fake_q(parent, title, text, buttons, default):
        prompts.append((title, text, default))
        return QMessageBox.No

    monkeypatch.setattr(ps.QMessageBox, "question", fake_q)
    high = PluginInfo(name="h", permissions=["process"])
    assert dlg._confirm_risk(high, "安装") is False
    assert prompts and "高风险" in prompts[0][0]
    assert prompts[0][2] == QMessageBox.No

    prompts.clear()
    monkeypatch.setattr(ps.QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    assert dlg._confirm_risk(high, "安装") is True

    prompts.clear()
    low = PluginInfo(name="l", permissions=["editor_read"])
    assert dlg._confirm_risk(low, "安装") is True
    assert prompts == []


def test_plugin_api_permission_matrix():
    from app.plugin_api import PluginAPI

    api = PluginAPI.__new__(PluginAPI)
    api.permissions = set()
    api.plugin_name = "test"
    api.show_status = lambda *a, **k: None
    assert api.run_command("echo hi") is None
    assert api.run_python("print(1)") is None
    assert api.run_command("echo hi") is None

    api.permissions.add("process")
    out = api.run_python("print(6*7)")
    assert out is not None and "42" in out


def test_sandbox_allowlist_no_dangerous_methods():
    from infrastructure.plugin_sandbox_rpc import ALLOWED_METHODS

    for bad in ("run_command", "run_python", "exec", "eval", "shell"):
        assert bad not in ALLOWED_METHODS


def test_ratings_signature_roundtrip(tmp_path):
    from sign_plugin import generate_keypair

    from core.plugin_signature import verify_ed25519

    mod_spec = __import__("importlib.util").util.spec_from_file_location(
        "qc_pub_rat2", os.path.join(ROOT, "tools", "publish_registry_release.py")
    )
    mod = __import__("importlib.util").util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(mod)
    priv, pub = generate_keypair()
    path, data, sig_path = mod.build_ratings(str(tmp_path), key_hex=priv)
    assert os.path.isfile(path) and sig_path and os.path.isfile(sig_path)
    raw = open(path, "rb").read()
    sig = open(sig_path, encoding="ascii").read().strip()
    ok, msg = verify_ed25519(raw, sig, public_keys=[bytes.fromhex(pub)])
    assert ok, msg
    bad, _ = verify_ed25519(raw + b" ", sig, public_keys=[bytes.fromhex(pub)])
    assert bad is False


def test_ratings_client_rejects_missing_sig(monkeypatch):
    from ui import plugin_client as pc

    monkeypatch.delenv("QINGCAO_NO_COMMUNITY_RATINGS", raising=False)

    class Resp:
        status_code = 404

        def __init__(self, content=b""):
            self.content = content

    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp())
    client = pc.PluginStoreClient("https://example/reg/registry.json")
    assert client.fetch_ratings() is None
