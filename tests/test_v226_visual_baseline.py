# -*- coding: utf-8 -*-
"""视觉回归基线存在性"""
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMES = (
    "window_dark_night.png", "window_light_clean.png",
    "window_eye_protect.png", "window_high_contrast.png",
    "panel_dark_night.png", "panel_light_clean.png",
    "panel_eye_protect.png", "panel_high_contrast.png",
)


def test_theme_baseline_files():
    base = os.path.join(ROOT, "docs", "theme_baseline")
    for name in NAMES:
        path = os.path.join(base, name)
        assert os.path.isfile(path), name
        assert os.path.getsize(path) > 10000, name
