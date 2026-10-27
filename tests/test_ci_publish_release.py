# -*- coding: utf-8 -*-
"""P3：发布说明自动附加包体积/SHA 报告"""
import importlib.util
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    path = os.path.join(ROOT, "tools", "ci_publish_release.py")
    spec = importlib.util.spec_from_file_location("qc_ci_release", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_compose_body_appends_report(tmp_path):
    m = _load()
    zip_path = tmp_path / "pkg.zip"
    zip_path.write_bytes(b"x" * 1048576)
    sha_path = tmp_path / "pkg.zip.sha256.txt"
    sha_path.write_text("abc  pkg.zip\n", encoding="ascii")
    out = m.compose_body("# 标题\n\n正文", str(zip_path), str(sha_path))
    assert "# 标题" in out and "正文" in out
    assert "包信息（自动生成）" in out
    assert "pkg.zip" in out and "MB" in out
    assert "SHA256" in out and len(out) > 40


def test_build_payload_fields():
    m = _load()
    p = m.build_payload("v9.9.9", "body")
    assert p["tag_name"] == "v9.9.9"
    assert p["draft"] is False and p["prerelease"] is False

def test_compose_body_size_delta(tmp_path):
    m = _load()
    zip_path = tmp_path / "pkg.zip"
    zip_path.write_bytes(b"x" * (2 * 1048576))
    sha_path = tmp_path / "pkg.zip.sha256.txt"
    sha_path.write_text("abc  pkg.zip\n", encoding="ascii")
    out = m.compose_body("body", str(zip_path), str(sha_path),
                         prev_size=1048576)
    assert "较上一版" in out
    assert "+1.00 MB" in out and "+100.0%" in out
    first = m.compose_body("body", str(zip_path), str(sha_path))
    assert "首次发布/未知" in first
