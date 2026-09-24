# -*- coding: utf-8 -*-
"""性能剖析器面板"""
import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton,
    QLabel, QFileDialog, QMessageBox, QApplication, QComboBox
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from core.profiler import get_profiler


class ProfilerDialog(QDialog):
    """性能剖析对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("性能剖析")
        self.resize(900, 600)

        self.profiler = get_profiler()

        self._build_ui()
        self._apply_style()
        self._update_status()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 工具条
        top = QHBoxLayout()

        self.status_label = QLabel("未运行")
        self.status_label.setStyleSheet(
            "color: #888; padding: 4px;"
        )
        top.addWidget(self.status_label)

        top.addStretch()

        top.addWidget(QLabel("排序:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems([
            "cumulative", "time", "calls", "pcalls"
        ])
        top.addWidget(self.sort_combo)

        layout.addLayout(top)

        # 按钮
        btn_row = QHBoxLayout()

        self.start_btn = QPushButton("▶ 开始")
        self.start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setEnabled(False)
        btn_row.addWidget(self.stop_btn)

        btn_row.addStretch()

        self.save_btn = QPushButton("💾 保存报告")
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)

        btn_row.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

        # 报告
        self.report_view = QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setFont(QFont("Consolas", 10))
        layout.addWidget(self.report_view, 1)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; }
            QPlainTextEdit {
                background-color: #0d0d0d;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                font-family: Consolas, monospace;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #666;
            }
            QComboBox {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px;
            }
        """)

    def _update_status(self):
        if self.profiler.active:
            self.status_label.setText("● 运行中...")
            self.status_label.setStyleSheet(
                "color: #f0ad4e; font-weight: bold;"
            )
        else:
            self.status_label.setText("○ 未运行")
            self.status_label.setStyleSheet("color: #888;")

    def _on_start(self):
        if self.profiler.start():
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.report_view.clear()
            self._update_status()

    def _on_stop(self):
        result = self.profiler.stop(
            sort_by=self.sort_combo.currentText(),
            top_n=30
        )
        if result:
            self.report_view.setPlainText(result)

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._update_status()

    def _on_save(self):
        result = self.profiler.get_result()
        if not result:
            QMessageBox.information(self, "提示", "没有报告可保存")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "保存性能报告",
            "profile_report.txt",
            "文本文件 (*.txt)"
        )
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(result)
            QMessageBox.information(self, "已保存", path)