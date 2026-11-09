# -*- coding: utf-8 -*-
"""v2.24 安全闭环：更新包签名 + CI 安全扫描接线"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))


def test_update_sign_roundtrip(tmp_path):
    import sign_plugin
    from sign_update_asset import sign_asset, verify_asset

    priv, pub = sign_plugin.generate_keypair()
    zip_path = tmp_path / "app.zip"
    zip_path.write_bytes(b"fake update payload" * 1000)
    sig_path = sign_asset(str(zip_path), key_hex=priv)
    assert sig_path and os.path.isfile(sig_path)
    ok, msg = verify_asset(str(zip_path), sig_path, pub_hex=pub)
    assert ok, msg
    # 篡改包体后被拒绝
    zip_path.write_bytes(b"tampered" + zip_path.read_bytes())
    bad, _ = verify_asset(str(zip_path), sig_path, pub_hex=pub)
    assert bad is False


def test_update_sign_requires_key(tmp_path):
    from sign_update_asset import sign_asset

    zip_path = tmp_path / "app.zip"
    zip_path.write_bytes(b"x")
    old = os.environ.pop("QINGCAO_PLUGIN_SIGN_KEY", None)
    try:
        assert sign_asset(str(zip_path)) is None
    finally:
        if old is not None:
            os.environ["QINGCAO_PLUGIN_SIGN_KEY"] = old


def test_ci_publish_signs_when_key_present(tmp_path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "qc_ci_pub", os.path.join(ROOT, "tools", "ci_publish_release.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import sign_plugin

    priv, pub = sign_plugin.generate_keypair()
    zip_path = tmp_path / "x.zip"
    zip_path.write_bytes(b"release-bytes")
    monkeypatch.setattr(mod, "ROOT", str(tmp_path))
    monkeypatch.setenv("QINGCAO_PLUGIN_SIGN_KEY", priv)
    sig = mod.sign_release_zip(str(zip_path))
    assert sig and os.path.isfile(sig)
    names = mod.needed_asset_names("2.24.0", signed=True)
    assert "QingCaoEditor-v2.24.0-windows.zip.sig" in names


def test_security_workflow_and_release_secret():
    sec = open(os.path.join(ROOT, ".github", "workflows", "security.yml"), encoding="utf-8").read()
    assert "pip_audit" in sec or "pip-audit" in sec
    rel = open(os.path.join(ROOT, ".github", "workflows", "release.yml"), encoding="utf-8").read()
    assert "QINGCAO_PLUGIN_SIGN_KEY" in rel
