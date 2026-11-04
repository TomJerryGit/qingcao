# -*- coding: utf-8 -*-
"""集成终端面板 MVP（v2.21 P1-1）

单命令执行模型：输入命令 -> QProcess 执行 -> 输出回显（异步、可清理）。
不自动执行命令、不落盘历史；关闭面板/退出时终止进程。
"""

import os
import sys

from PyQt5.QtCore import QProcess
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class TerminalPanel(QDockWidget):
    def __init__(self, main_window=None):
        super().__init__("终端", main_window)
        self.main_window = main_window
        self.setObjectName("TerminalDock")
        self._proc = None
        self._cwd = self._default_cwd()

        body = QWidget()
        vbox = QVBoxLayout(body)
        vbox.setContentsMargins(6, 6, 6, 6)
        vbox.setSpacing(4)

        row = QHBoxLayout()
        self.cwd_label = QLabel(self._cwd)
        self.cwd_label.setStyleSheet("color: #888; font-size: 11px;")
        self.cwd_label.setTextInteractionFlags(self.cwd_label.textInteractionFlags())
        row.addWidget(self.cwd_label, 1)
        clear_btn = QPushButton("清屏")
        clear_btn.setFixedWidth(60)
        clear_btn.clicked.connect(self.clear_output)
        row.addWidget(clear_btn)
        copy_btn = QPushButton("复制")
        copy_btn.setFixedWidth(60)
        copy_btn.clicked.connect(self.copy_output)
        row.addWidget(copy_btn)
        vbox.addLayout(row)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Consolas", 10))
        self.output.setStyleSheet(
            "QPlainTextEdit { background-color: #1e1e1e; color: #d4d4d4;"
            " border: 1px solid #3c3c3c; }"
        )
        vbox.addWidget(self.output, 1)

        inrow = QHBoxLayout()
        prompt = QLabel("$")
        prompt.setStyleSheet("color: #7ec850; font-weight: bold;")
        inrow.addWidget(prompt)
        self.input = QLineEdit()
        self.input.setPlaceholderText("输入命令，Enter 执行（单命令模式）")
        self.input.returnPressed.connect(self.run_command)
        inrow.addWidget(self.input, 1)
        run_btn = QPushButton("运行")
        run_btn.setFixedWidth(60)
        run_btn.clicked.connect(self.run_command)
        inrow.addWidget(run_btn)
        vbox.addLayout(inrow)

        self.setWidget(body)
        self.resize(700, 240)

    # ---------------- 基础 ----------------
    def _default_cwd(self):
        try:
            w = self.main_window
            for attr in ("_current_project", "project_root", "current_project"):
                proj = getattr(w, attr, None) if w is not None else None
                root = getattr(proj, "root", None) or (proj if isinstance(proj, str) else None)
                if root and os.path.isdir(str(root)):
                    return str(root)
        except Exception:
            pass
        return os.getcwd()

    def _append(self, text):
        if not text:
            return
        self.output.appendPlainText(str(text).rstrip("\n"))

    def clear_output(self):
        self.output.clear()

    def copy_output(self):
        try:
            from PyQt5.QtWidgets import QApplication

            QApplication.clipboard().setText(self.output.toPlainText())
        except Exception:
            pass

    # ---------------- 执行 ----------------
    def _shell(self):
        if sys.platform == "win32":
            return "powershell.exe", ["-NoProfile", "-NonInteractive", "-Command"]
        return "/bin/sh", ["-c"]

    def run_command(self):
        cmd = self.input.text().strip()
        if not cmd:
            return
        self.input.clear()
        self._append("> " + cmd)
        low = cmd.lower()
        if low.startswith("cd "):
            target = cmd[3:].strip().strip('"').strip("'")
            path = target if os.path.isabs(target) else os.path.join(self._cwd, target)
            path = os.path.abspath(path)
            if os.path.isdir(path):
                self._cwd = path
                self.cwd_label.setText(path)
                self._append("cwd: " + path)
            else:
                self._append("目录不存在: " + target)
            return
        if self._proc is not None:
            self._append("[提示] 上一条命令仍在执行")
            return
        shell, args = self._shell()
        proc = QProcess(self)
        proc.setWorkingDirectory(self._cwd)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(
            lambda: self._append(bytes(proc.readAllStandardOutput()).decode("utf-8", "replace"))
        )
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(
            lambda _e: (self._append("[错误] 无法启动 shell"), self._clear_proc())
        )
        self._proc = proc
        proc.start(shell, args + [cmd])

    def _clear_proc(self):
        self._proc = None

    def _on_finished(self, code, _status):
        self._append("[退出码 %s]" % code)
        self._clear_proc()

    # ---------------- 主题/清理 ----------------
    def refresh_theme(self, theme):
        try:
            colors = getattr(theme, "colors", {}) or {}
            bg = colors.get("background") or "#1e1e1e"
            fg = colors.get("foreground") or "#d4d4d4"
            border = colors.get("border") or "#3c3c3c"
            self.output.setStyleSheet(
                "QPlainTextEdit { background-color: %s; color: %s;"
                " border: 1px solid %s; }" % (bg, fg, border)
            )
        except Exception:
            pass

    def closeEvent(self, event):
        try:
            if self._proc is not None and self._proc.state() != QProcess.NotRunning:
                self._proc.terminate()
                if not self._proc.waitForFinished(800):
                    self._proc.kill()
        except Exception:
            pass
        self._proc = None
        super().closeEvent(event)
