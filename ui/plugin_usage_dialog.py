# -*- coding: utf-8 -*-
"""插件使用统计 UI（本地、隐私安全）。"""

import time

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class PluginUsageDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("插件使用统计（本地）")
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setAccessibleName("插件使用统计表")
        self.table.setToolTip("本地插件使用次数（不上传）")
        self.table.setHorizontalHeaderLabels(["插件", "激活", "停用", "最近使用"])
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 2)
        self.trend_table = QTableWidget(0, 3)
        self.trend_table.setHorizontalHeaderLabels(["日期", "激活", "停用"])
        self.trend_table.verticalHeader().setVisible(False)
        self.trend_table.setAccessibleName("使用趋势")
        self.trend_table.setToolTip("最近 14 天本地使用趋势")
        layout.addWidget(self.trend_table, 1)
        buttons = QDialogButtonBox()
        reset = QPushButton("清空统计")
        reset.setToolTip("清空本地插件使用统计")
        reset.setAccessibleName("清空插件使用统计")
        reset.clicked.connect(self._reset)
        buttons.addButton(reset, QDialogButtonBox.ActionRole)
        close = QPushButton("关闭")
        close.setToolTip("关闭统计窗口")
        close.setAccessibleName("关闭使用统计")
        close.clicked.connect(self.accept)
        buttons.addButton(close, QDialogButtonBox.AcceptRole)
        layout.addWidget(buttons)
        self.refresh()

    def _rows(self):
        from core.plugin_usage import snapshot

        rows = sorted(snapshot().items(), key=lambda kv: -int(kv[1].get("activations") or 0))
        out = []
        for name, rec in rows:
            last = rec.get("last_activate") or 0
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(last)) if last else "-"
            out.append(
                (name, int(rec.get("activations") or 0), int(rec.get("deactivations") or 0), when)
            )
        return out

    def refresh(self):
        rows = self._rows()
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        from core.plugin_usage import trend

        rows = trend(14)
        self.trend_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, key in enumerate(("date", "activate", "deactivate")):
                self.trend_table.setItem(r, c, QTableWidgetItem(str(row[key])))
        self.trend_table.resizeColumnsToContents()

    def _reset(self):
        if QMessageBox.question(self, "清空统计", "确定清空本地插件使用统计？") != QMessageBox.Yes:
            return
        from core.plugin_usage import reset

        reset()
        self.refresh()
