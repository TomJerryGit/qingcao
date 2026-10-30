# -*- coding: utf-8 -*-
"""插件包签名工具（Ed25519，v2.16 P3）

用法:
    python tools/sign_plugin.py --keygen
    python tools/sign_plugin.py --sign plugin.zip --key <私钥hex>
    python tools/sign_plugin.py --verify plugin.zip --sig <base64> --pub <公钥hex>
"""
import argparse
import base64
import hashlib
import io
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def generate_keypair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    priv = Ed25519PrivateKey.generate()
    priv_hex = priv.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption()).hex()
    pub_hex = priv.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw).hex()
    return priv_hex, pub_hex


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def sign_bytes(data, priv_hex):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))
    return base64.b64encode(priv.sign(data)).decode("ascii")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keygen", action="store_true")
    ap.add_argument("--sign", default="")
    ap.add_argument("--verify", default="")
    ap.add_argument("--key", default="")
    ap.add_argument("--sig", default="")
    ap.add_argument("--pub", default="")
    args = ap.parse_args()
    if args.keygen:
        priv, pub = generate_keypair()
        print("PRIVATE_KEY=" + priv)
        print("PUBLIC_KEY=" + pub)
        return 0
    if args.sign:
        data = io.open(args.sign, "rb").read()
        if not args.key:
            print("缺少 --key 私钥"); return 1
        print("SHA256=" + sha256_hex(data))
        print("SIGNATURE=" + sign_bytes(data, args.key))
        return 0
    if args.verify:
        data = io.open(args.verify, "rb").read()
        from core.plugin_signature import verify_ed25519
        if not args.pub:
            print("缺少 --pub 公钥"); return 1
        ok, msg = verify_ed25519(data, args.sig,
                                 public_keys=[bytes.fromhex(args.pub)])
        print("OK" if ok else "FAIL", msg)
        return 0 if ok else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
