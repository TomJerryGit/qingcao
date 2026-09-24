#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文件关联设置对话框"""
import sys
import subprocess
import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QListWidget, QPushButton,
    QMessageBox, QLabel
)
from PyQt5.QtCore import Qt


class FileAssociationDialog(QDialog):
    """文件关联设置"""

    EXTENSIONS = [
        ".txt", ".py", ".log", ".csv", ".json", ".xml",
        ".md", ".ini", ".cfg", ".conf", ".js", ".ts",
        ".html", ".css", ".c", ".cpp", ".h", ".java",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("文件关联设置")
        self.resize(400, 450)

        layout = QVBoxLayout(self)

        info = QLabel(
            "选择要与青草编辑器关联的文件扩展名：\n"
            "（需要管理员权限才能生效）"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.MultiSelection)

        for ext in self.EXTENSIONS:
            self.list_widget.addItem(ext)

        layout.addWidget(self.list_widget)

        apply_btn = QPushButton("应用关联")
        apply_btn.clicked.connect(self._apply)
        layout.addWidget(apply_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; font-size: 12px; }
            QListWidget {
                background-color: #252526; color: #d4d4d4;
                border: 1px solid #3c3c3c; font-size: 12px;
            }
            QListWidget::item { padding: 4px 8px; }
            QListWidget::item:selected { background-color: #094771; }
            QPushButton {
                background-color: #0e639c; color: white;
                border: none; border-radius: 3px;
                padding: 6px 14px; font-size: 12px;
            }
            QPushButton:hover { background-color: #1177bb; }
        """)

    def _apply(self):
        """应用关联"""
        selected = [item.text() for item in self.list_widget.selectedItems()]

        if not selected:
            QMessageBox.information(self, "提示", "请先选择扩展名")
            return

        if sys.platform != 'win32':
            QMessageBox.information(
                self, "提示",
                "当前操作系统不支持自动关联，请手动配置。"
            )
            return

        exe_path = sys.executable

        try:
            success_count = 0

            for ext in selected:
                try:
                    subprocess.run([
                        'reg', 'add',
                        f'HKEY_CLASSES_ROOT\\{ext}\\shell\\QingCao\\command',
                        '/ve', '/d', f'"{exe_path}" "%1"', '/f'
                    ], capture_output=True, check=True)
                    success_count += 1
                except Exception:
                    continue

            QMessageBox.information(
                self, "完成",
                f"已关联 {success_count} 个扩展名。\n"
                f"可能需要重启系统生效。"
            )

        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))