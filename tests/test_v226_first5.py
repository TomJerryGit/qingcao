# -*- coding: utf-8 -*-
"""首次启动 5 分钟流程"""
from PyQt5.QtWidgets import QLabel


def test_finish_page_has_quick_start(qapp):
    from ui.first_run_wizard import FirstRunWizard

    w = FirstRunWizard()
    try:
        text = "\n".join(lbl.text() for lbl in w.findChildren(QLabel))
        assert "F5" in text
        assert w.finish_page.is_telemetry() is False
    finally:
        w.close()
