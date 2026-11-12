# -*- coding: utf-8 -*-
"""v2.25 密钥轮换：信封签名/信任清单/吊销/旧格式兼容"""

import base64
import importlib.util
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location(
        "qc_key_rotation", os.path.join(ROOT, "tools", "key_rotation.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _keypair():
    from tools.sign_plugin import generate_keypair

    return generate_keypair()


def test_key_id():
    from core.plugin_signature import key_id_for

    assert key_id_for("1F32F745A66E") == "1f32f745"


def test_envelope_verify_with_trust_store(tmp_path, monkeypatch):
    mod = _load()
    from core.plugin_signature import verify_signature_envelope

    priv, pub = _keypair()
    data = b"hello-qc"
    env = mod.sign_envelope  # noqa: F841
    sig = mod.sign_bytes(data, priv)
    envelope = {"version": 1, "signatures": [{"key_id": mod.key_id_for(pub), "signature": sig}]}
    store = tmp_path / "trusted.json"
    store.write_text(
        json.dumps(
            {
                "version": 1,
                "keys": [
                    {
                        "key_id": mod.key_id_for(pub),
                        "public_key": pub,
                        "not_before": "2020-01-01",
                        "not_after": "2035-12-31",
                        "revoked": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("QINGCAO_TRUST_STORE", str(store))
    ok, msg = verify_signature_envelope(data, json.dumps(envelope))
    assert ok, msg


def test_revoked_key_rejected(tmp_path, monkeypatch):
    mod = _load()
    from core.plugin_signature import verify_signature_envelope

    priv, pub = _keypair()
    data = b"x"
    envelope = {
        "version": 1,
        "signatures": [{"key_id": mod.key_id_for(pub), "signature": mod.sign_bytes(data, priv)}],
    }
    store = tmp_path / "trusted.json"
    store.write_text(
        json.dumps(
            {
                "version": 1,
                "keys": [{"key_id": mod.key_id_for(pub), "public_key": pub, "revoked": True}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("QINGCAO_TRUST_STORE", str(store))
    ok, _ = verify_signature_envelope(data, json.dumps(envelope))
    assert ok is False


def test_legacy_raw_signature_still_works(monkeypatch):
    from core.plugin_signature import verify_signature_envelope

    priv, pub = _keypair()
    data = b"legacy"
    from tools.sign_plugin import sign_bytes

    raw = sign_bytes(data, priv)
    monkeypatch.setenv("QINGCAO_PLUGIN_PUBKEYS", pub)
    ok, msg = verify_signature_envelope(data, raw)
    assert ok, msg
