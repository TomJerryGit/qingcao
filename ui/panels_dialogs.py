# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""辅助对话框（v2.24 拆出）。"""

from ui.panels_common import *


class ReplaceConfirmDialog(QDialog):
    """
    替换确认对话框。

    显示替换预览，让用户确认。
    """

    def __init__(self, pattern: str, replacement: str, matches: List[SearchMatch], parent=None):
        super().__init__(parent)

        self.setWindowTitle("确认替换")
        self.resize(600, 400)

        self._pattern = pattern
        self._replacement = replacement
        self._matches = matches

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 信息
        info = QLabel(f"将替换 <b>{len(self._matches)}</b> 处匹配。")
        info.setStyleSheet("font-size: 13px; padding: 8px;")
        layout.addWidget(info)

        # 预览
        preview_label = QLabel("预览:")
        layout.addWidget(preview_label)

        preview_edit = QPlainTextEdit()
        preview_edit.setReadOnly(True)

        preview_lines = []
        for match in self._matches[:50]:
            preview_lines.append(f"行 {match.line}: {match.line_text.strip()}")
            preview_lines.append(f"  → {self._replacement}")

        if len(self._matches) > 50:
            preview_lines.append(f"\n... 及其他 {len(self._matches) - 50} 处")

        preview_edit.setPlainText("\n".join(preview_lines))
        layout.addWidget(preview_edit)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Yes | QDialogButtonBox.No)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


# ============================================================
# 跳转到行对话框
# ============================================================


class GotoLineDialog(QDialog):
    """
    跳转到行对话框。
    """

    def __init__(self, max_line: int, current_line: int = 1, parent=None):
        super().__init__(parent)

        self.setWindowTitle("跳转到行")
        self.setFixedSize(300, 120)

        self._max_line = max_line
        self._current_line = current_line

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QFormLayout(self)

        # 行号输入
        self.line_spin = QSpinBox()
        self.line_spin.setRange(1, max(1, self._max_line))
        self.line_spin.setValue(self._current_line)
        self.line_spin.selectAll()
        layout.addRow("行号:", self.line_spin)

        # 提示
        info = QLabel(f"范围: 1 - {self._max_line}")
        info.setStyleSheet("color: #888; font-size: 11px;")
        layout.addRow("", info)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_line(self) -> int:
        """获取选中的行号"""
        return self.line_spin.value()


# ============================================================
# 编码选择对话框
# ============================================================


class EncodingDialog(QDialog):
    """
    编码选择对话框。
    """

    def __init__(self, current_encoding: str = "utf-8", parent=None):
        super().__init__(parent)

        self.setWindowTitle("选择编码")
        self.resize(320, 400)

        self._current_encoding = current_encoding.lower()

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索编码...")
        self.search_edit.textChanged.connect(self._on_filter)
        layout.addWidget(self.search_edit)

        # 列表
        self.list_widget = QListWidget()

        current_row = 0
        for i, (display_name, enc_name) in enumerate(ENCODINGS):
            item = QListWidgetItem(f"{display_name}  ({enc_name})")
            item.setData(Qt.UserRole, enc_name)

            if enc_name == self._current_encoding:
                current_row = i
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            self.list_widget.addItem(item)

        self.list_widget.setCurrentRow(current_row)
        self.list_widget.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.list_widget)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_filter(self, text: str):
        """过滤编码列表"""
        text = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(text not in item.text().lower())

    def get_encoding(self) -> str:
        """获取选中的编码"""
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return self._current_encoding


# ============================================================
# 行尾符选择对话框
# ============================================================


class LineEndingDialog(QDialog):
    """
    行尾符选择对话框。
    """

    def __init__(self, current_eol: str = "\n", parent=None):
        super().__init__(parent)

        self.setWindowTitle("选择行尾符")
        self.setFixedSize(300, 220)

        self._current_eol = current_eol

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 说明
        info = QLabel("选择行尾符：")
        layout.addWidget(info)

        # 列表
        self.list_widget = QListWidget()

        current_row = 0
        for i, (display_name, eol_name) in enumerate(LINE_ENDINGS):
            item = QListWidgetItem(display_name)
            item.setData(Qt.UserRole, eol_name)

            if eol_name == self._current_eol:
                current_row = i
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            self.list_widget.addItem(item)

        self.list_widget.setCurrentRow(current_row)
        self.list_widget.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.list_widget)

        # 提示
        hint = QLabel("转换后文件将被标记为已修改，保存后生效。")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_eol(self) -> str:
        """获取选中的行尾符"""
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return self._current_eol


# ============================================================
# 主题选择对话框
# ============================================================


