# -*- coding: utf-8 -*-
"""v2.18 插件市场在线服务化 MVP：注册表生成/服务/拉取/验签"""
import base64
import importlib.util
import json
import os
import socket
import threading
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(path, name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_registry_build_serve_verify(tmp_path, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )

    from core.plugin_signature import verify_ed25519

    build = _load(os.path.join("tools", "build_plugin_registry.py"),
                  "qc_registry_build")
    server = _load(os.path.join("tools", "plugin_registry_server.py"),
                   "qc_registry_server")

    priv = Ed25519PrivateKey.generate()
    key_hex = priv.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption()).hex()
    pub_hex = priv.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw).hex()

    port = _free_port()
    base = "http://127.0.0.1:%d" % port
    out_dir = str(tmp_path / "registry")
    registry, out_json = build.build(
        "plugins", out_dir, base,
        only={"wordcount_sandbox", "whitespace_sandbox"}, key_hex=key_hex)
    assert len(registry["plugins"]) == 2
    assert os.path.exists(out_json)

    srv = server.make_server(out_dir, "127.0.0.1", port)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        url = base + "/registry.json"
        data = json.loads(urllib.request.urlopen(url, timeout=10).read())
        assert len(data["plugins"]) == 2
        entry = data["plugins"][0]
        zip_bytes = urllib.request.urlopen(
            entry["download_url"], timeout=10).read()
        ok, msg = verify_ed25519(zip_bytes, entry["signature"],
                                 public_keys=[bytes.fromhex(pub_hex)])
        assert ok is True, msg
        # 篡改后签名/哈希校验失败
        from ui.plugin_store import verify_plugin_signature
        assert verify_plugin_signature(
            zip_bytes + b"x", entry["file_hash"], entry["signature"],
            "ed25519")[0] is False

        # 插件市场客户端可直接拉取注册表（schema 兼容）
        from ui.plugin_store import PluginStoreClient
        client = PluginStoreClient(registry_url=url)
        reg = client.fetch_registry(force=True)
        assert reg and len(reg.get("plugins") or []) == 2
        names = {p["name"] for p in reg["plugins"]}
        assert names == {"wordcount_sandbox", "whitespace_sandbox"}
    finally:
        srv.shutdown()
        srv.server_close()


def test_registry_check_cli(tmp_path):
    build = _load(os.path.join("tools", "build_plugin_registry.py"),
                  "qc_registry_build2")
    server = _load(os.path.join("tools", "plugin_registry_server.py"),
                   "qc_registry_server2")
    out_dir = str(tmp_path / "reg2")
    build.build("plugins", out_dir, "http://127.0.0.1:1",
                only={"wordcount_sandbox"})
    ok, msg = server.check_registry(out_dir)
    assert ok is True, msg
    os.remove(os.path.join(out_dir, "plugins",
                           os.listdir(os.path.join(out_dir, "plugins"))[0]))
    ok, msg = server.check_registry(out_dir)
    assert ok is False and "缺少" in msg