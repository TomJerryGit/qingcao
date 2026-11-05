# -*- coding: utf-8 -*-
"""反馈与建议对话框（v2.21.x）

仅本机保存（JSONL），不上传；用于收集真实使用反馈。
"""

import json
import os
import platform
import time

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def feedback_path():
    return os.environ.get("QINGCAO_FEEDBACK_FILE") or os.path.join(
        ROOT, "data", "feedback", "feedback.jsonl"
    )


class FeedbackDialog(QDialog):
    def __init__(self, parent=None, version=None):
        super().__init__(parent)
        self.setWindowTitle("反馈与建议")
        self.resize(520, 360)
        self._version = version or ""
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("类型"))
        self.category = QComboBox()
        self.category.addItems(["问题反馈", "功能建议", "其他"])
        layout.addWidget(self.category)

        layout.addWidget(QLabel("内容（必填）"))
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(
            "请描述遇到的问题/建议；可注明操作步骤、期望结果。\n"
            "反馈仅保存在本机 data/feedback/feedback.jsonl，不会上传。"
        )
        layout.addWidget(self.text_edit, 1)

        layout.addWidget(QLabel("联系方式（可选）"))
        self.contact = QLineEdit()
        self.contact.setPlaceholderText("邮箱/其他（可选）")
        layout.addWidget(self.contact)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #7ec850; font-size: 11px;")
        layout.addWidget(self.status)

        from PyQt5.QtWidgets import QHBoxLayout

        row = QHBoxLayout()
        save_btn = QPushButton("保存到本机")
        save_btn.clicked.connect(self.save_feedback)
        row.addWidget(save_btn)
        copy_btn = QPushButton("复制内容")
        copy_btn.clicked.connect(self._copy)
        row.addWidget(copy_btn)
        row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        layout.addLayout(row)

    def _copy(self):
        try:
            from PyQt5.QtWidgets import QApplication

            QApplication.clipboard().setText(self.text_edit.toPlainText())
            self.status.setText("已复制到剪贴板")
        except Exception:
            pass

    def save_feedback(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            self.status.setText("请先填写反馈内容")
            return False
        rec = {
            "ts": time.time(),
            "iso": time.strftime("%Y-%m-%d %H:%M:%S"),
            "version": self._version,
            "os": platform.platform(),
            "category": self.category.currentText(),
            "text": text,
            "contact": self.contact.text().strip(),
        }
        try:
            path = feedback_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self.status.setText("已保存到本机：%s" % path)
            return True
        except Exception as e:
            self.status.setText("保存失败：%s" % e)
            return False
