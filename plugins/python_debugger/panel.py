# -*- coding: utf-8 -*-
"""调试面板（D3）：状态 / 调用栈 / 局部变量 / 程序输出 / 控制按钮。

本模块由 `plugins/python_debugger/__init__.py` 通过**文件路径**加载
（插件没有包上下文，不能用相对导入）。
"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)


class DebuggerPanel(QDialog):
    """非模态调试面板。

    刻意做成 `QDialog` 而不是 `QDockWidget`：插件被停用/重载时
    一起销毁，不留悬挂的 dock；由插件负责 show/hide。
    """

    def __init__(self, session=None, parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("调试 — Python")
        self.setObjectName("PythonDebuggerPanel")
        self.setModal(False)
        self.resize(560, 420)
        self._build_ui()

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.status_label = QLabel("未启动")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["名称", "值 / 位置"])
        self.tree.setColumnWidth(0, 200)
        layout.addWidget(self.tree, 3)

        output_label = QLabel("程序输出")
        layout.addWidget(output_label)
        self.output_view = QPlainTextEdit()
        self.output_view.setReadOnly(True)
        self.output_view.setObjectName("DebuggerOutput")
        layout.addWidget(self.output_view, 2)

        buttons = QHBoxLayout()
        self.continue_btn = self._add_button(buttons, "继续", "continue_")
        self.step_over_btn = self._add_button(buttons, "跳过", "step_over")
        self.step_into_btn = self._add_button(buttons, "进入", "step_into")
        self.step_out_btn = self._add_button(buttons, "跳出", "step_out")
        self.locals_btn = self._add_button(buttons, "变量", "request_locals")
        self.stack_btn = self._add_button(buttons, "栈", "request_stack")
        self.stop_btn = self._add_button(buttons, "终止", "stop")
        buttons.addStretch(1)
        layout.addLayout(buttons)

    def _add_button(self, layout, text, session_method):
        button = QPushButton(text)
        button.clicked.connect(
            lambda _checked=False, name=session_method: self._invoke(name)
        )
        layout.addWidget(button)
        return button

    def _invoke(self, session_method):
        """点击按钮 → 调用会话方法（没有会话时静默忽略）。"""
        session = self.session
        if session is None:
            return None
        method = getattr(session, session_method, None)
        if not callable(method):
            return None
        try:
            return method()
        except Exception as exc:  # pragma: no cover - UI 兜底
            self.set_status(f"操作失败：{exc}")
            return None

    # --------------------------------------------------------
    # 状态展示
    # --------------------------------------------------------
    def set_status(self, text):
        try:
            self.status_label.setText(str(text))
        except Exception:
            pass

    def clear(self):
        try:
            self.tree.clear()
        except Exception:
            pass

    def append_output(self, text):
        if not text:
            return
        try:
            cursor = self.output_view.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.output_view.setTextCursor(cursor)
            self.output_view.insertPlainText(str(text))
        except Exception:
            try:
                self.output_view.appendPlainText(str(text).rstrip("\n"))
            except Exception:
                pass

    def show_paused(self, payload):
        """显示"停在某处"：栈帧 + 当前帧局部变量。"""
        payload = payload or {}
        filepath = payload.get("file") or ""
        line = payload.get("line") or 1
        reason = payload.get("reason") or "break"
        reason_text = {
            "breakpoint": "命中断点",
            "step": "单步",
            "pause": "暂停",
        }.get(reason, reason)
        self.set_status(f"{reason_text}：{filepath}:{line}")
        self.show_stack(payload.get("stack") or [])
        self.show_locals(payload.get("locals") or {})

    def show_stack(self, frames):
        """显示调用栈（内层在前）。"""
        try:
            self.tree.clear()
        except Exception:
            return
        for index, frame in enumerate(frames or []):
            name = frame.get("name") or "?"
            filepath = frame.get("file") or "?"
            line = frame.get("line") or 0
            item = QTreeWidgetItem(self.tree)
            item.setText(0, f"#{index} {name}")
            item.setText(1, f"{filepath}:{line}")
            item.setData(0, Qt.UserRole, "frame")
        for column in (0, 1):
            try:
                self.tree.resizeColumnToContents(column)
            except Exception:
                pass

    def show_locals(self, values, prefix="局部"):
        """在调用栈列表顶部插入一个"局部变量"节点。"""
        try:
            parent = QTreeWidgetItem()
            parent.setText(0, f"{prefix}变量")
            parent.setData(0, Qt.UserRole, "locals")
            for name in sorted((values or {}).keys()):
                child = QTreeWidgetItem(parent)
                child.setText(0, str(name))
                child.setText(1, str(values.get(name)))
            parent.setExpanded(True)
            self.tree.insertTopLevelItem(0, parent)
        except Exception:
            pass

    def show_result(self, kind, value):
        """处理 stack / locals / eval 命令的异步结果。"""
        if kind == "stack":
            self.show_stack(value if isinstance(value, list) else [])
        elif kind == "locals":
            self.show_locals(value if isinstance(value, dict) else {})
        elif kind == "eval":
            self.append_output(f"{value}\n")
        else:
            self.set_status(f"{kind}: {value}")

    def __repr__(self):
        return f"<DebuggerPanel paused={bool(self.tree.topLevelItemCount())}>"
