# -*- coding: utf-8 -*-
"""v2.23 P1-3：Linux AppImage 构建接线"""

import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_linux_build_wiring():
    assert os.path.isfile(os.path.join(ROOT, "tools", "build_linux_appimage.py"))
    assert os.path.isfile(os.path.join(ROOT, "requirements-linux-ci.txt"))
    yml = open(
        os.path.join(ROOT, ".github", "workflows", "linux-build.yml"), encoding="utf-8"
    ).read()
    assert "ubuntu-22.04" in yml
    assert "build_linux_appimage.py" in yml
    assert "QingCaoEditor-x86_64.AppImage" in yml
    assert "python3-pyqt5.qsci" in yml
    assert "AppImage launch smoke" in yml


def test_smoke_hook():
    main = "".join(open(os.path.join(ROOT, _p), encoding="utf-8").read() for _p in ("main.py", "app/main_helpers.py", "app/main_run.py"))
    assert "QINGCAO_HEADLESS_SMOKE" in main
    assert os.path.isfile(os.path.join(ROOT, "docs", "linux_appimage.md"))
