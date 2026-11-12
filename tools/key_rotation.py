# -*- coding: utf-8 -*-
"""Ed25519 密钥轮换工具（v2.25）。

python tools/key_rotation.py --keygen
python tools/key_rotation.py --sign file.zip --key <privhex> [--key2 <privhex>]
python tools/key_rotation.py --verify file.zip --sig file.zip.sig
python tools/key_rotation.py --make-trust-store --pub <pubhex> --out resources/trusted_keys.json
"""

import argparse
import base64
import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.plugin_signature import key_id_for, verify_signature_envelope  # noqa: E402
from tools.sign_plugin import generate_keypair, sign_bytes  # noqa: E402


def make_trust_store(pub_hex, out, not_before="", not_after="", key_id="", revoked=False):
    path = out or os.path.join(ROOT, "resources", "trusted_keys.json")
    if os.path.isfile(path):
        data = json.load(io.open(path, encoding="utf-8"))
    else:
        data = {"version": 1, "keys": []}
    data.setdefault("keys", [])
    entry = {
        "key_id": key_id or key_id_for(pub_hex),
        "public_key": pub_hex.lower(),
        "not_before": not_before,
        "not_after": not_after,
        "revoked": bool(revoked),
    }
    data["keys"] = [k for k in data["keys"] if k.get("key_id") != entry["key_id"]]
    data["keys"].append(entry)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    io.open(path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    )
    return path, entry


def public_from_private(priv_hex):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))
    return (
        priv.public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        .hex()
    )


def sign_envelope(path, privs):
    data = io.open(path, "rb").read()
    sigs = []
    for priv in privs:
        pub = public_from_private(priv)
        sigs.append({"key_id": key_id_for(pub), "signature": sign_bytes(data, priv)})
    return {"version": 1, "signatures": sigs}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--keygen", action="store_true")
    ap.add_argument("--make-trust-store", action="store_true")
    ap.add_argument("--pub", default="")
    ap.add_argument("--key", action="append", default=[])
    ap.add_argument("--sign", default="")
    ap.add_argument("--verify", default="")
    ap.add_argument("--sig", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    if args.keygen:
        priv, pub = generate_keypair()
        print("private_hex=%s" % priv)
        print("public_hex=%s" % pub)
        print("key_id=%s" % key_id_for(pub))
        return 0
    if args.make_trust_store:
        if not args.pub:
            print("[rotate] 缺少 --pub")
            return 1
        path, entry = make_trust_store(args.pub, args.out)
        print("[rotate] trust store -> %s (key_id=%s)" % (path, entry["key_id"]))
        return 0
    if args.sign:
        if not args.key:
            print("[rotate] 缺少 --key")
            return 1
        env = sign_envelope(args.sign, args.key)
        out = args.out or (args.sign + ".sig")
        io.open(out, "w", encoding="utf-8", newline="\n").write(
            json.dumps(env, ensure_ascii=False, indent=2)
        )
        print("[rotate] signed %s -> %s（%d 个签名）" % (args.sign, out, len(env["signatures"])))
        return 0
    if args.verify:
        if not args.sig:
            print("[rotate] 缺少 --sig")
            return 1
        data = io.open(args.verify, "rb").read()
        sig = io.open(args.sig, encoding="utf-8").read()
        ok, msg = verify_signature_envelope(data, sig)
        print("[rotate] verify: %s (%s)" % ("PASS" if ok else "FAIL", msg))
        return 0 if ok else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
