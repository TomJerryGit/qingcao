# -*- coding: utf-8 -*-
"""v2.26 B3：插件签名信任"""

import base64
import json
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _make_signed_plugin(tmp_path):
    from tools.sign_plugin import sign_bytes

    priv = Ed25519PrivateKey.generate()
    priv_hex = priv.private_bytes_raw().hex() if hasattr(priv, "private_bytes_raw") else None
    if priv_hex is None:
        from cryptography.hazmat.primitives import serialization

        priv_hex = priv.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        ).hex()
    plugin = tmp_path / "signed_plugin"
    plugin.mkdir()
    manifest = json.dumps({"name": "signed_plugin"}).encode()
    (plugin / "plugin.json").write_bytes(manifest)
    (plugin / "plugin.json.sig").write_text(sign_bytes(manifest, priv_hex), encoding="ascii")
    from cryptography.hazmat.primitives import serialization

    pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return plugin, pub


def test_valid_signature_trusted(tmp_path):
    from core.plugin_trust import verify_plugin_signature

    plugin, pub = _make_signed_plugin(tmp_path)
    ok, msg = verify_plugin_signature(str(plugin), public_keys=[pub])
    assert ok, msg


def test_tampered_manifest_rejected(tmp_path):
    from core.plugin_trust import verify_plugin_signature

    plugin, pub = _make_signed_plugin(tmp_path)
    (plugin / "plugin.json").write_text('{"name":"evil"}', encoding="utf-8")
    ok, _msg = verify_plugin_signature(str(plugin), public_keys=[pub])
    assert not ok


def test_unsigned_rejected(tmp_path):
    from core.plugin_trust import verify_plugin_signature

    p = tmp_path / "plain"
    p.mkdir()
    (p / "plugin.json").write_text("{}", encoding="utf-8")
    ok, _msg = verify_plugin_signature(str(p), public_keys=[])
    assert not ok
