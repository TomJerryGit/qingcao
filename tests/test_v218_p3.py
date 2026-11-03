# -*- coding: utf-8 -*-
"""v2.18.x P3：市场 Token/HTTPS、mmap 基准、i18n 脚手架"""

import datetime
import json
import os
import socket
import ssl
import threading
import urllib.error
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(path, name):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _build_registry(tmp_path):
    build = _load(os.path.join("tools", "build_plugin_registry.py"), "qc_reg_build_p3")
    out_dir = str(tmp_path / "registry_p3")
    build.build("plugins", out_dir, "http://127.0.0.1:1", only={"wordcount_sandbox"})
    return out_dir


def test_token_auth(tmp_path, monkeypatch):
    server = _load(os.path.join("tools", "plugin_registry_server.py"), "qc_reg_srv_token")
    reg = _build_registry(tmp_path)
    port = _free_port()
    srv = server.make_server(reg, "127.0.0.1", port, token="secret-token")
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    url = "http://127.0.0.1:%d/registry.json" % port
    try:
        try:
            urllib.request.urlopen(url, timeout=10)
            assert False, "无 Token 应返回 401"
        except urllib.error.HTTPError as e:
            assert e.code == 401
        req = urllib.request.Request(url, headers={"Authorization": "Bearer secret-token"})
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        assert data["plugins"]

        # 客户端带 Token 拉取
        from ui.plugin_store import PluginStoreClient

        monkeypatch.setenv("QINGCAO_REGISTRY_TOKEN", "secret-token")
        client = PluginStoreClient(registry_url=url)
        regdata = client.fetch_registry(force=True)
        assert regdata and regdata.get("plugins")
        monkeypatch.delenv("QINGCAO_REGISTRY_TOKEN", raising=False)
        client2 = PluginStoreClient(registry_url=url)
        assert client2._download_json(url) is None
    finally:
        srv.shutdown()
        srv.server_close()


def test_https_server(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    server = _load(os.path.join("tools", "plugin_registry_server.py"), "qc_reg_srv_tls")
    reg = _build_registry(tmp_path)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_path = str(tmp_path / "cert.pem")
    key_path = str(tmp_path / "key.pem")
    open(cert_path, "wb").write(cert.public_bytes(serialization.Encoding.PEM))
    open(key_path, "wb").write(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    port = _free_port()
    srv = server.make_server(reg, "127.0.0.1", port, certfile=cert_path, keyfile=key_path)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        ctx = ssl._create_unverified_context()
        url = "https://127.0.0.1:%d/registry.json" % port
        data = json.loads(urllib.request.urlopen(url, timeout=10, context=ctx).read())
        assert data["plugins"]
    finally:
        srv.shutdown()
        srv.server_close()


def test_mmap_patch_helpers(tmp_path):
    mod = _load(os.path.join("tools", "bench_mmap_edit.py"), "qc_mmap_bench")
    p = tmp_path / "small.txt"
    lines = ["row %03d abcdefghij" % i for i in range(100)]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    new_line = lines[50].replace("abcdefghij", "ABCDEFGHIJ")
    dt, ln = mod._mmap_patch(str(p), 50, new_line)
    assert dt >= 0 and ln == len(lines[50])
    content = p.read_text(encoding="utf-8").split("\n")
    assert content[50] == new_line
    dt2, _ = mod._rewrite(str(p), 49, lines[49].replace("abcdefghij", "XXXXXXXXXX"))
    assert dt2 >= 0


def test_i18n_extract_and_tr(tmp_path):
    mod = _load(os.path.join("core", "i18n_json.py"), "qc_i18n")
    strings = mod.extract_from_source if hasattr(mod, "extract_from_source") else None
    extract = _load(os.path.join("tools", "extract_i18n_strings.py"), "qc_i18n_extract")
    got = extract.extract_from_source('x = "保存文件"\ny = "abc"\n')
    assert "保存文件" in got and "abc" not in got
    lang = tmp_path / "locale" / "en_US"
    lang.mkdir(parents=True)
    (lang / "strings.json").write_text(
        json.dumps({"保存文件": "Save File"}, ensure_ascii=False), encoding="utf-8"
    )
    data = mod.load_strings("en_US", root=str(tmp_path))
    assert data["保存文件"] == "Save File"
    mod.clear_cache()
    assert mod.tr("未翻译串") == "未翻译串"


def test_docs_p3():
    for rel in ("docs/mmap_incremental_edit_design.md", "docs/i18n_migration_plan.md"):
        assert os.path.exists(os.path.join(ROOT, rel))
