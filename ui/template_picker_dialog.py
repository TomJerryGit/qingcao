# -*- coding: utf-8 -*-
"""从代码模板新建文件（接线 `core/code_templates.py`）

## 为什么需要这个 UI

`core/code_templates.py`（240 行）提供了 8 个真实可用的模板
（Python 类/函数/测试/主程序、JS 函数/类、`.gitignore`、`README`），
但此前**零引用** —— 用户只能每次手敲 class 骨架。

本对话框把「选模板 → 填占位符 → 生成到新标签」串起来。

## 设计要点

* 占位符输入框**按模板动态生成**（取自 `get_template_placeholders()`），
  不给用户一个猜 `{init_body}` 该填什么的空白文本框；
* 右侧实时预览；
* 占位符可留空（`format_template` 会把缺失项填空串，
  保证生成结果**始终是合法文本**，而不是带 `{xxx}` 的坏代码）；
* 生成的标签会被标记为**未修改的新文档**，用户可继续编辑再保存。
"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.code_templates import (
    format_template,
    get_template,
    get_template_placeholders,
    list_templates,
)


# 模板中文显示名（`core.code_templates` 里的 "name" 字段已经是中文）
_DEFAULT_EXT = {
    "py_class": ".py",
    "py_function": ".py",
    "py_test": ".py",
    "py_main": ".py",
    "js_function": ".js",
    "js_class": ".js",
    "gitignore": ".gitignore",
    "readme": ".md",
}


class TemplatePickerDialog(QDialog):
    """选择代码模板 + 填占位符 + 预览 → 返回要插入的文本"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("从模板新建")
        self.resize(860, 560)

        # 结果（accept 后由调用方读取）
        self.generated_text = ""
        self.suggested_filename = ""

        self._inputs = {}          # 占位符 -> QLineEdit
        self._build_ui()
        self._reload_template()

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("模板:"))
        self.template_combo = QComboBox()
        for key in list_templates():
            info = get_template(key)
            self.template_combo.addItem(info.get("name") or key, key)
        self.template_combo.currentIndexChanged.connect(
            self._reload_template)
        top.addWidget(self.template_combo, 1)

        top.addWidget(QLabel("文件名:"))
        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("留空则用「未命名」")
        top.addWidget(self.filename_edit, 1)
        root.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)

        # 左：占位符输入
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.params_group = QGroupBox("填充内容")
        self.params_form = QFormLayout(self.params_group)
        left_layout.addWidget(self.params_group)
        left_layout.addStretch()
        tip = QLabel(
            "提示：留空的占位符会被替换为空字符串，\n"
            "生成结果仍是合法文本，可继续编辑。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #888; font-size: 11px;")
        left_layout.addWidget(tip)
        splitter.addWidget(left)

        # 右：预览
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("预览:"))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        self.preview.setFont(mono)
        right_layout.addWidget(self.preview, 1)
        splitter.addWidget(right)

        splitter.setSizes([320, 540])
        root.addWidget(splitter, 1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.buttons.button(QDialogButtonBox.Ok).setText("生成")
        self.buttons.button(QDialogButtonBox.Cancel).setText("取消")
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    def _reload_template(self):
        """切换模板：重建占位符输入框 + 刷新预览"""
        key = self.template_combo.currentData()
        if not key:
            return

        # 清空旧输入框
        while self.params_form.rowCount():
            self.params_form.removeRow(0)
        self._inputs.clear()

        for ph in get_template_placeholders(key):
            edit = QLineEdit()
            edit.setPlaceholderText(ph)
            edit.textChanged.connect(self._update_preview)
            self.params_form.addRow(ph + ":", edit)
            self._inputs[ph] = edit

        # 建议文件名：模板名 + 扩展名
        if not self.filename_edit.text().strip():
            base = key
            ext = _DEFAULT_EXT.get(key, ".txt")
            if ext == ".gitignore":
                self.filename_edit.setText(".gitignore")
            else:
                self.filename_edit.setText(base + ext)

        self._update_preview()

    def _values(self):
        return {k: w.text() for k, w in self._inputs.items() if w.text()}

    def _update_preview(self):
        key = self.template_combo.currentData()
        self.preview.setPlainText(format_template(key, **self._values()))

    # ---------- 结果 ----------
    def _on_accept(self):
        key = self.template_combo.currentData()
        self.generated_text = format_template(key, **self._values())
        self.suggested_filename = self.filename_edit.text().strip()
        self.accept()


def show_template_picker(parent=None):
    """便捷入口：弹对话框，返回 (text, filename)；取消返回 (None, None)"""
    dlg = TemplatePickerDialog(parent)
    if dlg.exec_() != QDialog.Accepted:
        return None, None
    return dlg.generated_text, dlg.suggested_filename
