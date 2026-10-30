# -*- coding: utf-8 -*-
"""插件包非对称签名验证（Ed25519，v2.16）

公钥配置（任选其一，可多个用于轮换）：
    QINGCAO_PLUGIN_PUBKEYS = "hex1,hex2" 或 base64 列表
    QINGCAO_PLUGIN_PUBKEY  = "hex"
吊销名单：
    QINGCAO_PLUGIN_REVOKED = "plugin_a,plugin_b"
"""
import base64
import os


def default_public_keys():
    """解析环境变量中的 Ed25519 公钥（hex 或 base64，逗号分隔）"""
    raw = (os.environ.get("QINGCAO_PLUGIN_PUBKEYS")
           or os.environ.get("QINGCAO_PLUGIN_PUBKEY") or "")
    keys = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            keys.append(bytes.fromhex(part))
            continue
        except ValueError:
            pass
        try:
            keys.append(base64.b64decode(part, validate=True))
        except Exception:
            continue
    return keys


def revoked_plugins():
    raw = os.environ.get("QINGCAO_PLUGIN_REVOKED", "")
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def is_revoked(plugin_name: str) -> bool:
    return (plugin_name or "").lower() in revoked_plugins()


def verify_ed25519(data: bytes, signature_b64: str, public_keys=None):
    """校验 Ed25519 签名；返回 (ok, 消息)"""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except Exception:
        return (False, "未安装 cryptography，无法验证 Ed25519 签名")
    keys = list(public_keys) if public_keys is not None \
        else default_public_keys()
    if not keys:
        return (False, "未配置 Ed25519 公钥（QINGCAO_PLUGIN_PUBKEYS）")
    try:
        sig = base64.b64decode(signature_b64)
    except Exception:
        return (False, "签名格式无效（需 base64）")
    for key_bytes in keys:
        try:
            pub = Ed25519PublicKey.from_public_bytes(bytes(key_bytes))
            pub.verify(sig, data)
            return (True, "ok")
        except Exception:
            continue
    return (False, "Ed25519 签名校验失败")
