# -*- coding: utf-8 -*-
"""集成终端面板（v2.21 P2：多标签 + ANSI 色彩）

每标签独立 QProcess/cwd；输出支持基础 ANSI SGR 颜色。
安全：不自动执行命令、不落盘历史；关闭时 terminate→kill。
"""

import html
import os
import re
import sys

from PyQt5.QtCore import QProcess, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont


try:
    from ui.pty_session import HAS_PTY, HAS_WINPTY, PtySession
except Exception:  # pragma: no cover
    HAS_WINPTY = False
    PtySession = None

from PyQt5.QtWidgets import (
    QDialog,
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
    """单命令终端标签（独立进程与 cwd）"""

    kind = "oneshot"

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


def key_event_to_bytes(event):
    """把 QKeyEvent 映射为 PTY 原始字节（P1 raw 输入直通）。"""
    key = event.key()
    mods = event.modifiers()
    ctrl = bool(mods & Qt.ControlModifier)
    text = event.text()
    special = {
        Qt.Key_Return: "\r",
        Qt.Key_Enter: "\r",
        Qt.Key_Backspace: "\x7f",
        Qt.Key_Tab: "\t",
        Qt.Key_Escape: "\x1b",
        Qt.Key_Up: "\x1b[A",
        Qt.Key_Down: "\x1b[B",
        Qt.Key_Right: "\x1b[C",
        Qt.Key_Left: "\x1b[D",
        Qt.Key_Home: "\x1b[H",
        Qt.Key_End: "\x1b[F",
        Qt.Key_Delete: "\x1b[3~",
        Qt.Key_PageUp: "\x1b[5~",
        Qt.Key_PageDown: "\x1b[6~",
    }
    if ctrl and Qt.Key_A <= key <= Qt.Key_Z:
        return chr(key - Qt.Key_A + 1)
    if key in special:
        return special[key]
    if text:
        return text
    return ""


from ui.terminal_screen import TerminalScreen


class TerminalHistoryDialog(QDialog):
    """独立 scrollback 视图：查看/复制终端历史（不干扰实时渲染）。"""

    def __init__(self, screen, parent=None):
        super().__init__(parent)
        self.setWindowTitle("终端历史")
        self.resize(760, 520)
        layout = QVBoxLayout(self)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setFont(QFont("Consolas", 10))
        text = "\n".join(screen.scrollback_lines())
        live = screen.text()
        self.view.setPlainText((text + "\n" if text else "") + live)
        layout.addWidget(self.view, 1)
        row = QHBoxLayout()
        copy_btn = QPushButton("复制全部")
        copy_btn.clicked.connect(self._copy)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        row.addStretch(1)
        row.addWidget(copy_btn)
        row.addWidget(close_btn)
        layout.addLayout(row)

    def _copy(self):
        try:
            from PyQt5.QtWidgets import QApplication

            QApplication.clipboard().setText(self.view.toPlainText())
        except Exception:
            pass


class TerminalOutput(QTextEdit):
    """输出区：把鼠标事件按 VT 协议回传给 PTY（P4 鼠标上报）。"""

    mouse_input = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._screen = None
        self._pressed = False
        self._button = 0
        self.setMouseTracking(True)

    def _cell(self, event):
        fm = self.fontMetrics()
        col = int(event.x() / max(1, fm.horizontalAdvance("M"))) + 1
        row = int(event.y() / max(1, fm.height())) + 1
        return col, row

    def mousePressEvent(self, event):
        if self._screen is not None and self._screen.mouse_reporting:
            button = {Qt.LeftButton: 0, Qt.MiddleButton: 1, Qt.RightButton: 2}.get(
                event.button(), 0
            )
            self._pressed, self._button = True, button
            col, row = self._cell(event)
            data = self._screen.encode_mouse(button, col, row, True)
            if data:
                self.mouse_input.emit(data)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pressed and self._screen is not None and self._screen.mouse_reporting:
            col, row = self._cell(event)
            data = self._screen.encode_mouse(self._button, col, row, False)
            self._pressed = False
            if data:
                self.mouse_input.emit(data)
                event.accept()
                return
        self._pressed = False
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._pressed
            and self._screen is not None
            and (1002 in self._screen.mouse_reporting or 1003 in self._screen.mouse_reporting)
        ):
            col, row = self._cell(event)
            data = self._screen.encode_mouse(self._button, col, row, True, motion=True)
            if data:
                self.mouse_input.emit(data)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        if self._screen is not None and self._screen.mouse_reporting:
            col, row = self._cell(event)
            data = self._screen.encode_wheel(event.angleDelta().y() > 0, col, row)
            if data:
                self.mouse_input.emit(data)
                event.accept()
                return
        super().wheelEvent(event)


