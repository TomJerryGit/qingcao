# -*- coding: utf-8 -*-
"""快捷键帮助浮层"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class ShortcutOverlay(QWidget):
    """快捷键帮助浮层"""

    def __init__(self, action_manager, parent=None):
        super().__init__(parent)

        self.action_manager = action_manager

        # 无边框 + 置顶
        self.setWindowFlags(
            Qt.Popup | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        self._build_ui()
        self._apply_style()

        # 自动关闭定时器
        self._auto_close = QTimer(self)
        self._auto_close.setSingleShot(True)
        self._auto_close.timeout.connect(self.close)
        self._auto_close.start(5000)

    def _build_ui(self):
        # 主容器
        container = QFrame(self)
        container.setObjectName("overlay_container")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(10)

        # 标题
        title = QLabel("⌨ 快捷键速查")
        title.setObjectName("overlay_title")
        layout.addWidget(title)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(8)

        # 按分类分组
        categories = self._group_actions()

        for cat_name, actions in categories.items():
            cat_label = QLabel(cat_name)
            cat_label.setObjectName("overlay_category")
            content_layout.addWidget(cat_label)

            grid = QGridLayout()
            grid.setHorizontalSpacing(20)
            grid.setVerticalSpacing(4)

            for i, (name, shortcut, text) in enumerate(actions):
                row = i // 2
                col = (i % 2) * 2

                text_label = QLabel(text)
                text_label.setObjectName("overlay_text")
                grid.addWidget(text_label, row, col)

                key_label = QLabel(shortcut)
                key_label.setObjectName("overlay_key")
                key_label.setAlignment(Qt.AlignCenter)
                grid.addWidget(key_label, row, col + 1)

            content_layout.addLayout(grid)

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        # 提示
        hint = QLabel("按任意键关闭")
        hint.setObjectName("overlay_hint")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        # 大小
        self.setFixedSize(700, 500)

    def _apply_style(self):
        self.setStyleSheet("""
            QFrame#overlay_container {
                background-color: rgba(30, 30, 30, 245);
                border: 2px solid #7ec850;
                border-radius: 8px;
            }
            QLabel#overlay_title {
                color: #7ec850;
                font-size: 20px;
                font-weight: bold;
                padding: 4px;
                border-bottom: 1px solid #3c3c3c;
            }
            QLabel#overlay_category {
                color: #4dabf7;
                font-size: 14px;
                font-weight: bold;
                padding: 8px 0 4px 0;
            }
            QLabel#overlay_text {
                color: #d4d4d4;
                font-size: 12px;
            }
            QLabel#overlay_key {
                background-color: #3c3c3c;
                color: #7ec850;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 3px 10px;
                font-family: Consolas;
                font-size: 12px;
                font-weight: bold;
                min-width: 100px;
            }
            QLabel#overlay_hint {
                color: #888;
                font-size: 11px;
                padding: 8px;
            }
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #2d2d2d;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #555;
                border-radius: 4px;
                min-height: 20px;
            }
        """)

    def _group_actions(self):
        """按分类分组动作"""
        result = {}

        if not self.action_manager:
            return result

        try:
            categories = self.action_manager.get_categories()
        except Exception:
            return result

        for cat_name, names in categories.items():
            actions = []
            for name in names[:20]:  # 每类最多 20 个
                action = self.action_manager.get(name)
                if not action:
                    continue
                shortcut = action.shortcut().toString()
                if not shortcut:
                    continue
                text = action.text().replace('&', '')
                if len(text) > 30:
                    text = text[:27] + '...'
                actions.append((name, shortcut, text))
            if actions:
                result[cat_name] = actions

        return result

    def keyPressEvent(self, event):
        """任意键关闭"""
        self.close()

    def mousePressEvent(self, event):
        """点击关闭"""
        self.close()

    def show_at_center(self, parent=None):
        """在屏幕中央显示"""
        if parent:
            geo = parent.geometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)
        else:
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - self.width()) // 2
            y = (screen.height() - self.height()) // 2
            self.move(x, y)

        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()