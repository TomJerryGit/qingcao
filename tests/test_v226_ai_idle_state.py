# -*- coding: utf-8 -*-
"""v2.26.13：空 AI 会话不应显示"正在生成"."""


def test_blank_session_idle_state(qapp):
    from plugins.ai_assistant.ai_result_dialog import AIResultDialog

    dlg = AIResultDialog(title="AI 对话", main_window=None)
    try:
        dlg.set_idle_state()
        assert "就绪" in dlg.status_label.text()
        assert not dlg.progress.isVisible()
        assert not dlg.cancel_btn.isVisible()
    finally:
        dlg.close()
