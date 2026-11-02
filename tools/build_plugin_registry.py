# -*- coding: utf-8 -*-
"""生成插件市场注册表（v2.18 在线服务化 MVP）

用法:
    python tools/build_plugin_registry.py --out data/registry \
        --base-url http://127.0.0.1:8765 [--only a,b] [--key-hex HEX]

输出: <out>/registry.json + <out>/plugins/<name>-<ver>.zip
"""
import argparse
import base64
import hashlib
import io
import json
import os
import sys
import zipfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _sign_ed25519(data, key_hex):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(key_hex))
    return base64.b64encode(key.sign(data)).decode("ascii")


def _pack_plugin(plugin_dir, out_plugins, name, version):
    zname = "%s-%s.zip" % (name, version)
    zpath = os.path.join(out_plugins, zname)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(plugin_dir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
            for f in files:
                if f.endswith(".pyc"):
                    continue
                full = os.path.join(root, f)
                rel = os.path.relpath(full, plugin_dir)
                zf.write(full, os.path.join(name, rel))
    return zpath, zname


def build(plugins_dir, out_dir, base_url, only=None, key_hex="", app_version=""):
    plugins_root = os.path.join(ROOT, plugins_dir)
    out_plugins = os.path.join(ROOT, out_dir, "plugins") if not os.path.isabs(out_dir) \
        else os.path.join(out_dir, "plugins")
    os.makedirs(out_plugins, exist_ok=True)
    entries = []
    for name in sorted(os.listdir(plugins_root)):
        if only and name not in only:
            continue
        manifest_path = os.path.join(plugins_root, name, "plugin.json")
        if not os.path.isfile(manifest_path):
            continue
        manifest = json.load(io.open(manifest_path, encoding="utf-8"))
        if not manifest.get("enabled", True):
            continue
        version = str(manifest.get("version", "0.0.0"))
        zpath, zname = _pack_plugin(
            os.path.join(plugins_root, name), out_plugins, name, version)
        data = io.open(zpath, "rb").read()
        entry = {
            "name": manifest.get("name") or name,
            "display_name": manifest.get("display_name") or name,
            "version": version,
            "description": manifest.get("description", ""),
            "author": manifest.get("author", ""),
            "homepage": manifest.get("homepage", ""),
            "category": manifest.get("category", "other"),
            "license": manifest.get("license", ""),
            "tags": manifest.get("keywords") or [],
            "permissions": manifest.get("permissions") or [],
            "dependencies": manifest.get("dependencies") or [],
            "file_hash": _sha256(data),
            "file_size": len(data),
            "download_url": "%s/plugins/%s" % (base_url.rstrip("/"), zname),
            "min_app_version": manifest.get("min_app_version", ""),
        }
        if key_hex:
            entry["signature"] = _sign_ed25519(data, key_hex)
            entry["signature_algo"] = "ed25519"
        entries.append(entry)
    registry = {"version": 1, "plugins": entries, "themes": [],
                "generated_by": "build_plugin_registry.py",
                "app_version": app_version}
    out_json = os.path.join(ROOT, out_dir, "registry.json") if not os.path.isabs(out_dir) \
        else os.path.join(out_dir, "registry.json")
    io.open(out_json, "w", encoding="utf-8", newline="\n").write(
        json.dumps(registry, ensure_ascii=False, indent=2))
    return registry, out_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugins-dir", default="plugins")
    ap.add_argument("--out", default="data/registry")
    ap.add_argument("--base-url", default="http://127.0.0.1:8765")
    ap.add_argument("--only", default="")
    ap.add_argument("--key-hex", default=os.environ.get(
        "QINGCAO_PLUGIN_SIGN_KEY", ""))
    ap.add_argument("--app-version", default="")
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()} or None
    registry, out_json = build(args.plugins_dir, args.out, args.base_url,
                               only=only, key_hex=args.key_hex,
                               app_version=args.app_version)
    print("[registry] %d 个插件 -> %s" % (len(registry["plugins"]), out_json))
    return 0


if __name__ == "__main__":
    sys.exit(main())
