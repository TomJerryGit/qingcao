# -*- coding: utf-8 -*-
"""会话快照管理"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QMessageBox, QInputDialog
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from core.snapshot import SnapshotManager


class SnapshotDialog(QDialog):
    """会话快照对话框"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window)
        self.setWindowTitle("会话快照")
        self.resize(500, 400)

        self.main_window = main_window
        self.mgr = SnapshotManager()

        self._build_ui()
        self._apply_style()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "快照可保存当前所有打开的文件、光标位置、窗口布局，"
            "随时一键恢复。"
        ))

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_restore)
        layout.addWidget(self.list_widget, 1)

        # 按钮
        btn_layout = QHBoxLayout()

        new_btn = QPushButton("➕ 新建快照")
        new_btn.clicked.connect(self._on_new)
        btn_layout.addWidget(new_btn)

        restore_btn = QPushButton("↺ 恢复")
        restore_btn.clicked.connect(self._on_restore)
        btn_layout.addWidget(restore_btn)

        delete_btn = QPushButton("🗑 删除")
        delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; }
            QListWidget {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #2d2d2d;
            }
            QListWidget::item:hover { background-color: #2a2d2e; }
            QListWidget::item:selected { background-color: #094771; }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #1177bb; }
        """)

    def refresh(self):
        self.list_widget.clear()
        for snap in self.mgr.list_snapshots():
            created = snap['created_at'][:19].replace('T', ' ')
            item = QListWidgetItem(
                "📸 %s\n    %d 个文件 · %s"
                % (snap['name'], snap['file_count'], created)
            )
            item.setData(Qt.UserRole, snap['name'])
            self.list_widget.addItem(item)

    def _on_new(self):
        name, ok = QInputDialog.getText(
            self, "新建快照", "快照名称:",
            text="快照_" + __import__('datetime').datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )
        )
        if not ok or not name.strip():
            return

        tabs = self.main_window.tabs
        if self.mgr.save_snapshot(name.strip(), tabs, self.main_window):
            QMessageBox.information(self, "成功", "快照已保存")
            self.refresh()
        else:
            QMessageBox.warning(self, "失败", "保存失败")

    def _on_restore(self):
        item = self.list_widget.currentItem()
        if not item:
            return

        name = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "恢复快照",
            "恢复快照 '%s'？\n\n当前打开的所有标签会被关闭。" % name,
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        count = self.mgr.restore_snapshot(
            name, self.main_window.tabs, self.main_window
        )
        QMessageBox.information(
            self, "成功", "已恢复 %d 个文件" % count
        )

    def _on_delete(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "确认删除", "删除快照 '%s'？" % name
        )
        if reply == QMessageBox.Yes:
            self.mgr.delete_snapshot(name)
            self.refresh()