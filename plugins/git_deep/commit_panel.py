# -*- coding: utf-8 -*-
"""Git 提交面板"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class CommitPanel(QDialog):
    """Git 提交面板"""

    def __init__(self, git_client, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Git 提交")
        self.resize(600, 500)

        self.git = git_client

        layout = QVBoxLayout(self)

        # 变更列表
        layout.addWidget(QLabel("变更:"))
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        # 提交信息
        layout.addWidget(QLabel("提交信息:"))
        self.msg_edit = QTextEdit()
        self.msg_edit.setMaximumHeight(120)
        layout.addWidget(self.msg_edit)

        # 按钮
        btn_layout = QHBoxLayout()

        ok_btn = QPushButton("✓ 提交")
        ok_btn.setStyleSheet(
            "background-color: #7ec850; color: white;"
        )
        ok_btn.clicked.connect(self._on_commit)
        btn_layout.addWidget(ok_btn)

        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        self._load_status()

    def _load_status(self):
        """加载变更"""
        try:
            status = self.git.status()
            for fp, code in status.items():
                item = QListWidgetItem(f"[{code}] {fp}")
                item.setCheckState(Qt.Checked)
                item.setData(Qt.UserRole, fp)
                self.list_widget.addItem(item)
        except Exception as e:
            self.list_widget.addItem(f"(加载失败: {e})")

    def _on_commit(self):
        """提交"""
        msg = self.msg_edit.toPlainText().strip()
        if not msg:
            return

        # 暂存选中的文件
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                fp = item.data(Qt.UserRole)
                if fp:
                    self.git.add(fp)

        success, output = self.git.commit(msg)
        if success:
            self.accept()
        else:
            self.msg_edit.setText(output)

    def get_message(self):
        return self.msg_edit.toPlainText().strip()