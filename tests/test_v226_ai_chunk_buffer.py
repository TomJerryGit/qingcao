# -*- coding: utf-8 -*-
"""AI 对话：空 active_key 时 chunk 不应被丢弃"""


def test_chunk_with_empty_active_key(qapp):
    from plugins.ai_assistant.ai_result_dialog import AIResultDialog

    d = AIResultDialog(title="t", main_window=None)
    try:
        d.set_idle_state()
        d._result_text = "BASE"
        d._chunk_start = 4
        d._chunk_session_key = ""
        d._on_chunk("HELLO")
        assert "HELLO" in d._result_text
        assert "HELLO" in d.browser.toPlainText()
    finally:
        d.close()
