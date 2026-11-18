# -*- coding: utf-8 -*-
"""插件签名信任（B3）：plugin.json.sig 由 trusted_keys 中的公钥验证。"""

import io
import os

from core.plugin_signature import is_revoked, verify_ed25519


def signature_path(plugin_dir):
    return os.path.join(plugin_dir, "plugin.json.sig")


def verify_plugin_signature(plugin_dir, public_keys=None):
    """返回 (trusted, message)。public_keys 为 bytes 列表（测试可注入）。"""
    manifest = os.path.join(plugin_dir, "plugin.json")
    sig_path = signature_path(plugin_dir)
    if not os.path.isfile(manifest):
        return (False, "缺少 plugin.json")
    if not os.path.isfile(sig_path):
        return (False, "缺少 plugin.json.sig")
    try:
        data = io.open(manifest, "rb").read()
        sig = io.open(sig_path, encoding="ascii").read().strip()
    except OSError as e:
        return (False, str(e))
    name = os.path.basename(os.path.abspath(plugin_dir))
    if is_revoked(name):
        return (False, "插件已被吊销")
    ok, msg = verify_ed25519(data, sig, public_keys)
    return (bool(ok), msg)


def env_fallback_allowed():
    """环境变量信任回退仅在 test/dev 且显式开启时允许。"""
    env = os.environ.get("QINGCAO_ENV", "production").strip().lower()
    if env not in ("test", "dev"):
        return False
    return os.environ.get("QINGCAO_TRUST_ENV_FALLBACK", "0") == "1"
