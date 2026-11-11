# -*- coding: utf-8 -*-
"""动态快捷键参考对话框（v2.25 UX）：从真实菜单收集，可搜索。"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)


def collect_shortcut_rows(window):
    """递归遍历菜单栏，返回 [(菜单路径, 动作文本, 快捷键)]。"""
    rows = []
    try:
        menubar = window.menuBar()
    except Exception:
        return rows
    seen = set()

    def walk(menu, path):
        for action in menu.actions():
            if action.isSeparator():
                continue
            text = (action.text() or "").replace("&", "").strip()
            sub = action.menu()
            if sub is not None:
                walk(sub, (path + " → " if path else "") + text)
                continue
            if id(action) in seen:
                continue
            seen.add(id(action))
            shortcut = action.shortcut().toString()
            if text:
                rows.append((path, text, shortcut))

    for action in menubar.actions():
        menu = action.menu()
        if menu is not None:
            title = (action.text() or "").replace("&", "").strip()
            walk(menu, title)
    return rows


class ShortcutListDialog(QDialog):
    """可搜索的快捷键一览（含未绑定动作）。"""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.setWindowTitle("快捷键参考")
        self.resize(760, 620)
        self._rows = collect_shortcut_rows(window)
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索命令或快捷键…")
        self.search.textChanged.connect(self._apply_filter)
        row.addWidget(self.search, 1)
        copy_btn = QPushButton("复制全部")
        copy_btn.clicked.connect(self._copy_all)
        row.addWidget(copy_btn)
        layout.addLayout(row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["命令", "快捷键", "菜单"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 320)
        self.tree.setColumnWidth(1, 160)
        layout.addWidget(self.tree, 1)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #888;")
        layout.addWidget(self.status)
        self._populate(self._rows)

    def _populate(self, rows):
        self.tree.clear()
        for path, text, shortcut in rows:
            item = QTreeWidgetItem([text, shortcut, path])
            self.tree.addTopLevelItem(item)
        bound = sum(1 for _p, _t, s in rows if s)
        self.status.setText("共 %d 项，已绑定快捷键 %d 项" % (len(rows), bound))

    def _apply_filter(self, text):
        text = (text or "").strip().lower()
        rows = [r for r in self._rows if not text or text in " ".join(r).lower()]
        self._populate(rows)

    def _copy_all(self):
        try:
            from PyQt5.QtWidgets import QApplication

            lines = ["%s\t%s\t%s" % (p, t, s) for p, t, s in self._rows]
            QApplication.clipboard().setText("\n".join(lines))
        except Exception:
            pass
