# -*- coding: utf-8 -*-
"""R1.2：按插件 settings schema 动态生成配置对话框。"""

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)


def normalize_schema(schema):
    """支持 list[dict] 或 dict{key:spec} 两种 schema。"""
    items = []
    if isinstance(schema, dict):
        for key, spec in schema.items():
            if isinstance(spec, dict):
                item = dict(spec)
                item.setdefault("key", key)
                items.append(item)
    elif isinstance(schema, (list, tuple)):
        for spec in schema:
            if isinstance(spec, dict) and spec.get("key"):
                items.append(dict(spec))
    return items


class SchemaSettingsDialog(QDialog):
    """schema → QFormLayout；保存到 QSettings("QingCao","PluginData")。"""

    def __init__(self, plugin_name, schema, settings=None, parent=None):
        super().__init__(parent)
        self.plugin_name = plugin_name
        self.settings = settings or QSettings("QingCao", "PluginData")
        self.setWindowTitle("插件设置 - %s" % plugin_name)
        self.widgets = {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        for spec in normalize_schema(schema):
            key = str(spec.get("key"))
            label = str(spec.get("label") or key)
            typ = str(spec.get("type") or "str")
            default = spec.get("default")
            value = self.settings.value("plugins/%s/%s" % (plugin_name, key), default)
            if typ == "bool":
                w = QCheckBox()
                w.setChecked(bool(value))
            elif typ == "int":
                w = QSpinBox()
                w.setRange(-1000000, 1000000)
                w.setValue(int(value or 0))
            elif typ == "float":
                w = QDoubleSpinBox()
                w.setRange(-1000000.0, 1000000.0)
                w.setValue(float(value or 0.0))
            elif typ == "choice":
                w = QComboBox()
                for text, val in spec.get("choices") or []:
                    w.addItem(str(text), val)
                idx = w.findData(value)
                if idx >= 0:
                    w.setCurrentIndex(idx)
            else:
                w = QLineEdit(str(value if value is not None else ""))
            form.addRow(label + ":", w)
            self.widgets[key] = (w, typ)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        out = {}
        for key, (w, typ) in self.widgets.items():
            if typ == "bool":
                out[key] = w.isChecked()
            elif typ == "int":
                out[key] = w.value()
            elif typ == "float":
                out[key] = w.value()
            elif typ == "choice":
                out[key] = w.currentData()
            else:
                out[key] = w.text()
        return out

    def accept(self):
        for key, value in self.values().items():
            self.settings.setValue("plugins/%s/%s" % (self.plugin_name, key), value)
        self.settings.sync()
        super().accept()
