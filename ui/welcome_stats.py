# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""提示/统计/页脚（v2.25 从 welcome_widget 拆出）。"""

from ui.welcome_widget_common import *  # noqa: F401,F403


class TipsPanel(QWidget):
    """
    每日技巧面板。

    随机显示一条使用技巧。
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._current_tip = ""

        self._build_ui()
        self._load_tip()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(8)

        # 标题行
        title_layout = QHBoxLayout()

        title = QLabel("💡 每日技巧")
        self.title_label = title
        title.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {C.panel_fg}; padding: 4px 0;"
        )
        title_layout.addWidget(title)

        title_layout.addStretch()

        # 换一条按钮
        self.next_btn = QToolButton()
        self.next_btn.setText("换一条")
        self.next_btn.setStyleSheet(f"""
            QToolButton {{
                color: {C.line_number_fg};
                background-color: transparent;
                border: none;
                font-size: 11px;
                padding: 2px 6px;
            }}
            QToolButton:hover {{
                color: {C.success};
                background-color: {C.menu_selection};
                border-radius: 3px;
            }}
        """)
        self.next_btn.clicked.connect(self._load_tip)
        title_layout.addWidget(self.next_btn)

        layout.addLayout(title_layout)

        # 技巧文本
        self.tip_label = QLabel()
        self.tip_label.setWordWrap(True)
        self.tip_label.setStyleSheet(f"""
            QLabel {{
                background-color: {C.panel_bg};
                color: {C.panel_fg};
                border-left: 3px solid {C.success};
                border-radius: 4px;
                padding: 12px 16px;
                font-size: 12px;
                line-height: 1.6;
            }}
        """)
        self.tip_label.setMinimumHeight(60)

        layout.addWidget(self.tip_label)

    def _load_tip(self):
        """加载随机技巧"""
        # 避免连续重复
        available_tips = [t for t in DAILY_TIPS if t != self._current_tip]
        if not available_tips:
            available_tips = DAILY_TIPS

        self._current_tip = random.choice(available_tips)
        self.tip_label.setText(_tr(self._current_tip))

    def refresh_theme(self, theme=None):
        """重放标题/换一条按钮/技巧卡片样式"""
        colors = getattr(theme, "colors", None) if theme else None
        if colors is not None:
            C.bind(colors)
        if getattr(self, "title_label", None) is not None:
            self.title_label.setStyleSheet(
                f"font-size: 14px; font-weight: bold; color: {C.panel_fg}; padding: 4px 0;"
            )
        self.next_btn.setStyleSheet(f"""
            QToolButton {{
                color: {C.line_number_fg};
                background-color: transparent;
                border: none;
                font-size: 11px;
                padding: 2px 6px;
            }}
            QToolButton:hover {{
                color: {C.success};
                background-color: {C.menu_selection};
                border-radius: 3px;
            }}
        """)
        self.tip_label.setStyleSheet(f"""
            QLabel {{
                background-color: {C.panel_bg};
                color: {C.panel_fg};
                border-left: 3px solid {C.success};
                border-radius: 4px;
                padding: 12px 16px;
                font-size: 12px;
                line-height: 1.6;
            }}
        """)


# ============================================================
# 使用统计面板
# ============================================================
class StatsPanel(QWidget):
    """
    使用统计面板。

    显示编辑器的使用统计信息。
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._build_ui()
        self._load_stats()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(8)

        # 标题
        title = QLabel("📊 使用统计")
        self.title_label = title
        title.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {C.panel_fg}; padding: 4px 0;"
        )
        layout.addWidget(title)

        # 统计网格
        grid = QGridLayout()
        grid.setSpacing(8)

        self.stats_labels: Dict[str, QLabel] = {}

        stats_definitions = [
            ("saves", "保存次数", "💾"),
            ("files_opened", "打开文件", "📂"),
            ("lines_edited", "编辑行数", "✏"),
            ("macros_used", "宏使用", "⏺"),
        ]

        for i, (key, display, icon) in enumerate(stats_definitions):
            row = i // 2
            col = i % 2

            # 统计项
            item_widget = QWidget()
            item_widget.setObjectName("stat_card")
            item_widget.setStyleSheet(f"""
                QWidget {{
                    background-color: {C.panel_bg};
                    border-radius: 4px;
                }}
            """)
            item_layout = QVBoxLayout(item_widget)
            item_layout.setContentsMargins(10, 8, 10, 8)
            item_layout.setSpacing(2)

            value_label = QLabel("0")
            value_label.setObjectName("stat_value")
            value_label.setStyleSheet(
                f"font-size: 20px; font-weight: bold; color: {C.success}; background: transparent;"
            )
            item_layout.addWidget(value_label)

            label = QLabel(f"{icon} {display}")
            label.setObjectName("stat_name")
            label.setStyleSheet(
                f"font-size: 11px; color: {C.line_number_fg}; background: transparent;"
            )
            item_layout.addWidget(label)

            self.stats_labels[key] = value_label

            grid.addWidget(item_widget, row, col)

        layout.addLayout(grid)

    def _load_stats(self):
        """加载统计数据。

        P1-B6: 改用 core.usage_stats

        原实现读取 data/onboarding.json，但该文件从未被任何
        模块写入，导致统计面板永远显示 0。改用统一的
        core.usage_stats（数据源：telemetry / session /
        local_completer）。
        """
        try:
            from core.usage_stats import get_usage_stats

            snap = get_usage_stats().get_snapshot()

            self.update_stat("saves", int(snap.files_saved))
            self.update_stat("files_opened", int(snap.files_opened))
            # lines_edited：用累计编辑时长（秒）近似
            self.update_stat("lines_edited", int(snap.total_edit_time))
            # macros_used：用加载插件数近似
            self.update_stat("macros_used", int(snap.plugins_loaded))
        except ImportError as e:
            print(f"[StatsPanel] core.usage_stats 不可用: {e}")
        except Exception as e:
            print(f"[StatsPanel] 加载统计失败: {e}")

    def update_stat(self, key: str, value: int):
        """更新统计值"""
        label = self.stats_labels.get(key)
        if label:
            # 格式化大数字
            if value >= 1000000:
                text = f"{value / 1000000:.1f}M"
            elif value >= 1000:
                text = f"{value / 1000:.1f}K"
            else:
                text = str(value)

            label.setText(text)

    def refresh(self):
        """刷新统计"""
        self._load_stats()

    def refresh_theme(self, theme=None):
        """重放统计卡片样式（卡片底色/数值色随主题）"""
        colors = getattr(theme, "colors", None) if theme else None
        if colors is not None:
            C.bind(colors)
        if getattr(self, "title_label", None) is not None:
            self.title_label.setStyleSheet(
                f"font-size: 14px; font-weight: bold; color: {C.panel_fg}; padding: 4px 0;"
            )
        for card in self.findChildren(QWidget):
            if card.objectName() == "stat_card":
                card.setStyleSheet(f"""
                    QWidget {{
                        background-color: {C.panel_bg};
                        border-radius: 4px;
                    }}
                """)
        for lbl in self.findChildren(QLabel):
            name = lbl.objectName()
            if name == "stat_value":
                lbl.setStyleSheet(
                    f"font-size: 20px; font-weight: bold; "
                    f"color: {C.success}; background: transparent;"
                )
            elif name == "stat_name":
                lbl.setStyleSheet(
                    f"font-size: 11px; color: {C.line_number_fg}; background: transparent;"
                )


