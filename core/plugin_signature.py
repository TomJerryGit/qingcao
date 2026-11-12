# -*- coding: utf-8 -*-
"""插件包非对称签名验证（Ed25519，v2.16）

公钥配置（任选其一，可多个用于轮换）：
    QINGCAO_PLUGIN_PUBKEYS = "hex1,hex2" 或 base64 列表
    QINGCAO_PLUGIN_PUBKEY  = "hex"
吊销名单：
    QINGCAO_PLUGIN_REVOKED = "plugin_a,plugin_b"
"""
import base64
import io
import json
import os


def trust_store_candidates():
    """运行时解析信任清单路径（环境变量优先，便于轮换/测试）。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return (
        os.environ.get("QINGCAO_TRUST_STORE", ""),
        os.path.join(root, "resources", "trusted_keys.json"),
        os.path.join(root, "data", "trusted_keys.json"),
    )


def key_id_for(public_hex: str) -> str:
    """key_id：公钥 hex 前 8 位（小写）。"""
    return (public_hex or "").lower()[:8]


def load_trusted_keys(path=None):
    """加载信任清单，返回 {key_id: {public: bytes, not_before, not_after, revoked}}。"""
    paths = [path] if path else [p for p in trust_store_candidates() if p]
    for p in paths:
        if not p or not os.path.isfile(p):
            continue
        try:
            data = json.load(io.open(p, encoding="utf-8"))
        except Exception:
            continue
        keys = {}
        for item in data.get("keys", data if isinstance(data, list) else []):
            try:
                pub_hex = item.get("public_key", "")
                pub = bytes.fromhex(pub_hex)
                kid = item.get("key_id") or key_id_for(pub_hex)
                keys[kid] = {
                    "public": pub,
                    "not_before": item.get("not_before", ""),
                    "not_after": item.get("not_after", ""),
                    "revoked": bool(item.get("revoked", False)),
                }
            except Exception:
                continue
        if keys:
            return keys
    return {}


def _key_in_window(entry):
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    for field, cmp in (("not_before", "ge"), ("not_after", "le")):
        raw = entry.get(field) or ""
        if not raw:
            continue
        try:
            dt = datetime.datetime.strptime(raw, "%Y-%m-%d").replace(
                tzinfo=datetime.timezone.utc)
        except Exception:
            continue
        if field == "not_before" and now < dt:
            return False
        if field == "not_after" and now > dt:
            return False
    return not entry.get("revoked", False)


def verify_signature_envelope(data: bytes, signature_text: str, public_keys=None):
    """校验签名信封（JSON）或旧版裸 base64 签名。"""
    text = (signature_text or "").strip()
    if text.startswith("{"):
        try:
            env = json.loads(text)
        except Exception:
            return (False, "签名信封 JSON 无效")
        sigs = env.get("signatures") or [env]
        trusted = load_trusted_keys()
        legacy = list(public_keys) if public_keys is not None else default_public_keys()
        for item in sigs:
            kid = item.get("key_id", "")
            sig_b64 = item.get("signature") or item.get("sig") or ""
            entry = trusted.get(kid)
            if entry is not None:
                if not _key_in_window(entry):
                    continue
                return verify_ed25519(data, sig_b64, [entry["public"]])
            if not kid and legacy:
                ok, msg = verify_ed25519(data, sig_b64, legacy)
                if ok:
                    return (ok, msg)
        return (False, "信封中无可用/有效密钥签名")
    return verify_ed25519(data, text, public_keys)


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