class ThemeChooserDialog(QDialog):
    """
    主题选择对话框。
    """

    def __init__(self, themes_dir: str, current_theme: str = "", parent=None):
        super().__init__(parent)

        self.setWindowTitle("选择主题")
        self.resize(400, 500)

        self._themes_dir = themes_dir
        self._current_theme = current_theme
        self._selected_theme: Optional[str] = None

        self._build_ui()
        self._load_themes()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索主题...")
        self.search_edit.textChanged.connect(self._on_filter)
        layout.addWidget(self.search_edit)

        # 列表
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.accept)
        self.list_widget.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self.list_widget)

        # 预览
        self.preview_label = QLabel("选择主题以预览")
        self.preview_label.setStyleSheet(
            "background-color: #1e1e1e; color: #888; "
            "border: 1px solid #3c3c3c; padding: 8px; "
            "font-size: 12px;"
        )
        self.preview_label.setFixedHeight(60)
        layout.addWidget(self.preview_label)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_themes(self):
        """加载主题列表"""
        self.list_widget.clear()

        # 添加"跟随系统"选项
        system_item = QListWidgetItem("跟随系统")
        system_item.setData(Qt.UserRole, "__system__")
        self.list_widget.addItem(system_item)

        # 扫描主题目录
        if os.path.isdir(self._themes_dir):
            for filename in sorted(os.listdir(self._themes_dir)):
                if filename.endswith(".json"):
                    theme_name = os.path.splitext(filename)[0]
                    theme_path = os.path.join(self._themes_dir, filename)

                    item = QListWidgetItem(theme_name)
                    item.setData(Qt.UserRole, theme_path)

                    if theme_path == self._current_theme:
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                        self.list_widget.setCurrentItem(item)

                    self.list_widget.addItem(item)

    def _on_filter(self, text: str):
        """过滤主题"""
        text = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(text not in item.text().lower())

    def _on_selection(self):
        """选中项变化"""
        item = self.list_widget.currentItem()
        if item:
            theme_path = item.data(Qt.UserRole)
            if theme_path and theme_path != "__system__":
                self.preview_label.setText(f"主题文件: {os.path.basename(theme_path)}")
            else:
                self.preview_label.setText("跟随系统主题")

    def get_theme(self) -> Optional[str]:
        """获取选中的主题路径"""
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return None


# ============================================================
# 通用输入对话框
# ============================================================


class InputDialog(QDialog):
    """
    通用输入对话框。

    支持单行/多行文本输入。
    """

    def __init__(
        self, title: str, label: str, default: str = "", multiline: bool = False, parent=None
    ):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.resize(400, 200 if multiline else 130)

        self._multiline = multiline

        self._build_ui(title, label, default)

    def _build_ui(self, title: str, label: str, default: str):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 标签
        if label:
            lbl = QLabel(label)
            layout.addWidget(lbl)

        # 输入
        if self._multiline:
            self.input_edit = QPlainTextEdit()
            self.input_edit.setPlainText(default)
        else:
            self.input_edit = QLineEdit()
            self.input_edit.setText(default)
            self.input_edit.selectAll()
            self.input_edit.returnPressed.connect(self.accept)

        layout.addWidget(self.input_edit)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 焦点
        self.input_edit.setFocus()

    def get_text(self) -> str:
        """获取输入文本"""
        if self._multiline:
            return self.input_edit.toPlainText()
        return self.input_edit.text()


# ============================================================
# 进度对话框
# ============================================================


class ProgressDialog(QDialog):
    """
    进度对话框。

    可取消的进度显示。
    """

    def __init__(self, title: str = "处理中", maximum: int = 100, parent=None):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setFixedSize(400, 130)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._cancelled = False

        self._build_ui(title, maximum)

    def _build_ui(self, title: str, maximum: int):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 消息
        self.message_label = QLabel(title)
        self.message_label.setStyleSheet("font-size: 13px;")
        layout.addWidget(self.message_label)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, maximum)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # 状态
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.status_label)

        # 取消按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self._on_cancel)
        layout.addWidget(buttons)

    def _on_cancel(self):
        """取消"""
        self._cancelled = True
        self.reject()

    def set_value(self, value: int):
        """设置进度值"""
        self.progress_bar.setValue(value)

    def set_maximum(self, maximum: int):
        """设置最大值"""
        self.progress_bar.setMaximum(maximum)

    def set_message(self, message: str):
        """设置消息"""
        self.message_label.setText(message)

    def set_status(self, status: str):
        """设置状态"""
        self.status_label.setText(status)

    def is_cancelled(self) -> bool:
        """是否已取消"""
        return self._cancelled

    def increment(self, delta: int = 1):
        """增加进度"""
        self.progress_bar.setValue(self.progress_bar.value() + delta)


# ============================================================
# 消息提示条
# ============================================================