# ============================================================
# 底部信息
# ============================================================
class WelcomeFooter(QWidget):
    """
    欢迎页底部信息。

    显示作者、邮箱、链接。
    """

    link_clicked = pyqtSignal(str)  # URL

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedHeight(50)

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignCenter)

        # 开发者
        author_label = QLabel(f"开发者: {AUTHOR}")
        author_label.setStyleSheet(f"color: {C.line_number_fg}; font-size: 11px;")
        layout.addWidget(author_label)

        # 分隔符
        sep = QLabel("·")
        sep.setStyleSheet(f"color: {C.border};")
        layout.addWidget(sep)

        # 邮箱
        email_label = QLabel(f"📧 {EMAIL}")
        email_label.setStyleSheet(f"color: {C.line_number_fg}; font-size: 11px;")
        email_label.setToolTip("点击复制邮箱")
        email_label.setCursor(Qt.PointingHandCursor)
        email_label.mousePressEvent = lambda e: self._copy_email()
        layout.addWidget(email_label)

        # 分隔符
        sep2 = QLabel("·")
        sep2.setStyleSheet(f"color: {C.border};")
        layout.addWidget(sep2)

        # 文档链接
        docs_label = QLabel("📖 文档")
        docs_label.setStyleSheet(f"""
            color: {C.info};
            font-size: 11px;
            text-decoration: underline;
        """)
        docs_label.setCursor(Qt.PointingHandCursor)
        docs_label.mousePressEvent = lambda e: self.link_clicked.emit(DOCS_URL)
        layout.addWidget(docs_label)

        # 分隔符
        sep3 = QLabel("·")
        sep3.setStyleSheet(f"color: {C.border};")
        layout.addWidget(sep3)

        # GitHub
        github_label = QLabel("🐙 GitHub")
        github_label.setStyleSheet(f"""
            color: {C.info};
            font-size: 11px;
            text-decoration: underline;
        """)
        github_label.setCursor(Qt.PointingHandCursor)
        github_label.mousePressEvent = lambda e: self.link_clicked.emit(HOMEPAGE)
        layout.addWidget(github_label)

    def _copy_email(self):
        """复制邮箱到剪贴板"""
        try:
            QApplication.clipboard().setText(EMAIL)
            bus.emit_status(f"已复制邮箱: {EMAIL}", 2000, "success")
        except Exception:
            pass

    def refresh_theme(self, theme=None):
        """重放 Footer 文字与链接颜色"""
        colors = getattr(theme, "colors", None) if theme else None
        if colors is not None:
            C.bind(colors)
        for lbl in self.findChildren(QLabel):
            t = lbl.text()
            if t == "·":
                lbl.setStyleSheet(f"color: {C.border};")
            elif t.startswith("开发者") or t.startswith("📧"):
                lbl.setStyleSheet(f"color: {C.line_number_fg}; font-size: 11px;")
            elif t.startswith(("📖", "🐙")):
                lbl.setStyleSheet(f"""
                    color: {C.info};
                    font-size: 11px;
                    text-decoration: underline;
                """)


# ============================================================
# 欢迎页主控件
# ============================================================
