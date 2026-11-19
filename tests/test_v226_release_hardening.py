# -*- coding: utf-8 -*-
"""Sprint 1：发布链路 ZIP 回退"""

import os
import sys
import zipfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_ensure_package_repacks_missing_zip(tmp_path, monkeypatch):
    from tools import ci_publish_release as rel

    monkeypatch.setattr(rel, "ROOT", str(tmp_path))
    src = tmp_path / "dist" / "QingCaoEditor"
    src.mkdir(parents=True)
    (src / "QingCaoEditor.exe").write_bytes(b"x")
    zip_path = str(tmp_path / "dist" / "QingCaoEditor-v9.9.9-windows.zip")
    assert rel.ensure_package(zip_path)
    assert os.path.isfile(zip_path)
    assert os.path.isfile(zip_path + ".sha256.txt")
    with zipfile.ZipFile(zip_path) as z:
        assert "QingCaoEditor.exe" in z.namelist()
