# -*- coding: utf-8 -*-
"""v2.17 无障碍深化：名称/缩放/焦点环/键盘审计"""
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_accessible_names(qapp):
    from PyQt5.QtWidgets import QLineEdit, QPushButton, QWidget

    from ui.accessibility import apply_accessible_names
    root = QWidget()
    btn = QPushButton("保存", root)
    edit = QLineEdit(root)
    edit.setPlaceholderText("搜索")
    n = apply_accessible_names(root)
    assert n >= 2
    assert btn.accessibleName() == "保存"
    assert edit.accessibleName()  # 兜底为类型名
    root.close()


def test_font_scale_and_restore(qapp):
    from PyQt5.QtWidgets import QPushButton, QWidget

    from ui.accessibility import apply_font_scale
    root = QWidget()
    btn = QPushButton("x", root)
    base = btn.font().pointSizeF()
    apply_font_scale(root, 1.5)
    scaled = btn.font().pointSizeF()
    assert scaled > base
    apply_font_scale(root, 1.0)
    restored = btn.font().pointSizeF()
    assert abs(restored - base) < 1.0
    root.close()


def test_focus_ring_qss():
    from ui.accessibility import focus_ring_qss
    qss = focus_ring_qss()
    assert "palette(highlight)" in qss
    assert ":focus" in qss


def test_keyboard_audit_strict_pass():
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    out = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools",
                                      "audit_keyboard_a11y.py"), "--strict"],
        cwd=ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "审计通过" in out.stdout


def test_a11y_wiring_and_docs():
    main = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
    assert "apply_accessibility_settings" in main
    win = open(os.path.join(ROOT, "ui", "main_window.py"),
               encoding="utf-8").read()
    assert "focus_ring_qss" in win
    prefs = open(os.path.join(ROOT, "ui", "preferences_panel.py"),
                 encoding="utf-8").read()
    assert "ui_scale_spin" in prefs
    assert os.path.exists(os.path.join(
        ROOT, "docs", "manual_validation_v2.17_a11y.md"))
    yml = open(os.path.join(ROOT, ".github", "workflows", "test.yml"),
               encoding="utf-8").read()
    assert "audit_keyboard_a11y.py --strict" in yml