# -*- coding: utf-8 -*-
"""v2.24.x UX：首启向导（离屏渲染 + 步骤）"""

import os


def test_onboarding_steps_and_render(tmp_path, qapp):
    from PyQt5.QtGui import QPixmap

    from ui.onboarding import OnboardingDialog

    dlg = OnboardingDialog()
    try:
        assert dlg.current_step() == 0
        assert dlg._next.text() == "下一步"
        dlg._on_next()
        assert dlg.current_step() == 1
        dlg._on_prev()
        assert dlg.current_step() == 0
        dlg._on_next()
        dlg._on_next()
        assert dlg._next.text() == "开始使用"
        dlg.show()
        dlg.adjustSize()
        pix = QPixmap(dlg.size())
        dlg.render(pix)
        out = os.path.join(str(tmp_path), "onboarding.png")
        assert pix.save(out) is True
        assert os.path.getsize(out) > 1000
    finally:
        dlg.close()


def test_onboarding_marker_roundtrip(qapp):
    from ui import onboarding

    onboarding.mark_onboarding_done()
    assert onboarding.should_show_onboarding() is False
