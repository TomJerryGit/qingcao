# -*- coding: utf-8 -*-
"""可点击的状态栏组件：编码、行尾符、Git 分支"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QLabel, QMenu


# 常用编码
ENCODINGS = [
    ("UTF-8", "utf-8"),
    ("UTF-8 with BOM", "utf-8-sig"),
    ("GBK", "gbk"),
    ("GB2312", "gb2312"),
    ("GB18030", "gb18030"),
    ("Big5", "big5"),
    ("Shift-JIS", "shift_jis"),
    ("EUC-KR", "euc-kr"),
    ("ISO-8859-1", "iso-8859-1"),
    ("Windows-1252", "windows-1252"),
    ("UTF-16 LE", "utf-16-le"),
    ("UTF-16 BE", "utf-16-be"),
    ("ASCII", "ascii"),
]

# 行尾符
LINE_ENDINGS = [
    ("LF (Unix)", "\n"),
    ("CRLF (Windows)", "\r\n"),
    ("CR (Mac Classic)", "\r"),
]


class ClickableLabel(QLabel):
    """可点击的 QLabel"""
    clicked = pyqtSignal()

    def __init__(self, text="", parent=None, tooltip=""):
        super().__init__(text, parent)
        if tooltip:
            self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QLabel { padding: 2px 6px; border-radius: 3px; color: white; }"
            "QLabel:hover { background-color: rgba(255,255,255,40); }"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class EncodingLabel(ClickableLabel):
    """编码显示标签（点击弹菜单切换）"""

    encoding_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("UTF-8", parent, "点击切换编码")
        self._current = "utf-8"

    def set_encoding(self, enc):
        """更新显示"""
        self._current = enc
        display = enc.upper()
        for name, code in ENCODINGS:
            if code == enc:
                display = name
                break
        self.setText(display)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._show_menu(event.globalPos())
        super().mousePressEvent(event)

    def _show_menu(self, pos):
        menu = QMenu(self)
        for name, code in ENCODINGS:
            action = menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(code == self._current)
            action.triggered.connect(
                lambda checked=False, c=code: self._on_select(c)
            )
        menu.exec_(pos)

    def _on_select(self, code):
        if code != self._current:
            self.encoding_changed.emit(code)
            # 不立即更新显示，等主窗口确认后再更新


class EolLabel(ClickableLabel):
    """行尾符标签（点击弹菜单切换）"""

    eol_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("LF", parent, "点击切换行尾符")
        self._current = "\n"

    def set_eol(self, eol):
        """更新显示"""
        self._current = eol
        display = {"\n": "LF", "\r\n": "CRLF", "\r": "CR"}.get(eol, "LF")
        self.setText(display)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._show_menu(event.globalPos())
        super().mousePressEvent(event)

    def _show_menu(self, pos):
        menu = QMenu(self)
        for name, code in LINE_ENDINGS:
            action = menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(code == self._current)
            action.triggered.connect(
                lambda checked=False, c=code: self._on_select(c)
            )
        menu.exec_(pos)

    def _on_select(self, code):
        if code != self._current:
            self.eol_changed.emit(code)


class GitBranchLabel(ClickableLabel):
    """Git 分支标签（点击打开 Git 面板）"""

    git_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("", parent, "点击打开 Git 面板")

    def mousePressEvent(self, event):
        # P1-B7: 阻止 super() 触发 clicked
        # 基类 ClickableLabel.mousePressEvent 会 emit self.clicked，
        # 如果这里也调 super()，一次点击会触发 clicked + git_clicked
        # 两个信号。
        if event.button() == Qt.LeftButton and self.text():
            self.git_clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)