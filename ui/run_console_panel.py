# -*- coding: utf-8 -*-
"""内嵌运行控制台：QProcess + 输入框，支持 input() 交互。"""

import os

from PyQt5.QtCore import QProcess, QProcessEnvironment, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class RunConsolePanel(QDockWidget):
    def __init__(self, main_window=None):
        super().__init__("运行控制台", main_window)
        self.setObjectName("run_console")
        self.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        self._main = main_window

        body = QWidget(self)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(4, 4, 4, 4)
        self.output = QTextEdit(body)
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Consolas", 10))
        self.output.setAccessibleName("运行输出")
        layout.addWidget(self.output, 1)

        row = QHBoxLayout()
        self.input = QLineEdit(body)
        self.input.setPlaceholderText("输入后回车发送给程序（Ctrl+C 可点停止）")
        self.input.setAccessibleName("运行输入")
        self.input.returnPressed.connect(self.send_input)
        row.addWidget(self.input, 1)
        self.stop_btn = QPushButton("停止", body)
        self.stop_btn.clicked.connect(self.stop)
        self.clear_btn = QPushButton("清空", body)
        self.clear_btn.clicked.connect(self.output.clear)
        row.addWidget(self.stop_btn)
        row.addWidget(self.clear_btn)
        layout.addLayout(row)
        self.setWidget(body)

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.input.setEnabled(False)
        try:
            from ui.dock_title import install_close_button

            install_close_button(self, "运行控制台")
        except Exception:
            pass

    def run_file(self, filepath, interpreter="python"):
        self.stop()
        self.output.clear()
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUNBUFFERED", "1")
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(os.path.dirname(filepath) or ".")
        self.output.append("> %s -u %s\n" % (interpreter, filepath))
        self.process.start(interpreter, ["-u", filepath])
        self.input.setEnabled(True)
        self.input.setFocus()

    def run_batch(self, batch_path, cwd=None, label=""):
        self.stop()
        self.output.clear()
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(cwd or os.path.dirname(batch_path) or ".")
        self.output.append("> " + (label or batch_path) + "\n")
        self.process.start("cmd.exe", ["/c", batch_path])
        self.input.setEnabled(True)
        self.input.setFocus()

    def _read(self):
        data = bytes(self.process.readAllStandardOutput())
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("gbk", errors="replace")
        self.output.moveCursor(self.output.textCursor().End)
        self.output.insertPlainText(text)
        self.output.verticalScrollBar().setValue(self.output.verticalScrollBar().maximum())

    def _ensure_newline(self):
        text = self.output.toPlainText()
        if text and not text.endswith("\n"):
            self.output.insertPlainText("\n")

    def send_input(self):
        if self.process.state() == QProcess.NotRunning:
            return
        text = self.input.text()
        self._ensure_newline()
        self.output.append("> " + text)
        self.process.write((text + "\n").encode("utf-8"))
        self.input.clear()

    def stop(self):
        if self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1000):
                self.process.kill()
                self.process.waitForFinished(1000)
        self.input.setEnabled(False)

    def _finished(self, code, _status):
        self.input.setEnabled(False)
        self.output.append("\n[进程退出，代码 %s]" % code)

    def _error(self, _err):
        self.output.append("\n[启动失败: %s]" % self.process.errorString())

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)

    def refresh_theme(self, theme=None):
        try:
            from ui.dock_title import _theme_foreground

            fg = _theme_foreground(self)
            if theme is not None:
                fg = getattr(theme.colors, "foreground", fg)
            self.setStyleSheet("QDockWidget::title{color:%s;}" % fg)
        except Exception:
            pass
