# -*- coding: utf-8 -*-
"""集成终端面板（v2.21 P2：多标签 + ANSI 色彩）

每标签独立 QProcess/cwd；输出支持基础 ANSI SGR 颜色。
安全：不自动执行命令、不落盘历史；关闭时 terminate→kill。
"""

import html
import os
import re
import sys

from PyQt5.QtCore import QProcess, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


_ANSI_RE = re.compile(r"\x1b\[([0-9;]*)m")
_COLORS = {
    30: "#1e1e1e",
    31: "#e06c75",
    32: "#98c379",
    33: "#e5c07b",
    34: "#61afef",
    35: "#c678dd",
    36: "#56b6c2",
    37: "#dcdfe4",
    90: "#5c6370",
    91: "#e06c75",
    92: "#98c379",
    93: "#e5c07b",
    94: "#61afef",
    95: "#c678dd",
    96: "#56b6c2",
    97: "#ffffff",
}


def ansi_to_html(text):
    """把 ANSI SGR 转成 HTML（颜色/粗体），未知码忽略。"""
    out = []
    pos = 0
    color = None
    bold = False
    for m in _ANSI_RE.finditer(text):
        chunk = text[pos : m.start()]
        if chunk:
            esc = html.escape(chunk).replace("\n", "<br>")
            style = []
            if color:
                style.append("color:%s" % color)
            if bold:
                style.append("font-weight:bold")
            out.append('<span style="%s">%s</span>' % (";".join(style), esc) if style else esc)
        codes = [int(x) for x in (m.group(1) or "0").split(";") if x.strip().isdigit()]
        for c in codes or [0]:
            if c == 0:
                color = None
                bold = False
            elif c == 1:
                bold = True
            elif c == 22:
                bold = False
            elif c == 39:
                color = None
            elif c in _COLORS:
                color = _COLORS[c]
        pos = m.end()
    tail = text[pos:]
    if tail:
        esc = html.escape(tail).replace("\n", "<br>")
        style = []
        if color:
            style.append("color:%s" % color)
        if bold:
            style.append("font-weight:bold")
        out.append('<span style="%s">%s</span>' % (";".join(style), esc) if style else esc)
    return "".join(out)


