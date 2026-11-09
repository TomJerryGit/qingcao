# -*- coding: utf-8 -*-
"""v2.23 D4：pywinpty 依赖/最小 PTY 会话/打包资源"""

import os
import sys

import pytest


def test_requirements_and_build_wired():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    req = open(os.path.join(root, "requirements.txt"), encoding="utf-8").read()
    assert "pywinpty" in req
    build = open(os.path.join(root, "build.py"), encoding="utf-8").read()
    assert "collect_winpty_assets" in build and "winpty" in build
    assert os.path.isfile(os.path.join(root, "ui", "pty_session.py"))


@pytest.mark.skipif(sys.platform != "win32", reason="仅 Windows PTY")
def test_pty_minimal_session():
    pytest.importorskip("winpty")
    from ui.pty_session import HAS_WINPTY, PtySession

    assert HAS_WINPTY
    session = PtySession(["cmd.exe", "/Q"])
    try:
        session.write("echo qc-pty-test\r\n")
        assert session.wait_for("qc-pty-test", timeout=12)
        assert session.is_alive()
    finally:
        session.close()


@pytest.mark.skipif(sys.platform != "win32", reason="仅 Windows PTY")
def test_winpty_package_assets():
    winpty = pytest.importorskip("winpty")
    pkg_dir = os.path.dirname(winpty.__file__)
    names = os.listdir(pkg_dir)
    assert any("winpty" in n.lower() for n in names), names
