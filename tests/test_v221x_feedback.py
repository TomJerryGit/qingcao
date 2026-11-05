# -*- coding: utf-8 -*-
"""v2.21.x 反馈收集：对话框/报告/入口"""

import json
import os


def test_feedback_dialog_save(qapp, tmp_path, monkeypatch):
    out = tmp_path / "feedback.jsonl"
    monkeypatch.setenv("QINGCAO_FEEDBACK_FILE", str(out))
    from ui.feedback_dialog import FeedbackDialog

    dlg = FeedbackDialog(None, version="2.21.2")
    try:
        assert dlg.save_feedback() is False  # 空内容拒绝
        dlg.text_edit.setPlainText("终端多标签很好用，希望有 PTY")
        dlg.category.setCurrentText("功能建议")
        dlg.contact.setText("test@example.com")
        assert dlg.save_feedback() is True
        rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 1
        assert rows[0]["category"] == "功能建议"
        assert rows[0]["version"] == "2.21.2"
        assert "PTY" in rows[0]["text"]
    finally:
        dlg.close()


def test_feedback_report(tmp_path):
    import importlib.util

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "qc_fb_report", os.path.join(root, "tools", "feedback_report.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fb = tmp_path / "f.jsonl"
    fb.write_text(
        json.dumps(
            {"iso": "2026-11-05 10:00", "category": "问题反馈", "text": "启动偶发卡顿"},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    rows = mod.load_feedback(str(fb))
    assert len(rows) == 1
    ev = mod.local_evidence()
    text = mod.render(rows, ev, generated="2026-11-05 10:00")
    assert "启动偶发卡顿" in text and "优先级建议" in text
    assert os.path.isfile(os.path.join(root, "docs", "user_feedback_report.md"))


def test_feedback_menu_wired():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mb = open(os.path.join(root, "ui", "mixins", "menu_builder_mixin.py"), encoding="utf-8").read()
    assert "反馈与建议" in mb and "_show_feedback" in mb
    cap = open(
        os.path.join(root, "ui", "mixins", "capability_wiring_mixin.py"), encoding="utf-8"
    ).read()
    assert "_show_feedback" in cap
    assert os.path.isfile(os.path.join(root, "docs", "v2.22_prioritization.md"))
