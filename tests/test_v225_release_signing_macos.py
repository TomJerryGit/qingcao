# -*- coding: utf-8 -*-
"""v3.0：Authenticode 条件签名 + macOS spike 工作流静态检查"""

import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def test_release_has_conditional_authenticode():
    t = _read(".github/workflows/release.yml")
    assert "Authenticode Sign (optional)" in t
    assert "WINDOWS_SIGN_CERT_BASE64" in t
    assert "signtool" in t and "Get-AuthenticodeSignature" in t
    assert "SIGNING_CERT_BASE64 != ''" in t
    assert os.path.isfile(os.path.join(ROOT, "docs", "authenticode_checklist.md"))


def test_macos_spike_workflow():
    t = _read(".github/workflows/macos-spike.yml")
    assert "macos-latest" in t and "upload-artifact" in t
    assert "QT_QPA_PLATFORM" in t
    assert os.path.isfile(os.path.join(ROOT, "docs", "macos_spike.md"))
