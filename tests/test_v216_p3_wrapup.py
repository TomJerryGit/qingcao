# -*- coding: utf-8 -*-
"""v2.16 P3 收尾：签名工具 / 沙箱检查插件 / 主题基线对比"""
import importlib.util
import json
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(path, name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sign_tool_roundtrip():
    mod = _load(os.path.join("tools", "sign_plugin.py"), "qc_sign_tool")
    from core.plugin_signature import verify_ed25519
    priv, pub = mod.generate_keypair()
    data = b"zip-bytes"
    sig = mod.sign_bytes(data, priv)
    ok, msg = verify_ed25519(data, sig, public_keys=[bytes.fromhex(pub)])
    assert ok is True, msg
    assert mod.sha256_hex(data) == mod.sha256_hex(data)
    assert verify_ed25519(b"tampered", sig,
                          public_keys=[bytes.fromhex(pub)])[0] is False


def test_whitespace_sandbox_diagnostics():
    from infrastructure.plugin_sandbox_manager import SandboxedPlugin
    path = os.path.join(ROOT, "plugins", "whitespace_sandbox")
    sp = SandboxedPlugin(path, timeout=8)
    try:
        st = sp.status_text("a\nb")
        assert "2 行" in st
        text = "ok line\nbad  \n\tindented\n" + "x" * 130 + "\n"
        items = sp.diagnostics(text)
        codes = {it.get("code") for it in items}
        assert "trailing-ws" in codes
        assert "tab-indent" in codes
        assert "long-line" in codes
    finally:
        sp.close()


def test_whitespace_manifest_fields():
    m = json.load(open(os.path.join(
        ROOT, "plugins", "whitespace_sandbox", "plugin.json"),
        encoding="utf-8"))
    assert m["sandbox"] is True and m["enabled"] is True
    for key in ("api_version", "category", "license", "homepage",
                "keywords"):
        assert key in m, key


def test_theme_baseline_check_wiring():
    baseline = os.path.join(ROOT, "docs", "theme_baseline")
    pngs = [f for f in os.listdir(baseline) if f.endswith(".png")]
    assert len(pngs) >= 8
    for theme in ("dark_night", "light_clean", "eye_protect",
                  "high_contrast"):
        assert "window_%s.png" % theme in pngs
        assert "panel_%s.png" % theme in pngs
    tool = open(os.path.join(ROOT, "tools",
                             "theme_e2e_screenshots.py"),
                encoding="utf-8").read()
    assert "--check" in tool and "基线对比通过" in tool


def test_playbook_and_ci_wiring():
    assert os.path.exists(os.path.join(
        ROOT, "docs", "plugin_market_key_rotation_playbook.md"))
    yml = open(os.path.join(ROOT, ".github", "workflows", "test.yml"),
               encoding="utf-8").read()
    assert "theme_e2e_screenshots.py --check" in yml