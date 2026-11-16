# -*- coding: utf-8 -*-
"""v2.26：macOS .app 冒烟工作流契约"""

import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_macos_spike_has_app_smoke():
    src = open(
        os.path.join(ROOT, ".github", "workflows", "macos-spike.yml"), encoding="utf-8"
    ).read()
    assert "QINGCAO_HEADLESS_SMOKE" in src
    assert "APP_SMOKE_OK" in src
    assert "Contents/MacOS" in src
