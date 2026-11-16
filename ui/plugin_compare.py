# -*- coding: utf-8 -*-
"""P4：插件对比对话框。"""

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


FIELDS = (
    ("版本", "version"),
    ("作者", "author"),
    ("类型", "type"),
    ("权限", "permissions"),
    ("评分", "rating"),
    ("安全", "security"),
    ("状态", "status"),
    ("描述", "description"),
)


def _value(info, attr):
    value = getattr(info, attr, "")
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(x) for x in value)
    return str(value or "-")


def compare_rows(left, right):
    rows = []
    for label, attr in FIELDS:
        rows.append((label, _value(left, attr), _value(right, attr)))
    return rows


class PluginCompareDialog(QDialog):
    def __init__(self, plugins, parent=None):
        super().__init__(parent)
        self.plugins = list(plugins or [])
        self.setWindowTitle("插件对比")
        self.resize(760, 420)
        layout = QVBoxLayout(self)
        pick = QHBoxLayout()
        self.left_combo = QComboBox()
        self.right_combo = QComboBox()
        for p in self.plugins:
            title = getattr(p, "display_title", None) or getattr(p, "name", "?")
            self.left_combo.addItem(str(title), getattr(p, "name", ""))
            self.right_combo.addItem(str(title), getattr(p, "name", ""))
        pick.addWidget(QLabel("插件 A:"))
        pick.addWidget(self.left_combo, 1)
        pick.addWidget(QLabel("插件 B:"))
        pick.addWidget(self.right_combo, 1)
        layout.addLayout(pick)
        self.table = QTableWidget(len(FIELDS), 3)
        self.table.setHorizontalHeaderLabels(["字段", "插件 A", "插件 B"])
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.left_combo.currentIndexChanged.connect(self._refresh_table)
        self.right_combo.currentIndexChanged.connect(self._refresh_table)
        if len(self.plugins) > 1:
            self.right_combo.setCurrentIndex(1)
        self._refresh_table()

    def _by_name(self, name):
        for p in self.plugins:
            if getattr(p, "name", "") == name:
                return p
        return None

    def _refresh_table(self):
        left = self._by_name(self.left_combo.currentData())
        right = self._by_name(self.right_combo.currentData())
        rows = compare_rows(left, right)
        for r, (label, a, b) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(label))
            self.table.setItem(r, 1, QTableWidgetItem(a))
            self.table.setItem(r, 2, QTableWidgetItem(b))
        self.table.resizeColumnsToContents()
