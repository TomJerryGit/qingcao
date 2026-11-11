# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""欢迎页头部/快捷动作（v2.25 从 welcome_widget 拆出）。"""

from ui.welcome_widget_common import *  # noqa: F401,F403


class WelcomeHeader(QWidget):
    """
    欢迎页头部。

    显示 Logo、应用名称、版本、标语。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(160)

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 30, 0, 10)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

        # Logo（大字）
        self.logo_label = QLabel("🌱")
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setStyleSheet("font-size: 48px;")
        layout.addWidget(self.logo_label)

        # 应用名称
        self.title_label = QLabel(_tr(APP_NAME))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet(
            f"font-size: 28px; font-weight: bold; color: {C.success}; letter-spacing: 4px;"
        )
        layout.addWidget(self.title_label)

        # 版本信息
        version_label = QLabel(f"v{APP_VERSION}  ·  {_tr(APP_DESCRIPTION)}")
        version_label.setObjectName("welcome_version")
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setStyleSheet(f"font-size: 12px; color: {C.line_number_fg};")
        layout.addWidget(version_label)

        # 标语
        self.slogan_label = QLabel(_tr(APP_SLOGAN))
        self.slogan_label.setObjectName("welcome_slogan")
        self.slogan_label.setAlignment(Qt.AlignCenter)
        self.slogan_label.setStyleSheet(
            f"font-size: 13px; color: {C.line_number_fg}; font-style: italic; letter-spacing: 2px;"
        )
        layout.addWidget(self.slogan_label)

    def refresh_theme(self, theme=None):
        """重放头部内联样式（标题/版本/标语颜色随主题）"""
        colors = getattr(theme, "colors", None) if theme else None
        if colors is not None:
            C.bind(colors)
        self.title_label.setStyleSheet(
            f"font-size: 28px; font-weight: bold; color: {C.success}; letter-spacing: 4px;"
        )
        for lbl in self.findChildren(QLabel):
            name = lbl.objectName()
            if name == "welcome_version":
                lbl.setStyleSheet(f"font-size: 12px; color: {C.line_number_fg};")
            elif name == "welcome_slogan":
                lbl.setStyleSheet(
                    f"font-size: 13px; color: {C.line_number_fg}; "
                    f"font-style: italic; letter-spacing: 2px;"
                )


# ============================================================
# 快捷操作面板
# ============================================================


class QuickActionsPanel(QWidget):
    """
    快捷操作面板。

    提供新建、打开、文件夹等入口。
    """

    action_triggered = pyqtSignal(str)  # action_key

    def __init__(self, parent=None):
        super().__init__(parent)

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(8)

        # 标题
        title = QLabel(_tr("快速开始"))
        self.title_label = title
        title.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {C.panel_fg}; padding: 4px 0;"
        )
        layout.addWidget(title)

        # 按钮网格
        grid = QGridLayout()
        grid.setSpacing(8)

        for i, (icon, text, shortcut, key) in enumerate(QUICK_ACTIONS):
            btn = self._create_action_button(icon, text, shortcut, key)
            row = i // 3
            col = i % 3
            grid.addWidget(btn, row, col)

        layout.addLayout(grid)

    def _create_action_button(self, icon: str, text: str, shortcut: str, key: str) -> QPushButton:
        """创建操作按钮"""
        btn = QPushButton()
        btn.setObjectName("quick_action_button")
        btn.setFixedHeight(60)
        btn.setCursor(Qt.PointingHandCursor)

        # 内容
        if shortcut:
            btn.setText(f"{icon}  {text}\n     {shortcut}")
        else:
            btn.setText(f"{icon}  {text}")

        btn.setStyleSheet(f"""
            QPushButton#quick_action_button {{
                background-color: {C.menu_bg};
                color: {C.panel_fg};
                border: 1px solid {C.border};
                border-radius: 6px;
                font-size: 12px;
                text-align: left;
                padding: 8px 12px;
            }}
            QPushButton#quick_action_button:hover {{
                background-color: {C.menu_selection};
                border-color: {C.accent};
                color: {C.selection_foreground};
            }}
            QPushButton#quick_action_button:pressed {{
                background-color: {C.button_pressed};
            }}
        """)

        btn.clicked.connect(lambda: self.action_triggered.emit(key))

        return btn

    def refresh_theme(self, theme=None):
        """重放快捷操作按钮样式（卡片底色/边框随主题）"""
        colors = getattr(theme, "colors", None) if theme else None
        if colors is not None:
            C.bind(colors)
        if getattr(self, "title_label", None) is not None:
            self.title_label.setStyleSheet(
                f"font-size: 14px; font-weight: bold; color: {C.panel_fg}; padding: 4px 0;"
            )
        for btn in self.findChildren(QPushButton):
            if btn.objectName() != "quick_action_button":
                continue
            btn.setStyleSheet(f"""
                QPushButton#quick_action_button {{
                    background-color: {C.menu_bg};
                    color: {C.panel_fg};
                    border: 1px solid {C.border};
                    border-radius: 6px;
                    font-size: 12px;
                    text-align: left;
                    padding: 8px 12px;
                }}
                QPushButton#quick_action_button:hover {{
                    background-color: {C.menu_selection};
                    border-color: {C.accent};
                    color: {C.selection_foreground};
                }}
                QPushButton#quick_action_button:pressed {{
                    background-color: {C.button_pressed};
                }}
            """)


# ============================================================
# 最近文件列表
# ============================================================