class HistoryLineEdit(QLineEdit):
    """带命令历史（↑/↓）的输入框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history = []
        self._hist_idx = 0

    def add_history(self, cmd):
        cmd = (cmd or "").strip()
        if cmd and (not self._history or self._history[-1] != cmd):
            self._history.append(cmd)
        self._hist_idx = len(self._history)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Up and self._history:
            self._hist_idx = max(0, self._hist_idx - 1)
            self.setText(self._history[self._hist_idx])
            event.accept()
            return
        if event.key() == Qt.Key_Down and self._history:
            if self._hist_idx < len(self._history) - 1:
                self._hist_idx += 1
                self.setText(self._history[self._hist_idx])
            else:
                self._hist_idx = len(self._history)
                self.clear()
            event.accept()
            return
        super().keyPressEvent(event)


class TerminalTab(QWidget):
    """单标签终端（独立进程与 cwd）"""

    def __init__(self, cwd, parent=None):
        super().__init__(parent)
        self._cwd = cwd
        self._proc = None
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(4)

        row = QHBoxLayout()
        self.cwd_label = QLabel(self._cwd)
        self.cwd_label.setStyleSheet("color: #888; font-size: 11px;")
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

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Consolas", 10))
        self.output.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; border: 1px solid #3c3c3c; }"
        )
        vbox.addWidget(self.output, 1)

        inrow = QHBoxLayout()
        prompt = QLabel("$")
        prompt.setStyleSheet("color: #7ec850; font-weight: bold;")
        inrow.addWidget(prompt)
        self.input = HistoryLineEdit()
        self.input.setPlaceholderText("输入命令，Enter 执行（单命令模式）")
        self.input.returnPressed.connect(self.run_command)
        inrow.addWidget(self.input, 1)
        run_btn = QPushButton("运行")
        run_btn.setFixedWidth(60)
        run_btn.clicked.connect(self.run_command)
        inrow.addWidget(run_btn)
        vbox.addLayout(inrow)

    def _append(self, text):
        if not text:
            return
        escaped = html.escape(str(text).rstrip("\n")).replace("\n", "<br>")
        self.output.append(escaped)

    def _append_ansi(self, text):
        if not text:
            return
        self.output.moveCursor(self.output.textCursor().End)
        self.output.insertHtml(ansi_to_html(text))
        self.output.ensureCursorVisible()

    def clear_output(self):
        self.output.clear()

    def copy_output(self):
        try:
            from PyQt5.QtWidgets import QApplication

            QApplication.clipboard().setText(self.output.toPlainText())
        except Exception:
            pass

    def _shell(self):
        if sys.platform == "win32":
            return "powershell.exe", ["-NoProfile", "-NonInteractive", "-Command"]
        return "/bin/sh", ["-c"]

    def run_command(self):
        cmd = self.input.text().strip()
        if not cmd:
            return
        self.input.add_history(cmd)
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
            lambda: self._append_ansi(
                bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
            )
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

    def terminate(self):
        try:
            if self._proc is not None and self._proc.state() != QProcess.NotRunning:
                self._proc.terminate()
                if not self._proc.waitForFinished(800):
                    self._proc.kill()
        except Exception:
            pass
        self._proc = None


class TerminalPanel(QDockWidget):
    def __init__(self, main_window=None):
        super().__init__("终端", main_window)
        self.main_window = main_window
        self.setObjectName("TerminalDock")
        self._default = self._default_cwd()
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        add_btn = QToolButton()
        add_btn.setText("+")
        add_btn.setToolTip("新建终端标签")
        add_btn.clicked.connect(lambda: self.add_tab())
        self.tabs.setCornerWidget(add_btn, Qt.TopRightCorner)
        self.setWidget(self.tabs)
        self.add_tab()
        self.resize(760, 260)

    # ---------- 兼容单标签 API ----------
    @property
    def _tab(self):
        w = self.tabs.currentWidget()
        return w

    @property
    def input(self):
        return self._tab.input

    @property
    def output(self):
        return self._tab.output

    @property
    def _proc(self):
        return self._tab._proc if self._tab else None

    @property
    def _cwd(self):
        return self._tab._cwd if self._tab else self._default

    @property
    def cwd_label(self):
        return self._tab.cwd_label

    def run_command(self):
        if self._tab:
            self._tab.run_command()

    def clear_output(self):
        if self._tab:
            self._tab.clear_output()

    def copy_output(self):
        if self._tab:
            self._tab.copy_output()

    # ---------- 多标签 ----------
    def add_tab(self, cwd=None):
        tab = TerminalTab(cwd or self._default)
        idx = self.tabs.addTab(tab, "终端 %d" % (self.tabs.count() + 1))
        self.tabs.setCurrentIndex(idx)
        tab.input.setFocus()
        return tab

    def close_tab(self, index):
        if self.tabs.count() <= 1:
            return
        w = self.tabs.widget(index)
        if w is not None:
            w.terminate()
        self.tabs.removeTab(index)
        w.deleteLater()

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

    def refresh_theme(self, theme):
        try:
            colors = getattr(theme, "colors", {}) or {}
            bg = colors.get("background") or "#1e1e1e"
            fg = colors.get("foreground") or "#d4d4d4"
            border = colors.get("border") or "#3c3c3c"
            for i in range(self.tabs.count()):
                tab = self.tabs.widget(i)
                if tab is not None:
                    tab.output.setStyleSheet(
                        "QTextEdit { background-color: %s; color: %s;"
                        " border: 1px solid %s; }" % (bg, fg, border)
                    )
        except Exception:
            pass

    def closeEvent(self, event):
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if tab is not None:
                tab.terminate()
        super().closeEvent(event)
