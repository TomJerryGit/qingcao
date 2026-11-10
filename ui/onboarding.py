# -*- coding: utf-8 -*-
"""首启向导（v2.24.x UX）：语言 / 主题 / 插件市场 3 步。"""

from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


PREF_KEY = "onboarding_done"


def _prefs():
    from app.preferences import Preferences

    return Preferences()


def should_show_onboarding():
    try:
        return not bool(_prefs().get(PREF_KEY, False))
    except Exception:
        return False


def mark_onboarding_done():
    try:
        _prefs().set(PREF_KEY, True)
    except Exception:
        pass


class OnboardingDialog(QDialog):
    STEPS = (
        ("👋 欢迎使用青草编辑器", "可在 首选项 → 语言 中切换 中文 / English / 日本語 / 한국어。"),
        ("🎨 选择你的主题", "默认已适配深色；可在 视图 → 主题 或 首选项 中更换。"),
        ("🧩 探索插件市场", "工具 → 插件市场：安装扩展、查看评分与更新。"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("欢迎使用青草编辑器")
        self.resize(520, 320)
        self._index = 0
        self._stack = QStackedWidget(self)
        self.setObjectName("OnboardingDialog")
        for title, desc in self.STEPS:
            page = QWidget()
            lay = QVBoxLayout(page)
            t = QLabel(title)
            t.setStyleSheet("font-size: 18px; font-weight: bold;")
            d = QLabel(desc)
            d.setWordWrap(True)
            lay.addWidget(t)
            lay.addWidget(d)
            lay.addStretch(1)
            self._stack.addWidget(page)
        self._prev = QPushButton("上一步", self)
        self._next = QPushButton("下一步", self)
        self._prev.clicked.connect(self._on_prev)
        self._next.clicked.connect(self._on_next)
        self._prev.setEnabled(False)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self._prev)
        row.addWidget(self._next)
        root = QVBoxLayout(self)
        root.addWidget(self._stack, 1)
        root.addLayout(row)

    def current_step(self):
        return self._index

    def _on_prev(self):
        if self._index > 0:
            self._index -= 1
            self._refresh()

    def _on_next(self):
        if self._index < len(self.STEPS) - 1:
            self._index += 1
            self._refresh()
        else:
            mark_onboarding_done()
            self.accept()

    def _refresh(self):
        self._stack.setCurrentIndex(self._index)
        self._prev.setEnabled(self._index > 0)
        self._next.setText("开始使用" if self._index == len(self.STEPS) - 1 else "下一步")


def maybe_show_onboarding(parent=None):
    if not should_show_onboarding():
        return False
    dlg = OnboardingDialog(parent)
    dlg.exec_()
    mark_onboarding_done()
    return True
