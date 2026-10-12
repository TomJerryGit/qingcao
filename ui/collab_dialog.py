# -*- coding: utf-8 -*-
"""协作编辑对话框"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class CollabDialog(QDialog):
    """协作编辑对话框"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent or main_window)
        self.setWindowTitle("协作编辑")
        self.resize(500, 400)

        self.main_window = main_window
        self.session = None

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        # 主机模式
        host_tab = QWidget()
        host_layout = QVBoxLayout(host_tab)

        host_layout.addWidget(QLabel(
            "启动主机，让其他人连接到你的会话。"
        ))

        host_layout.addWidget(QLabel("端口:"))
        self.host_port = QLineEdit("52000")
        host_layout.addWidget(self.host_port)

        host_layout.addWidget(QLabel("房间名:"))
        self.host_room = QLineEdit("default")
        host_layout.addWidget(self.host_room)

        self.start_host_btn = QPushButton("▶ 启动主机")
        self.start_host_btn.clicked.connect(self._on_start_host)
        host_layout.addWidget(self.start_host_btn)

        self.host_status = QLabel("")
        self.host_status.setStyleSheet("color: #7ec850;")
        host_layout.addWidget(self.host_status)

        host_layout.addStretch()
        tabs.addTab(host_tab, "作为主机")

        # 客户端模式
        join_tab = QWidget()
        join_layout = QVBoxLayout(join_tab)

        join_layout.addWidget(QLabel(
            "加入其他主机的会话。"
        ))

        join_layout.addWidget(QLabel("主机地址:"))
        self.join_host = QLineEdit("127.0.0.1")
        join_layout.addWidget(self.join_host)

        join_layout.addWidget(QLabel("端口:"))
        self.join_port = QLineEdit("52000")
        join_layout.addWidget(self.join_port)

        join_layout.addWidget(QLabel("房间名:"))
        self.join_room = QLineEdit("default")
        join_layout.addWidget(self.join_room)

        self.join_btn = QPushButton("🔗 加入")
        self.join_btn.clicked.connect(self._on_join)
        join_layout.addWidget(self.join_btn)

        self.join_status = QLabel("")
        self.join_status.setStyleSheet("color: #7ec850;")
        join_layout.addWidget(self.join_status)

        join_layout.addStretch()
        tabs.addTab(join_tab, "加入会话")

        layout.addWidget(tabs)

        # 用户列表
        layout.addWidget(QLabel("在线用户:"))
        self.users_list = QListWidget()
        self.users_list.setMaximumHeight(120)
        layout.addWidget(self.users_list)

        # 底部
        bottom = QHBoxLayout()
        bottom.addStretch()

        self.leave_btn = QPushButton("离开")
        self.leave_btn.setEnabled(False)
        self.leave_btn.clicked.connect(self._on_leave)
        bottom.addWidget(self.leave_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)

        layout.addLayout(bottom)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; }
            QLineEdit {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 6px;
            }
            QLineEdit:focus { border-color: #007acc; }
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
            QTabWidget::pane {
                border: 1px solid #3c3c3c;
                background-color: #252526;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #d4d4d4;
                padding: 6px 14px;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: #7ec850;
            }
            QListWidget {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
            }
        """)

    def _on_start_host(self):
        from core.collab import CollabSession
        try:
            port = int(self.host_port.text())
        except ValueError:
            QMessageBox.warning(self, "错误", "端口号无效")
            return

        self.session = CollabSession()
        self.session.user_joined.connect(self._on_user_joined)
        self.session.user_left.connect(self._on_user_left)
        self.session.error_occurred.connect(
            lambda e: QMessageBox.warning(self, "错误", e)
        )

        if self.session.start_host(port, self.host_room.text()):
            self.host_status.setText(
                "✓ 主机已启动，端口 " + str(port)
            )
            self.start_host_btn.setEnabled(False)
            self.leave_btn.setEnabled(True)
            self.users_list.addItem(
                "👤 %s (你)" % self.session.user_name
            )

    def _on_join(self):
        from core.collab import CollabSession
        try:
            port = int(self.join_port.text())
        except ValueError:
            QMessageBox.warning(self, "错误", "端口号无效")
            return

        self.session = CollabSession()
        self.session.connected.connect(
            lambda: self.join_status.setText("✓ 已连接")
        )
        self.session.user_joined.connect(self._on_user_joined)
        self.session.user_left.connect(self._on_user_left)
        self.session.error_occurred.connect(
            lambda e: QMessageBox.warning(self, "错误", e)
        )

        if self.session.join(self.join_host.text(), port,
                             self.join_room.text()):
            self.users_list.addItem(
                "👤 %s (你)" % self.session.user_name
            )
            self.leave_btn.setEnabled(True)
            self.join_btn.setEnabled(False)

    def _on_user_joined(self, user_id, user_name):
        self.users_list.addItem("👤 " + user_name)

    def _on_user_left(self, user_id):
        # 简单实现：清空重加
        pass

    def _on_leave(self):
        if self.session:
            self.session.leave()
            self.session = None
        self.users_list.clear()
        self.leave_btn.setEnabled(False)
        self.start_host_btn.setEnabled(True)
        self.join_btn.setEnabled(True)
        self.host_status.setText("")
        self.join_status.setText("")