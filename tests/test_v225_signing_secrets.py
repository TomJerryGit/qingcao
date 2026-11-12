# -*- coding: utf-8 -*-
"""v3.0：签名 Secrets 检查工具"""

import importlib.util
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location(
        "qc_sign_check", os.path.join(ROOT, "tools", "check_signing_secrets.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_missing_detection():
    mod = _load()
    assert mod.missing(set()) == list(mod.REQUIRED)
    assert mod.missing(set(mod.REQUIRED)) == []
    assert mod.missing({"WINDOWS_SIGN_CERT_BASE64"}) == ["WINDOWS_SIGN_CERT_PASSWORD"]
