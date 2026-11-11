# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""最近文件列表（v2.25 从 welcome_widget 拆出）。"""

from ui.welcome_widget_common import *  # noqa: F401,F403


class RecentFilesList(QWidget):
    """
    最近文件列表。

    显示最近打开的文件和项目。
    """

    file_clicked = pyqtSignal(str)  # 文件路径
    project_clicked = pyqtSignal(str)  # 项目路径

    def __init__(self, parent=None):
        super().__init__(parent)

        self._settings = QSettings("QingCao", "Editor")

        self._build_ui()
        self._load_recent()

        # 修复说明（P2-2）: 订阅文件事件自动刷新最近列表
        try:
            from app.event_bus import bus

            bus.file_opened.connect(self._on_file_event)
            bus.file_saved.connect(self._on_file_event)
        except Exception as e:
            print(f"[RecentFilesList] 事件订阅失败: {e}")

    def _on_file_event(self, event):
        """文件事件回调 —— 刷新最近列表"""
        try:
            QTimer.singleShot(100, self._load_recent)
        except Exception:
            pass

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(8)

        # 标题行
        title_layout = QHBoxLayout()

        self.title_label = QLabel(_tr("最近打开"))
        self.title_label.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {C.panel_fg}; padding: 4px 0;"
        )
        title_layout.addWidget(self.title_label)

        title_layout.addStretch()

        # 清空按钮
        self.clear_btn = QToolButton()
        self.clear_btn.setText(_tr("清空"))
        self.clear_btn.setStyleSheet(f"""
            QToolButton {{
                color: {C.line_number_fg};
                background-color: transparent;
                border: none;
                font-size: 11px;
                padding: 2px 6px;
            }}
            QToolButton:hover {{
                color: {C.error};
                background-color: {C.menu_selection};
                border-radius: 3px;
            }}
        """)
        self.clear_btn.clicked.connect(self._clear_recent)
        title_layout.addWidget(self.clear_btn)

        layout.addLayout(title_layout)

        # 文件列表
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("recent_list")
        self.list_widget.setFrameShape(QFrame.NoFrame)
        self.list_widget.setSelectionMode(QListWidget.SingleSelection)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.setStyleSheet(f"""
            QListWidget#recent_list {{
                background-color: transparent;
                border: none;
                color: {C.panel_fg};
                font-size: 12px;
                outline: none;
            }}
            QListWidget#recent_list::item {{
                padding: 6px 10px;
                border-radius: 4px;
                margin: 1px 0;
            }}
            QListWidget#recent_list::item:hover {{
                background-color: {C.menu_bg};
            }}
            QListWidget#recent_list::item:selected {{
                background-color: {C.menu_selection};
                color: {C.selection_foreground};
            }}
        """)

        layout.addWidget(self.list_widget, 1)

    # --------------------------------------------------------
    # 加载
    # --------------------------------------------------------
    def _load_recent(self):
        """加载最近文件列表"""
        self.list_widget.clear()

        # 加载最近文件
        files = self._settings.value("recent_files", [])
        if isinstance(files, str):
            files = [files] if files else []

        file_count = 0
        for filepath in files:
            if not filepath or not os.path.exists(filepath):
                continue

            if file_count >= MAX_RECENT_FILES:
                break

            item = self._create_file_item(filepath)
            self.list_widget.addItem(item)
            file_count += 1

        # 加载最近项目
        projects = self._settings.value("recent_projects", [])
        if isinstance(projects, str):
            projects = [projects] if projects else []

        project_count = 0
        for project_path in projects:
            if not project_path or not os.path.exists(project_path):
                continue

            if project_count >= MAX_RECENT_PROJECTS:
                break

            item = self._create_project_item(project_path)
            self.list_widget.addItem(item)
            project_count += 1

        # 空状态
        if self.list_widget.count() == 0:
            empty_item = QListWidgetItem("（暂无最近打开的文件）")
            empty_item.setForeground(QColor(C.line_number_fg))
            empty_item.setFlags(Qt.NoItemFlags)
            empty_item.setTextAlignment(Qt.AlignCenter)
            self.list_widget.addItem(empty_item)

    def _create_file_item(self, filepath: str) -> QListWidgetItem:
        """创建文件列表项"""
        item = QListWidgetItem()

        # 图标（根据文件类型）
        ext = os.path.splitext(filepath)[1].lower()
        icon_map = {
            ".py": "🐍",
            ".js": "📜",
            ".ts": "📘",
            ".cpp": "⚙",
            ".c": "⚙",
            ".h": "📋",
            ".java": "☕",
            ".go": "🐹",
            ".rs": "🦀",
            ".md": "📝",
            ".txt": "📄",
            ".json": "📊",
            ".xml": "📋",
            ".html": "🌐",
            ".css": "🎨",
            ".log": "📃",
            ".csv": "📈",
        }
        icon = icon_map.get(ext, "📄")

        # 文件名和路径
        filename = os.path.basename(filepath)
        dirname = os.path.dirname(filepath)

        # 缩略路径
        if len(dirname) > 50:
            dirname = "..." + dirname[-47:]

        item.setText(f"{icon}  {filename}")
        item.setToolTip(f"{filepath}\n\n双击打开")

        item.setData(Qt.UserRole, "file")
        item.setData(Qt.UserRole + 1, filepath)

        return item

    def _create_project_item(self, project_path: str) -> QListWidgetItem:
        """创建项目列表项"""
        item = QListWidgetItem()

        name = os.path.basename(project_path)
        if name.endswith(".qingcao-project"):
            name = name[:-16]

        item.setText(f"📁  [项目] {name}")
        item.setToolTip(f"{project_path}\n\n双击打开项目")

        item.setData(Qt.UserRole, "project")
        item.setData(Qt.UserRole + 1, project_path)

        return item

    # --------------------------------------------------------
    # 交互
    # --------------------------------------------------------
    def _on_item_clicked(self, item: QListWidgetItem):
        """单击项"""
        # 单击仅选中，不打开
        pass

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """双击项"""
        item_type = item.data(Qt.UserRole)
        path = item.data(Qt.UserRole + 1)

        if not path:
            return

        if item_type == "file":
            self.file_clicked.emit(path)
        elif item_type == "project":
            self.project_clicked.emit(path)

    def _clear_recent(self):
        """清空最近列表"""
        # 关键修复：QMessageBox 已在顶部导入
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空最近文件列表吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        self._settings.setValue("recent_files", [])
        self._settings.setValue("recent_projects", [])
        self._load_recent()

    def refresh(self):
        """刷新列表"""
        self._load_recent()

    def refresh_theme(self, theme=None):
        """重放标题/清空按钮/列表样式"""
        colors = getattr(theme, "colors", None) if theme else None
        if colors is not None:
            C.bind(colors)
        self.title_label.setStyleSheet(
            f"font-size: 14px; font-weight: bold; color: {C.panel_fg}; padding: 4px 0;"
        )
        self.clear_btn.setStyleSheet(f"""
            QToolButton {{
                color: {C.line_number_fg};
                background-color: transparent;
                border: none;
                font-size: 11px;
                padding: 2px 6px;
            }}
            QToolButton:hover {{
                color: {C.error};
                background-color: {C.menu_selection};
                border-radius: 3px;
            }}
        """)
        self.list_widget.setStyleSheet(f"""
            QListWidget#recent_list {{
                background-color: transparent;
                border: none;
                color: {C.panel_fg};
                font-size: 12px;
                outline: none;
            }}
            QListWidget#recent_list::item {{
                padding: 6px 10px;
                border-radius: 4px;
                margin: 1px 0;
            }}
            QListWidget#recent_list::item:hover {{
                background-color: {C.menu_bg};
            }}
            QListWidget#recent_list::item:selected {{
                background-color: {C.menu_selection};
                color: {C.selection_foreground};
            }}
        """)


# ============================================================
# 每日技巧面板
# ============================================================
