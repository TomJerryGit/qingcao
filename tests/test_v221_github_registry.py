# -*- coding: utf-8 -*-
import importlib.util
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from ui_source_utils import read_market_source


def _load():
    spec = importlib.util.spec_from_file_location(
        "qc_pub_reg", os.path.join(ROOT, "tools", "publish_registry_release.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_urls():
    mod = _load()
    assert (
        mod.registry_url("o/r", "t") == "https://github.com/o/r/releases/download/t/registry.json"
    )
    assert (
        mod.asset_download_url("o/r", "t", "x.zip")
        == "https://github.com/o/r/releases/download/t/x.zip"
    )


def test_dry_run_build(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    mod = _load()
    priv = Ed25519PrivateKey.generate()
    key_hex = priv.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    ).hex()
    out = str(tmp_path / "reg")
    reg, out_json = mod.build_assets(
        out, "o/r", "plugin-registry", only={"wordcount_sandbox"}, key_hex=key_hex
    )
    assert len(reg["plugins"]) == 1 and os.path.isfile(out_json)
    e = reg["plugins"][0]
    assert e["download_url"].startswith(
        "https://github.com/o/r/releases/download/plugin-registry/plugins/"
    )
    assert e["signature"] and e["signature_algo"] == "ed25519"


def test_wiring():
    assert os.path.isfile(os.path.join(ROOT, "docs", "plugin_registry_github_releases.md"))
    assert os.path.isfile(os.path.join(ROOT, ".github", "workflows", "publish_registry.yml"))
    src = read_market_source()
    assert "GITHUB_REGISTRY_URL" in src
