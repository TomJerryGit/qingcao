# -*- coding: utf-8 -*-
"""完整 UI 隔离阶段 C：远程控件树宿主渲染器。"""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class RemoteUIRenderer(QWidget):
    control_event = pyqtSignal(str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._widgets = {}
        self._signature = None

    def update_tree(self, tree):
        controls = (tree or {}).get("controls") or []
        signature = tuple(
            (
                c.get("id"),
                c.get("kind"),
                c.get("text"),
                c.get("value"),
                bool(c.get("enabled", True)),
                bool(c.get("visible", True)),
            )
            for c in controls
        )
        if signature == self._signature:
            return
        self._signature = signature
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._widgets = {}
        for c in controls:
            cid = str(c.get("id") or "")[:64]
            kind = c.get("kind")
            text = str(c.get("text") or "")
            value = str(c.get("value") or "")
            if not cid:
                continue
            w = None
            if kind == "label":
                w = QLabel(text)
            elif kind == "button":
                w = QPushButton(text or cid)
                action = str(c.get("action") or "")
                w.setProperty("qc_action", action)
                w.clicked.connect(
                    lambda _=False, i=cid, a=action: self.control_event.emit(i, "click", a)
                )
            elif kind == "line_edit":
                w = QLineEdit(value)
                w.textChanged.connect(
                    lambda v, i=cid: self.control_event.emit(i, "text_changed", v)
                )
            elif kind == "check_box":
                w = QCheckBox(text)
                w.setChecked(value in ("1", "true", "True"))
                w.toggled.connect(
                    lambda on, i=cid: self.control_event.emit(
                        i, "checked_changed", "1" if on else "0"
                    )
                )
            elif kind == "text_view":
                w = QTextEdit()
                w.setReadOnly(True)
                w.setPlainText(value)
            else:
                continue
            w.setAccessibleName(cid)
            w.setVisible(bool(c.get("visible", True)))
            w.setEnabled(bool(c.get("enabled", True)))
            self._widgets[cid] = w
            self._layout.addWidget(w)

    def widget_for(self, control_id):
        return self._widgets.get(str(control_id))
