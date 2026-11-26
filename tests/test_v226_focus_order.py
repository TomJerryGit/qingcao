# -*- coding: utf-8 -*-
"""键盘焦点审计逻辑"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QPushButton, QWidget

from tools.focus_order_audit import audit


def test_audit_detects_no_focus(qapp):
    w = QWidget()
    b = QPushButton("按钮", w)
    b.setFocusPolicy(Qt.NoFocus)
    w.show()
    try:
        issues = audit(w)
        assert any(x[0] == "no-focus" for x in issues)
    finally:
        w.hide(); w.close()
