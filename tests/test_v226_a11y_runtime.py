# -*- coding: utf-8 -*-
"""运行时无障碍审计逻辑"""
from PyQt5.QtWidgets import QPushButton

from tools.a11y_runtime_audit import audit


def test_audit_detects_unnamed_button(qapp):
    from PyQt5.QtWidgets import QWidget

    w = QWidget()
    b = QPushButton("", w)
    b.setToolTip("")
    b.setAccessibleName("")
    w.show()
    try:
        issues = audit(w)
        assert any(x[0] == "button" for x in issues)
    finally:
        w.hide(); w.close()
