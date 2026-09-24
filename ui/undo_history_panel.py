# -*- coding: utf-8 -*-
"""撤销历史面板"""
from PyQt5.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QPushButton, QLabel, QMenu, QToolButton
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


class UndoHistoryPanel(QDockWidget):
    """撤销/重做历史面板"""

    def __init__(self, main_window=None, parent=None):
        super().__init__("撤销历史", parent or main_window)
        self.main_window = main_window
        self.setObjectName("UndoHistoryPanel")
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 工具条
        toolbar = QHBoxLayout()

        refresh_btn = QToolButton()
        refresh_btn.setText("🔄")
        refresh_btn.setToolTip("刷新")
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(refresh_btn)

        toolbar.addStretch()

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #888; font-size: 11px;")
        toolbar.addWidget(self.count_label)

        layout.addLayout(toolbar)

        # 历史列表
        self.history_list = QListWidget()
        self.history_list.itemDoubleClicked.connect(self._on_jump)
        self.history_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(
            self._show_context_menu
        )
        layout.addWidget(self.history_list, 1)

        # 当前状态指示
        self.current_label = QLabel("当前: 最新")
        self.current_label.setStyleSheet(
            "background-color: #094771; color: white; "
            "padding: 4px 8px; border-radius: 3px;"
        )
        layout.addWidget(self.current_label)

        self.setWidget(container)


    def refresh_theme(self, theme):
        """主题变更时刷新样式（v3.0）"""
        try:
            from infrastructure.theme_loader import adapt_qss_colors
            # 保存原始 QSS（只保存一次）
            if not hasattr(self, '_original_qss') or not self._original_qss:
                self._original_qss = self.styleSheet()
            if self._original_qss:
                qss = adapt_qss_colors(self._original_qss, theme)
                self.setStyleSheet(qss)
        except Exception as e:
            print(f"[{self.__class__.__name__}] refresh_theme 失败: {e}")

    def _apply_style(self):
        self.setStyleSheet("""
            QDockWidget { background-color: #252526; color: #d4d4d4; }
            QDockWidget::title {
                background-color: #2d2d2d;
                padding: 4px 8px;
                border-bottom: 1px solid #3c3c3c;
            }
            QListWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                font-size: 12px;
                outline: none;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-radius: 2px;
            }
            QListWidget::item:hover { background-color: #2a2d2e; }
            QListWidget::item:selected { background-color: #094771; }
            QLabel { color: #d4d4d4; }
            QToolButton {
                background-color: transparent;
                color: #d4d4d4;
                border: none;
                padding: 4px 8px;
            }
            QToolButton:hover {
                background-color: #3c3c3c;
                border-radius: 3px;
            }
        """)

    def refresh(self):
        """刷新历史列表"""
        self.history_list.clear()
        self._entries = []

        proxy = None
        if self.main_window and hasattr(self.main_window, 'tabs'):
            proxy = self.main_window.tabs.current_proxy()

        if not proxy or not hasattr(proxy, 'undo_manager'):
            self.count_label.setText("无编辑器")
            return

        undo_mgr = proxy.undo_manager
        undo_stack = getattr(undo_mgr, 'undo_stack', [])
        redo_stack = getattr(undo_mgr, 'redo_stack', [])

        # 显示已撤销的（重做栈，倒序）
        for i, cmd in enumerate(reversed(redo_stack)):
            desc = cmd.describe() if hasattr(cmd, 'describe') else str(cmd)
            item = QListWidgetItem("↪ [可重做] %s" % desc)
            item.setForeground(QColor("#888"))
            item.setData(Qt.UserRole, ('redo', len(redo_stack) - 1 - i))
            self.history_list.addItem(item)
            self._entries.append(item)

        # 显示当前光标位置
        current_item = QListWidgetItem("▶ 当前状态")
        current_item.setForeground(QColor("#7ec850"))
        font = current_item.font()
        font.setBold(True)
        current_item.setFont(font)
        current_item.setData(Qt.UserRole, ('current', -1))
        self.history_list.addItem(current_item)
        self._current_row = self.history_list.count() - 1

        # 显示已执行的（撤销栈，倒序）
        for i, cmd in enumerate(reversed(undo_stack)):
            desc = cmd.describe() if hasattr(cmd, 'describe') else str(cmd)
            item = QListWidgetItem("↩ %s" % desc)
            item.setData(Qt.UserRole, ('undo', len(undo_stack) - 1 - i))
            self.history_list.addItem(item)
            self._entries.append(item)

        # 滚动到当前
        self.history_list.setCurrentRow(self._current_row)
        self.history_list.scrollToItem(
            self.history_list.item(self._current_row),
            QListWidget.PositionAtCenter
        )

        # 更新计数
        self.count_label.setText(
            "撤销 %d · 重做 %d" % (len(undo_stack), len(redo_stack))
        )
        self.current_label.setText(
            "当前: 撤销栈顶 (%d 步)" % len(undo_stack)
        )

    def _on_jump(self, item):
        """双击跳转"""
        data = item.data(Qt.UserRole)
        if not data:
            return

        kind, idx = data
        if kind == 'current':
            return

        proxy = None
        if self.main_window and hasattr(self.main_window, 'tabs'):
            proxy = self.main_window.tabs.current_proxy()

        if not proxy or not hasattr(proxy, 'undo_manager'):
            return

        undo_mgr = proxy.undo_manager
        undo_stack = getattr(undo_mgr, 'undo_stack', [])
        redo_stack = getattr(undo_mgr, 'redo_stack', [])

        try:
            if kind == 'undo':
                # 撤销到该点
                steps = len(undo_stack) - idx
                for _ in range(steps):
                    if not undo_mgr.undo(proxy.sc):
                        break

            elif kind == 'redo':
                # 重做到该点
                steps = idx + 1
                for _ in range(steps):
                    if not undo_mgr.redo(proxy.sc):
                        break

            self.refresh()
        except Exception as e:
            print("[UndoHistory] 跳转失败: %s" % e)

    def _show_context_menu(self, pos):
        item = self.history_list.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)

        jump_act = menu.addAction("➡ 跳转到此状态")
        jump_act.triggered.connect(lambda: self._on_jump(item))

        menu.exec_(self.history_list.mapToGlobal(pos))