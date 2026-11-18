# -*- coding: utf-8 -*-
"""v2.26：插件注册表自动刷新工作流"""

import io
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_registry_workflow_exists():
    path = os.path.join(ROOT, ".github", "workflows", "plugin-registry.yml")
    assert os.path.exists(path)
    text = io.open(path, encoding="utf-8").read()
    assert "release:" in text
    assert "publish_registry_release.py" in text
    assert "contents: write" in text
