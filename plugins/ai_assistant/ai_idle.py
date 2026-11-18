# -*- coding: utf-8 -*-
"""AI 空会话就绪态（从结果对话框拆出，控制文件行数）。"""


def apply_idle_state(dlg):
    if dlg._worker is not None and dlg._worker.isRunning():
        return
    dlg.status_label.setText("就绪：选择代码后执行 AI 动作，或在下方继续追问")
    dlg.status_label.setStyleSheet("color: #888; padding: 4px; font-size: 12px;")
    dlg.progress.setVisible(False)
    dlg.cancel_btn.setVisible(False)
    dlg.follow_edit.setEnabled(True)
    dlg.follow_btn.setEnabled(True)
    dlg.copy_btn.setEnabled(bool(dlg._result_text))
    for name in ("replace_btn", "insert_btn", "diff_btn"):
        btn = getattr(dlg, name, None)
        if btn is not None:
            btn.setEnabled(bool(dlg._result_text))
