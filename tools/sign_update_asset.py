# -*- coding: utf-8 -*-
"""更新安装包 Ed25519 签名工具（v2.24 安全闭环）。

签名：python tools/sign_update_asset.py --sign dist/QingCaoEditor-vX-windows.zip
校验：python tools/sign_update_asset.py --verify <zip> --sig <zip.sig> --pub <hex>
私钥来源：--key 或环境变量 QINGCAO_PLUGIN_SIGN_KEY。
"""

import argparse
import io
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))


def key_from_env(explicit=""):
    return (explicit or os.environ.get("QINGCAO_PLUGIN_SIGN_KEY", "")).strip()


def sign_asset(zip_path, key_hex=""):
    """对安装包签名，写 <zip>.sig（base64），返回签名路径。"""
    key = key_from_env(key_hex)
    if not key:
        return None
    from sign_plugin import sign_bytes

    data = io.open(zip_path, "rb").read()
    sig = sign_bytes(data, key)
    sig_path = zip_path + ".sig"
    with io.open(sig_path, "w", encoding="ascii", newline="\n") as f:
        f.write(sig)
    return sig_path


def verify_asset(zip_path, sig_path="", pub_hex=""):
    """校验安装包签名，返回 (ok, msg)。"""
    from core.plugin_signature import verify_ed25519

    sig_path = sig_path or (zip_path + ".sig")
    if not os.path.isfile(zip_path) or not os.path.isfile(sig_path):
        return (False, "安装包或签名文件缺失")
    data = io.open(zip_path, "rb").read()
    sig = io.open(sig_path, encoding="ascii", errors="replace").read().strip()
    keys = [bytes.fromhex(pub_hex)] if pub_hex else None
    return verify_ed25519(data, sig, public_keys=keys)


def main():
    ap = argparse.ArgumentParser(description="更新安装包签名/校验")
    ap.add_argument("--sign", default="", help="待签名 ZIP")
    ap.add_argument("--verify", default="", help="待校验 ZIP")
    ap.add_argument("--sig", default="", help="签名文件（默认 <zip>.sig）")
    ap.add_argument("--key", default="", help="Ed25519 私钥 hex")
    ap.add_argument("--pub", default="", help="Ed25519 公钥 hex（校验用）")
    args = ap.parse_args()
    if args.sign:
        path = sign_asset(args.sign, args.key)
        if not path:
            print("[update-sign] 未提供私钥（--key / QINGCAO_PLUGIN_SIGN_KEY）")
            return 1
        print("[update-sign] 已签名:", path)
        return 0
    if args.verify:
        ok, msg = verify_asset(args.verify, args.sig, args.pub)
        print("[update-sign]", "OK" if ok else "FAILED", "-", msg)
        return 0 if ok else 1
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
