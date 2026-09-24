#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""调试器面板"""
from PyQt5.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QTreeWidget, QTreeWidgetItem, QPushButton, QLabel,
    QTextEdit
)
from PyQt5.QtCore import Qt, pyqtSignal


class DebugPanel(QDockWidget):
    """调试器面板"""

    continue_requested = pyqtSignal()
    step_over_requested = pyqtSignal()
    step_into_requested = pyqtSignal()
    stop_requested = pyqtSignal()

    def __init__(self, main_window=None, parent=None):
        super().__init__("调试", parent or main_window)

        self.main_window = main_window

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 控制按钮
        btn_layout = QHBoxLayout()
        for text, signal in [
            ("▶ 继续", self.continue_requested),
            ("⏭ 跳过", self.step_over_requested),
            ("⏬ 进入", self.step_into_requested),
            ("⏹ 停止", self.stop_requested),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(signal.emit)
            btn_layout.addWidget(btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 变量视图
        layout.addWidget(QLabel("变量:"))
        self.var_tree = QTreeWidget()
        self.var_tree.setHeaderLabels(["名称", "值"])
        layout.addWidget(self.var_tree, 1)

        # 调用堆栈
        layout.addWidget(QLabel("调用堆栈:"))
        self.stack_tree = QTreeWidget()
        self.stack_tree.setHeaderLabels(["函数", "文件:行"])
        layout.addWidget(self.stack_tree, 1)

        # 输出
        layout.addWidget(QLabel("输出:"))
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumHeight(100)
        layout.addWidget(self.output)

        self.setWidget(container)

    def update_variables(self, variables):
        """更新变量"""
        self.var_tree.clear()
        for name, value in (variables or {}).items():
            item = QTreeWidgetItem(self.var_tree, [str(name), str(value)[:200]])

    def update_stack(self, stack):
        """更新调用堆栈"""
        self.stack_tree.clear()
        for frame in (stack or []):
            func = frame.get('function', '?')
            file = frame.get('file', '?')
            line = frame.get('line', 0)
            QTreeWidgetItem(self.stack_tree, [func, f"{file}:{line}"])

    def append_output(self, text):
        """追加输出"""
        self.output.append(text)