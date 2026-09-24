# -*- coding: utf-8 -*-
"""集成终端"""
import os
import sys
import subprocess
import threading
from PyQt5.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QLineEdit, QPushButton, QToolButton, QComboBox, QLabel,
    QApplication
)
from PyQt5.QtCore import Qt, QProcess, pyqtSignal
from PyQt5.QtGui import QFont, QColor


class TerminalPanel(QDockWidget):
    """集成终端面板"""

    def __init__(self, main_window=None, parent=None):
        super().__init__("终端", parent or main_window)
        self.main_window = main_window
        self.setObjectName("TerminalPanel")
        self.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)

        self.process = None
        self._cwd = os.getcwd()

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 工具条
        toolbar = QWidget()
        toolbar.setStyleSheet(
            "background-color: #2d2d2d; "
            "border-bottom: 1px solid #3c3c3c;"
        )
        top = QHBoxLayout(toolbar)
        top.setContentsMargins(6, 4, 6, 4)
        top.setSpacing(4)

        top.addWidget(QLabel("Shell:"))
        self.shell_combo = QComboBox()
        self.shell_combo.addItems([
            "PowerShell", "CMD", "Bash (WSL)"
        ])
        self.shell_combo.currentTextChanged.connect(self._on_shell_changed)
        top.addWidget(self.shell_combo)

        top.addStretch()

        clear_btn = QToolButton()
        clear_btn.setText("🗑")
        clear_btn.setToolTip("清空")
        clear_btn.clicked.connect(self._clear)
        top.addWidget(clear_btn)

        restart_btn = QToolButton()
        restart_btn.setText("🔄")
        restart_btn.setToolTip("重启终端")
        restart_btn.clicked.connect(self._restart)
        top.addWidget(restart_btn)

        layout.addWidget(toolbar)

        # 输出区
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Consolas", 10))
        self.output.setStyleSheet(
            "background-color: #0d0d0d; color: #d4d4d4; "
            "border: none; padding: 4px;"
        )
        layout.addWidget(self.output, 1)

        # 输入区
        input_widget = QWidget()
        input_widget.setStyleSheet(
            "background-color: #0d0d0d; border-top: 1px solid #3c3c3c;"
        )
        input_layout = QHBoxLayout(input_widget)
        input_layout.setContentsMargins(8, 4, 8, 4)
        input_layout.setSpacing(4)

        self.prompt_label = QLabel("$")
        self.prompt_label.setStyleSheet(
            "color: #7ec850; font-family: Consolas; font-weight: bold;"
        )
        input_layout.addWidget(self.prompt_label)

        self.input_edit = QLineEdit()
        self.input_edit.setStyleSheet(
            "background-color: #0d0d0d; color: #d4d4d4; "
            "border: none; font-family: Consolas; padding: 4px;"
        )
        self.input_edit.returnPressed.connect(self._on_send)
        input_layout.addWidget(self.input_edit, 1)

        layout.addWidget(input_widget)

        self.setWidget(container)


    def refresh_theme(self, theme):
        """主题变更时刷新样式（v3.0）"""
        try:
            from infrastructure.theme_loader import adapt_qss_colors
            # 保存原始 QSS（只保存一次）
            if not hasattr(self, '_original_qss') or not self._original_qss:
                self._original_qss = self.styleSheet()
            if self._original_qss:
                qss = adapt_qss_colors(self._original_qss, theme)
                self.setStyleSheet(qss)
        except Exception as e:
            print(f"[{self.__class__.__name__}] refresh_theme 失败: {e}")

    def _apply_style(self):
        self.setStyleSheet("""
            QDockWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QDockWidget::title {
                background-color: #2d2d2d;
                padding: 4px 8px;
                border-bottom: 1px solid #3c3c3c;
            }
            QToolButton {
                background-color: transparent;
                color: #d4d4d4;
                border: none;
                padding: 4px 8px;
            }
            QToolButton:hover {
                background-color: #3c3c3c;
                border-radius: 3px;
            }
            QComboBox {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px 6px;
            }
        """)

    def _on_shell_changed(self, shell_name):
        """shell 切换"""
        self._restart()

    def _restart(self):
        """重启终端"""
        if self.process:
            try:
                self.process.kill()
            except Exception:
                pass
            self.process = None

        self.output.clear()
        self._append_output("终端已重启\n", "#888")

        shell_name = self.shell_combo.currentText()

        if "PowerShell" in shell_name:
            cmd = ["powershell.exe", "-NoLogo"]
        elif "CMD" in shell_name:
            cmd = ["cmd.exe"]
        elif "WSL" in shell_name:
            cmd = ["wsl.exe", "bash"]
        else:
            cmd = ["cmd.exe"]

        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=self._cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW
                    if sys.platform == 'win32' else 0,
            )

            # 启动读取线程
            threading.Thread(
                target=self._read_output, daemon=True
            ).start()

            self._append_output(
                "已启动: " + " ".join(cmd) + "\n", "#7ec850"
            )
        except Exception as e:
            self._append_output(
                "启动失败: " + str(e) + "\n", "#f14c4c"
            )

    def _read_output(self):
        """读取输出"""
        try:
            while self.process and self.process.poll() is None:
                line = self.process.stdout.readline()
                if not line:
                    break
                self._append_output(line)
        except Exception:
            pass

    def _append_output(self, text, color=None):
        """追加输出"""
        cursor = self.output.textCursor()
        cursor.movePosition(cursor.End)
        cursor.insertText(text)
        self.output.setTextCursor(cursor)
        self.output.ensureCursorVisible()

    def _on_send(self):
        """发送命令"""
        cmd = self.input_edit.text()
        if not cmd:
            return

        self.input_edit.clear()

        # 显示命令
        self._append_output("$ " + cmd + "\n", "#7ec850")

        if not self.process or self.process.poll() is not None:
            self._append_output("终端未运行\n", "#f14c4c")
            return

        try:
            self.process.stdin.write(cmd + "\n")
            self.process.stdin.flush()
        except Exception as e:
            self._append_output("发送失败: " + str(e) + "\n", "#f14c4c")

    def _clear(self):
        """清空"""
        self.output.clear()

    def set_cwd(self, path):
        """设置工作目录"""
        if os.path.isdir(path):
            self._cwd = path
            self._append_output(
                "工作目录已切换到: " + path + "\n", "#4dabf7"
            )