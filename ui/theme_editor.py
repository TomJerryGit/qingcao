# -*- coding: utf-8 -*-
"""主题编辑器"""
import json
import os

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


# 颜色分组定义
COLOR_GROUPS = {
    "编辑器基础": [
        ("background", "背景", "#1e1e1e"),
        ("foreground", "前景（文字）", "#d4d4d4"),
        ("caret", "光标", "#aeafad"),
        ("current_line", "当前行高亮", "#2a2d2e"),
        ("selection", "选区背景", "#264f78"),
    ],
    "语法高亮": [
        ("comment", "注释", "#6a9955"),
        ("keyword", "关键字", "#569cd6"),
        ("number", "数字", "#b5cea8"),
        ("string", "字符串", "#ce9178"),
        ("class_name", "类名", "#4ec9b0"),
        ("function_name", "函数名", "#dcdcaa"),
        ("decorator", "装饰器", "#c586c0"),
        ("operator", "运算符", "#d4d4d4"),
    ],
    "行号与边距": [
        ("line_number_bg", "行号背景", "#2d2d2d"),
        ("line_number_fg", "行号前景", "#858585"),
        ("margin_bg", "边距背景", "#2d2d2d"),
        ("margin_fg", "边距前景", "#858585"),
    ],
    "UI 元素": [
        ("window_bg", "窗口背景", "#1e1e1e"),
        ("window_fg", "窗口文字", "#d4d4d4"),
        ("menubar_bg", "菜单栏背景", "#252526"),
        ("menubar_fg", "菜单栏文字", "#d4d4d4"),
        ("statusbar_bg", "状态栏背景", "#007acc"),
        ("statusbar_fg", "状态栏文字", "#ffffff"),
        ("tab_bg", "标签背景", "#2d2d2d"),
        ("tab_active_bg", "活动标签背景", "#1e1e1e"),
        ("panel_bg", "面板背景", "#252526"),
        ("border", "边框", "#3c3c3c"),
    ],
    "强调色": [
        ("accent", "强调色", "#7ec850"),
        ("warning", "警告", "#f0ad4e"),
        ("error", "错误", "#f14c4c"),
        ("success", "成功", "#7ec850"),
        ("info", "信息", "#4dabf7"),
    ],
}


class ColorRow(QWidget):
    """单行颜色编辑"""

    color_changed = pyqtSignal(str, str)  # key, color

    def __init__(self, key, name, default_color, parent=None):
        super().__init__(parent)
        self.key = key
        self.name = name
        self.color = default_color

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        # 名称
        label = QLabel(name)
        label.setMinimumWidth(100)
        layout.addWidget(label)

        # 颜色块（可点击）
        self.color_button = QPushButton()
        self.color_button.setFixedSize(60, 24)
        self.color_button.setStyleSheet(
            f"background-color: {default_color}; "
            f"border: 1px solid #555; border-radius: 3px;"
        )
        self.color_button.clicked.connect(self._pick_color)
        layout.addWidget(self.color_button)

        # 十六进制显示
        self.hex_edit = QLineEdit(default_color)
        self.hex_edit.setMaximumWidth(100)
        self.hex_edit.editingFinished.connect(self._on_hex_changed)
        layout.addWidget(self.hex_edit)

        layout.addStretch()

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self.color), self, "选择颜色")
        if color.isValid():
            self._set_color(color.name())

    def _on_hex_changed(self):
        text = self.hex_edit.text().strip()
        if not text.startswith("#"):
            text = "#" + text
        color = QColor(text)
        if color.isValid():
            self._set_color(color.name())
        else:
            self.hex_edit.setText(self.color)

    def _set_color(self, color):
        self.color = color
        self.color_button.setStyleSheet(
            f"background-color: {color}; "
            f"border: 1px solid #555; border-radius: 3px;"
        )
        self.hex_edit.setText(color)
        self.color_changed.emit(self.key, color)

    def get_color(self):
        return self.color


class ThemeEditor(QDialog):
    """主题编辑器"""

    theme_saved = pyqtSignal(str)  # 主题文件路径

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("主题编辑器")
        self.resize(800, 600)

        self._color_rows = {}
        self._theme_data = {}

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 顶部工具栏
        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("主题名称:"))
        self.name_edit = QLineEdit("my_theme")
        self.name_edit.setMaximumWidth(200)
        toolbar.addWidget(self.name_edit)

        toolbar.addStretch()

        # E3 修复：emoji 被 GBK 编辑器写坏成 ?，去掉 emoji 前缀
        load_btn = QPushButton("加载主题")
        load_btn.clicked.connect(self._load_theme)
        toolbar.addWidget(load_btn)

        save_btn = QPushButton("保存主题")
        save_btn.clicked.connect(self._save_theme)
        toolbar.addWidget(save_btn)

        layout.addLayout(toolbar)

        # 中间：颜色编辑区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        content_layout = QVBoxLayout(content)

        for group_name, colors in COLOR_GROUPS.items():
            group_box = QGroupBox(group_name)
            group_layout = QVBoxLayout(group_box)

            for key, name, default in colors:
                row = ColorRow(key, name, default, self)
                row.color_changed.connect(self._on_color_changed)
                self._color_rows[key] = row
                group_layout.addWidget(row)

            content_layout.addWidget(group_box)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # 底部按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Close
        )
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; }
            QGroupBox {
                color: #7ec850; border: 1px solid #3c3c3c;
                border-radius: 4px; margin-top: 10px; padding-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px; padding: 0 5px;
            }
            QLineEdit {
                background-color: #3c3c3c; color: #d4d4d4;
                border: 1px solid #555; border-radius: 3px;
                padding: 4px;
            }
            QPushButton {
                background-color: #0e639c; color: white;
                border: none; border-radius: 3px;
                padding: 6px 16px; min-width: 80px;
            }
            QPushButton:hover { background-color: #1177bb; }
        """)

    def _on_color_changed(self, key, color):
        """颜色改变"""
        self._theme_data[key] = color

    def _load_theme(self):
        """加载主题文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "加载主题", "", "主题文件 (*.json)"
        )
        if not path:
            return

        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)

            # 加载名称
            self.name_edit.setText(
                os.path.splitext(os.path.basename(path))[0]
            )

            # 加载颜色
            colors = data.get('colors', {})
            for key, color in colors.items():
                if key in self._color_rows:
                    self._color_rows[key]._set_color(color)

            QMessageBox.information(self, "成功", "主题已加载")
        except Exception as e:
            QMessageBox.warning(self, "加载失败", str(e))

    def _save_theme(self):
        """保存主题"""
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "错误", "请输入主题名称")
            return

        # 选择保存位置
        default_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "themes"
        )
        os.makedirs(default_dir, exist_ok=True)

        path, _ = QFileDialog.getSaveFileName(
            self, "保存主题",
            os.path.join(default_dir, f"{name}.json"),
            "主题文件 (*.json)"
        )

        if not path:
            return

        try:
            # 收集所有颜色
            colors = {}
            for key, row in self._color_rows.items():
                colors[key] = row.get_color()

            # 构建主题数据
            theme_data = {
                'name': name,
                'display_name': name,
                'type': 'dark',
                'version': 2,
                'colors': colors,
                'font_family': 'Consolas',
                'font_size': 12,
            }

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(theme_data, f, indent=2, ensure_ascii=False)

            QMessageBox.information(
                self, "成功",
                f"主题已保存到:\n{path}\n\n"
                f"可在\"视图 → 主题\"中应用。"
            )
            self.theme_saved.emit(path)
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))