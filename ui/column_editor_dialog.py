# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""列编辑对话框（v2.24 拆分：common/Dialog）。"""

from ui.column_editor_dialog_common import *  # noqa: F401,F403


class ColumnEditorDialog(QDialog):
    """列编辑器对话框（可独立构造，不依赖 MainWindow）。

    用法::

        dlg = ColumnEditorDialog(editor)
        if dlg.exec_() == QDialog.Accepted:
            print(dlg.result_data())

    参数:
        editor: QScintilla 控件或 ``EditorProxy``（可为 None，仅预览界面）
        parent: 父控件
    """

    def __init__(self, editor=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("列编辑器")
        self.setMinimumWidth(470)

        self._editor = editor
        self._result: Optional[ColumnEditResult] = None
        try:
            self._target = resolve_target(editor) if editor is not None else None
        except Exception:
            self._target = None

        self._build_ui()
        self._sync_state()

    # --------------------------------------------------------
    # 界面
    # --------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)

        self._scope_label = QLabel(self._scope_text(), self)
        self._scope_label.setWordWrap(True)
        root.addWidget(self._scope_label)

        box = QGroupBox("插入内容", self)
        box_layout = QVBoxLayout(box)

        # --- 文本模式 ---
        text_row = QHBoxLayout()
        self._text_radio = QRadioButton("插入文本:", box)
        self._text_radio.setChecked(True)
        self._text_edit = QLineEdit(box)
        self._text_edit.setPlaceholderText("要在每一行的目标列插入的文本")
        text_row.addWidget(self._text_radio)
        text_row.addWidget(self._text_edit, 1)
        box_layout.addLayout(text_row)

        # --- 数字模式 ---
        num_row = QHBoxLayout()
        self._number_radio = QRadioButton("插入数字:", box)
        num_row.addWidget(self._number_radio)
        num_row.addStretch(1)
        box_layout.addLayout(num_row)

        form = QFormLayout()

        self._start_edit = QLineEdit("1", box)
        self._start_edit.setToolTip("起始值：支持 0x1F / 0o17 / 0b1010 写法")
        form.addRow("起始值:", self._start_edit)

        self._step_spin = QSpinBox(box)
        self._step_spin.setRange(-1000000, 1000000)
        self._step_spin.setValue(1)
        form.addRow("步长:", self._step_spin)

        self._radix_combo = QComboBox(box)
        for value, label in RADIXES:
            self._radix_combo.addItem(label, value)
        form.addRow("进制:", self._radix_combo)

        self._pad_combo = QComboBox(box)
        self._pad_combo.addItem("不填充", PAD_NONE)
        self._pad_combo.addItem("前导零（按最大值宽度）", PAD_ZERO)
        self._pad_combo.addItem("前导空格（右对齐）", PAD_SPACE)
        form.addRow("填充方式:", self._pad_combo)

        self._width_spin = QSpinBox(box)
        self._width_spin.setRange(0, 64)
        self._width_spin.setValue(0)
        self._width_spin.setToolTip("最少位数（0 = 按序列自动）")
        form.addRow("最小位数:", self._width_spin)

        flags = QWidget(box)
        flags_layout = QHBoxLayout(flags)
        flags_layout.setContentsMargins(0, 0, 0, 0)
        self._prefix_check = QCheckBox("加前缀（0x/0o/0b）", flags)
        self._uppercase_check = QCheckBox("十六进制大写", flags)
        self._uppercase_check.setChecked(True)
        flags_layout.addWidget(self._prefix_check)
        flags_layout.addWidget(self._uppercase_check)
        flags_layout.addStretch(1)
        form.addRow("", flags)

        box_layout.addLayout(form)
        root.addWidget(box)

        self._preview = QLabel(self)
        self._preview.setWordWrap(True)
        root.addWidget(self._preview)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        self._ok_button = buttons.button(QDialogButtonBox.Ok)
        self._ok_button.setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        # 实时刷新
        self._text_radio.toggled.connect(self._sync_state)
        self._text_edit.textChanged.connect(self._sync_state)
        self._start_edit.textChanged.connect(self._sync_state)
        self._step_spin.valueChanged.connect(self._sync_state)
        self._radix_combo.currentIndexChanged.connect(self._sync_state)
        self._pad_combo.currentIndexChanged.connect(self._sync_state)
        self._width_spin.valueChanged.connect(self._sync_state)
        self._prefix_check.toggled.connect(self._sync_state)
        self._uppercase_check.toggled.connect(self._sync_state)

    def _scope_text(self) -> str:
        t = self._target
        if t is None or not t.lines:
            return "作用范围：无可编辑目标（请先选中若干行，或建立矩形选区/多光标）"
        names = {
            SOURCE_RECTANGLE: "矩形选区",
            SOURCE_MULTI: "多光标",
            SOURCE_SELECTION: "当前选区",
            SOURCE_CARET: "当前光标",
            SOURCE_EXPLICIT: "显式指定",
        }
        first = t.lines[0] + 1
        last = t.lines[-1] + 1
        span = f"第 {first} 行" if first == last else f"第 {first}–{last} 行"
        text = (
            f"作用范围：{names.get(t.source, t.source)}，{span}"
            f"（共 {len(t.lines)} 行）；目标列：{t.column}"
        )
        if t.warning:
            text += f"\n⚠ {t.warning}"
        return text

    def _flag_widgets(self) -> List[QWidget]:
        return [
            self._start_edit,
            self._step_spin,
            self._radix_combo,
            self._pad_combo,
            self._width_spin,
            self._prefix_check,
            self._uppercase_check,
        ]

    def _sync_state(self, *_args):
        """模式切换 / 参数变化 → 刷新可用状态与预览。"""
        text_mode = bool(self._text_radio.isChecked())
        self._text_edit.setEnabled(text_mode)
        for widget in self._flag_widgets():
            widget.setEnabled(not text_mode)
        try:
            radix = int(self._radix_combo.currentData() or 10)
        except Exception:
            radix = 10
        self._prefix_check.setEnabled(not text_mode and radix != 10)
        self._uppercase_check.setEnabled(not text_mode and radix == 16)
        self._refresh_preview()

    def _refresh_preview(self):
        count = len(self._target.lines) if self._target else 0
        try:
            cfg = self.build_config()
        except ValueError as e:
            self._preview.setText(f"⚠ {e}")
            self._ok_button.setEnabled(False)
            return
        if count <= 0:
            self._preview.setText("⚠ 没有可编辑的目标行")
            self._ok_button.setEnabled(False)
            return

        if cfg.mode == MODE_TEXT:
            self._preview.setText(f"将在 {count} 行插入文本：{cfg.text!r}")
        else:
            values = preview_number_texts(
                cfg.start,
                cfg.step,
                count,
                radix=cfg.radix,
                pad=cfg.pad,
                min_width=cfg.min_width,
                prefix=cfg.prefix,
                uppercase=cfg.uppercase,
                preview=5,
            )
            joined = ", ".join(values)
            if count > len(values):
                joined += ", …"
            note = "（步长为 0：所有行都是同一个数字）" if cfg.step == 0 else ""
            self._preview.setText(f"将在 {count} 行插入：{joined}{note}")
        self._ok_button.setEnabled(True)

    # --------------------------------------------------------
    # 结果
    # --------------------------------------------------------
    def build_config(self) -> ColumnEditConfig:
        """从界面读出配置；参数非法时抛 ``ValueError``。"""
        if self._text_radio.isChecked():
            cfg = ColumnEditConfig(mode=MODE_TEXT, text=self._text_edit.text())
        else:
            cfg = ColumnEditConfig(
                mode=MODE_NUMBER,
                start=parse_int_literal(self._start_edit.text()),
                step=int(self._step_spin.value()),
                radix=int(self._radix_combo.currentData() or 10),
                pad=str(self._pad_combo.currentData() or PAD_NONE),
                min_width=int(self._width_spin.value()),
                prefix=bool(self._prefix_check.isChecked()),
                uppercase=bool(self._uppercase_check.isChecked()),
            )
        err = cfg.validate()
        if err:
            raise ValueError(err)
        return cfg

    def result_data(self) -> Optional[ColumnEditResult]:
        """已执行成功的列编辑结果（取消时为 None）。"""
        return self._result

    def accept(self):
        """确定：执行列编辑；失败则提示并保持对话框打开。

        幂等保护：某些 Qt 版本会把 ``QDialogButtonBox.accepted`` 自动接到
        对话框的 ``accept()`` 上（这里又显式接了一次），若不设防，同一次
        "确定"会**执行两遍**列编辑。
        """
        if self._result is not None:
            super().accept()
            return
        try:
            cfg = self.build_config()
        except ValueError as e:
            QMessageBox.warning(self, "列编辑器", str(e))
            return
        result = apply_column_edit(self._editor, cfg)
        if not result.ok:
            QMessageBox.warning(self, "列编辑器", result.reason or "无法执行列编辑")
            return
        self._result = result
        super().accept()

    # --------------------------------------------------------
    # 便捷入口
    # --------------------------------------------------------
    @classmethod
    def run(cls, editor, parent=None) -> Optional[ColumnEditResult]:
        """弹出对话框；用户确认并执行成功时返回结果，否则 None。"""
        dlg = cls(editor, parent)
        if dlg.exec_() == QDialog.Accepted:
            return dlg.result_data()
        return None
