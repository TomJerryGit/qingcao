# -*- coding: utf-8 -*-
"""调试器宿主面板（B3-D5）：展示 DebugService 的栈/变量事件。"""

from PyQt5.QtWidgets import (
    QDockWidget,
    QLabel,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class DebugHostPanel(QDockWidget):
    def __init__(self, service, parent=None):
        super().__init__("调试器（宿主）", parent)
        self.service = service
        self.setObjectName("DebugHostPanel")
        body = QWidget(self)
        layout = QVBoxLayout(body)
        self.status = QLabel("未启动")
        layout.addWidget(self.status)
        self.tabs = QTabWidget()
        self.stack_tree = QTreeWidget()
        self.stack_tree.setAccessibleName("调用栈")
        self.stack_tree.setToolTip("调试调用栈")
        self.stack_tree.setHeaderLabels(["帧", "位置"])
        self.locals_tree = QTreeWidget()
        self.locals_tree.setAccessibleName("局部变量")
        self.locals_tree.setToolTip("调试变量")
        self.locals_tree.setHeaderLabels(["名称", "值"])
        self.tabs.addTab(self.stack_tree, "调用栈")
        self.tabs.addTab(self.locals_tree, "变量")
        layout.addWidget(self.tabs)
        self.setWidget(body)
        try:
            service.event.connect(self.on_event)
        except Exception:
            pass

    def on_event(self, payload):
        if not isinstance(payload, dict):
            return
        name = payload.get("event")
        data = payload.get("data") or {}
        if name == "debug.break":
            self.status.setText(
                "暂停：%s:%s" % (data.get("file", "?"), int(data.get("line", 0)) + 1)
            )
        elif name == "debug.stack":
            self._fill_stack(data.get("frames") or [])
        elif name == "debug.locals":
            self._fill_locals(data.get("values") or {})
        elif name == "debug.exit":
            self.status.setText("已结束（exit=%s）" % data.get("code"))
        elif name == "debug.error":
            self.status.setText("错误：%s" % data.get("message", ""))

    def _fill_stack(self, frames):
        self.stack_tree.clear()
        for idx, frame in enumerate(frames or []):
            item = QTreeWidgetItem(self.stack_tree)
            item.setText(0, "#%d %s" % (idx, frame.get("name", "?")))
            item.setText(1, "%s:%s" % (frame.get("file", "?"), frame.get("line", 0)))

    def _fill_locals(self, values):
        self.locals_tree.clear()
        for key in sorted((values or {}).keys()):
            item = QTreeWidgetItem(self.locals_tree)
            item.setText(0, str(key))
            item.setText(1, str(values.get(key)))