class PtyLineEdit(HistoryLineEdit):
    """PTY 输入框：Ctrl+C 发送中断（\\x03）。"""

    interrupt_requested = pyqtSignal()
    raw_key = pyqtSignal(str)
    raw_mode = False

    def keyPressEvent(self, event):
        if self.raw_mode:
            data = key_event_to_bytes(event)
            if data:
                self.raw_key.emit(data)
            event.accept()
            return
        if event.key() == Qt.Key_C and event.modifiers() & Qt.ControlModifier:
            self.interrupt_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


def render_needed(screen, last_revision):
    """渲染节流：内容（revision）未变则跳过重绘。"""
    rev = getattr(screen, "revision", 0)
    return rev != last_revision


class PtyTerminalTab(QWidget):
    """交互式 PTY 终端标签（持续 shell 会话）。"""

    kind = "pty"
    # P7：主视图内可滚动查看的历史行上限（性能与可用性折中）
    HISTORY_RENDER_MAX = 400

    def __init__(self, cwd, parent=None):
        super().__init__(parent)
        shell = ["cmd.exe"] if sys.platform == "win32" else ["/bin/sh"]
        workdir = cwd if cwd and os.path.isdir(cwd) else None
        self._session = PtySession(argv=shell, cwd=workdir)
        self._screen = TerminalScreen(30, 100)
        self._last_revision = -1
        self._cwd = cwd
        self._proc = None
        self.interrupts = 0

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(4)

        row = QHBoxLayout()
        mode = QLabel("交互 PTY")
        mode.setStyleSheet("color: #7ec850; font-size: 11px;")
        row.addWidget(mode)
        self.cwd_label = QLabel(cwd or "")
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
        self.history_btn = QPushButton("历史")
        self.history_btn.setFixedWidth(56)
        self.history_btn.setToolTip("查看终端历史（独立 scrollback 视图）")
        self.history_btn.clicked.connect(self.show_history)
        row.addWidget(self.history_btn)
        self.raw_btn = QPushButton("raw")
        self.raw_btn.setFixedWidth(56)
        self.raw_btn.setCheckable(True)
        self.raw_btn.setToolTip("原始输入：按键直接发送到 PTY（alt-screen 等交互程序）")
        self.raw_btn.toggled.connect(self.set_raw_mode)
        row.addWidget(self.raw_btn)
        vbox.addLayout(row)

        self.output = TerminalOutput()
        self.output.setReadOnly(True)
        self.output._screen = self._screen
        self.output.setFont(QFont("Consolas", 10))
        self.output.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; border: 1px solid #3c3c3c; }"
        )
        vbox.addWidget(self.output, 1)

        inrow = QHBoxLayout()
        prompt = QLabel("$")
        prompt.setStyleSheet("color: #7ec850; font-weight: bold;")
        inrow.addWidget(prompt)
        self.input = PtyLineEdit()
        self.input.setPlaceholderText("交互模式：输入命令回车，Ctrl+C 中断")
        self.input.returnPressed.connect(self.run_command)
        self.input.interrupt_requested.connect(self.send_interrupt)
        self.input.raw_key.connect(self.send_raw)
        self.output.mouse_input.connect(self.send_raw)
        inrow.addWidget(self.input, 1)
        run_btn = QPushButton("发送")
        run_btn.setFixedWidth(60)
        run_btn.clicked.connect(self.run_command)
        inrow.addWidget(run_btn)
        vbox.addLayout(inrow)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._drain)
        self._timer.start(50)

    def _append_ansi(self, text):
        if not text:
            return
        self.output.moveCursor(self.output.textCursor().End)
        self.output.insertHtml(ansi_to_html(text))
        self.output.ensureCursorVisible()

    def show_history(self):
        dlg = TerminalHistoryDialog(self._screen, self)
        dlg.exec_()

    def _render_screen(self):
        """P6：内容未变时跳过重绘；保持用户滚动位置。"""
        if not render_needed(self._screen, getattr(self, "_last_revision", -1)):
            return
        self._last_revision = getattr(self._screen, "revision", 0)
        try:
            bar = self.output.verticalScrollBar()
            at_bottom = bar.value() >= bar.maximum() - 2
            old_value = bar.value()
            self.output.setHtml(self._screen.render_html(
                include_scrollback=True, max_scrollback=self.HISTORY_RENDER_MAX))
            if at_bottom:
                self.output.moveCursor(self.output.textCursor().End)
                self.output.ensureCursorVisible()
            else:
                bar.setValue(min(old_value, bar.maximum()))
        except Exception:
            pass

    def _drain(self):
        try:
            data = self._session.read_available()
        except Exception:
            return
        if data:
            self._screen.feed(data)
            self._render_screen()

    def run_command(self):
        text = self.input.text()
        self.input.add_history(text)
        self.input.clear()
        self._session.write(text + "\r\n")

    def set_raw_mode(self, enabled: bool):
        """P1：raw 输入开关；开启后按键直通 PTY（不等待回车）。"""
        self.raw_mode = bool(enabled)
        self.input.raw_mode = self.raw_mode
        self.input.setPlaceholderText(
            "RAW 模式：按键直通（Esc 退出程序 / Ctrl+C 中断）"
            if self.raw_mode
            else "交互模式：输入命令回车，Ctrl+C 中断"
        )
        self.input.setFocus()

    def send_raw(self, data: str):
        """发送原始字节到 PTY（测试可直接调用）。"""
        try:
            self._session.write(data)
            return True
        except Exception:
            return False

    def send_interrupt(self):
        self.interrupts += 1
        try:
            self._session.write("\x03")
        except Exception:
            pass

    def clear_output(self):
        try:
            self._screen.clear()
        except Exception:
            pass
        self.output.clear()

    def copy_output(self):
        try:
            from PyQt5.QtWidgets import QApplication

            QApplication.clipboard().setText(self.output.toPlainText())
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            fm = self.output.fontMetrics()
            rows = max(5, self.output.height() // max(1, fm.height()))
            cols = max(20, self.output.width() // max(1, fm.horizontalAdvance("M")))
            self._screen.resize(rows, cols)
            self._session._proc.setwinsize(rows, cols)
        except Exception:
            pass

    def terminate(self):
        try:
            self._timer.stop()
        except Exception:
            pass
        try:
            self._session.close()
        except Exception:
            pass


class TerminalPanel(QDockWidget):
    def __init__(self, main_window=None):
        super().__init__("终端", main_window)
        self.main_window = main_window
        self.setObjectName("TerminalDock")
        self._default = self._default_cwd()
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        corner = QWidget()
        corner_row = QHBoxLayout(corner)
        corner_row.setContentsMargins(0, 0, 4, 0)
        corner_row.setSpacing(2)
        add_btn = QToolButton()
        add_btn.setText("+")
        add_btn.setToolTip("新建单命令终端标签")
        add_btn.clicked.connect(lambda: self.add_tab())
        corner_row.addWidget(add_btn)
        pty_btn = QToolButton()
        pty_btn.setText("PTY")
        pty_btn.setToolTip("新建交互式 PTY 标签（不可用时回退单命令）")
        pty_btn.clicked.connect(lambda: self.add_tab(pty=True))
        corner_row.addWidget(pty_btn)
        self.tabs.setCornerWidget(corner, Qt.TopRightCorner)
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
    def add_tab(self, cwd=None, pty=False):
        """新增标签；pty=True 时创建交互式 PTY（不可用自动回退）。"""
        tab = None
        label = None
        if pty:
            if HAS_PTY and PtySession is not None:
                try:
                    tab = PtyTerminalTab(cwd or self._default)
                    label = "PTY %d" % (self.tabs.count() + 1)
                except Exception as e:
                    print("[terminal] PTY 启动失败，回退单命令模式:", e)
            if tab is None:
                tab = TerminalTab(cwd or self._default)
                tab.setToolTip("PTY 不可用，已回退单命令模式")
                label = "终端 %d（回退）" % (self.tabs.count() + 1)
        else:
            tab = TerminalTab(cwd or self._default)
            label = "终端 %d" % (self.tabs.count() + 1)
        idx = self.tabs.addTab(tab, label)
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
