# -*- coding: utf-8 -*-
"""问题面板"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.problems import Severity, get_problem_manager


SEVERITY_ICONS = {
    "error": "✗",
    "warning": "⚠",
    "info": "ℹ",
    "hint": "💡",
}

SEVERITY_COLORS = {
    "error": QColor("#f14c4c"),
    "warning": QColor("#f0ad4e"),
    "info": QColor("#4dabf7"),
    "hint": QColor("#888888"),
}


class ProblemsPanel(QDockWidget):
    """问题面板"""

    def __init__(self, main_window=None, parent=None):
        super().__init__("问题", parent or main_window)
        self.main_window = main_window
        self.setObjectName("ProblemsPanel")
        self.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)

        self.pm = get_problem_manager()
        self.pm.problems_changed.connect(self.refresh)

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 工具条
        top = QHBoxLayout()

        refresh_btn = QToolButton()
        refresh_btn.setText("🔄")
        refresh_btn.setToolTip("刷新")
        refresh_btn.clicked.connect(self.refresh)
        top.addWidget(refresh_btn)

        clear_btn = QToolButton()
        clear_btn.setText("🗑")
        clear_btn.setToolTip("清空所有")
        clear_btn.clicked.connect(self.pm.clear)
        top.addWidget(clear_btn)

        sandbox_clear_btn = QToolButton()
        sandbox_clear_btn.setText("🧹")
        sandbox_clear_btn.setToolTip("清除沙箱诊断")
        sandbox_clear_btn.clicked.connect(self._clear_sandbox)
        top.addWidget(sandbox_clear_btn)

        top.addStretch()

        self.filter_combo = QComboBox()
        self.filter_combo.addItem("全部来源", "all")
        self.filter_combo.addItem("仅沙箱", "sandbox")
        self.filter_combo.addItem("仅非沙箱", "other")
        self.filter_combo.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.filter_combo)

        # 过滤
        self.filter_label = QLabel("")
        self.filter_label.setStyleSheet("color: #888; font-size: 11px;")
        top.addWidget(self.filter_label)

        layout.addLayout(top)

        # 问题树
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["", "问题", "文件", "行", "来源"])
        self.tree.setColumnWidth(0, 30)
        self.tree.setColumnWidth(1, 350)
        self.tree.setColumnWidth(4, 110)
        self.tree.itemDoubleClicked.connect(self._on_jump)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.tree)

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
            QTreeWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                font-size: 12px;
                outline: none;
            }
            QTreeWidget::item {
                padding: 3px 6px;
            }
            QTreeWidget::item:hover { background-color: #2a2d2e; }
            QTreeWidget::item:selected { background-color: #094771; }
            QHeaderView::section {
                background-color: #252526;
                color: #888;
                border: none;
                border-bottom: 1px solid #3c3c3c;
                padding: 4px;
                font-size: 11px;
            }
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

    def _clear_sandbox(self):
        """清除所有沙箱来源诊断（v2.15）"""
        mw = self.main_window
        if mw is not None and hasattr(mw, "clear_sandbox_problems"):
            try:
                mw.clear_sandbox_problems()
            except Exception:
                pass
        self.refresh()

    def _filter_problems(self, problems):
        """按来源过滤（全部/沙箱/非沙箱/指定插件，v2.16）"""
        mode = "all"
        try:
            mode = self.filter_combo.currentData()
        except Exception:
            pass
        if mode == "sandbox":
            return [p for p in problems
                    if str(getattr(p, "source", "")).startswith("sandbox:")]
        if mode == "other":
            return [p for p in problems
                    if not str(getattr(p, "source", "")).startswith("sandbox:")]
        if isinstance(mode, str) and mode.startswith("plugin:"):
            want = mode[len("plugin:"):]
            return [p for p in problems
                    if str(getattr(p, "source", "")) == want]
        return problems

    def _sync_filter_options(self):
        """动态加入沙箱插件来源选项（保留当前选择，v2.16）"""
        try:
            cur = self.filter_combo.currentData()
        except Exception:
            cur = "all"
        sources = set()
        try:
            for probs in (self.pm.problems or {}).values():
                for prob in probs:
                    src = str(getattr(prob, "source", "") or "")
                    if src.startswith("sandbox:"):
                        sources.add(src)
        except Exception:
            pass
        try:
            existing = {self.filter_combo.itemData(i)
                        for i in range(self.filter_combo.count())}
        except Exception:
            existing = set()
        for src in sorted(sources):
            key = "plugin:" + src
            if key not in existing:
                self.filter_combo.addItem("插件: " + src, key)
        try:
            idx = self.filter_combo.findData(cur)
            if idx >= 0:
                self.filter_combo.setCurrentIndex(idx)
        except Exception:
            pass

    def refresh(self):
        """刷新显示"""
        self.tree.clear()
        self._sync_filter_options()

        # 按文件分组
        file_problems = self.pm.problems

        total = 0
        for filepath, problems in sorted(file_problems.items()):
            if not problems:
                continue

            problems = self._filter_problems(problems)
            if not problems:
                continue

            import os
            fname = os.path.basename(filepath)

            file_item = QTreeWidgetItem(self.tree)
            file_item.setText(1, "%s (%d)" % (fname, len(problems)))
            file_item.setData(0, Qt.UserRole, ('file', filepath))
            font = file_item.font(1)
            font.setBold(True)
            file_item.setFont(1, font)

            for prob in problems:
                child = QTreeWidgetItem(file_item)
                icon = SEVERITY_ICONS.get(prob.severity, "•")
                child.setText(0, icon)
                child.setForeground(0, QBrush(
                    SEVERITY_COLORS.get(prob.severity, QColor("#d4d4d4"))
                ))
                child.setText(1, prob.message)
                child.setText(2, fname)
                child.setText(3, str(prob.line + 1))
                child.setText(4, str(getattr(prob, "source", "") or ""))
                child.setData(0, Qt.UserRole, ('problem', prob))
                total += 1

            file_item.setExpanded(True)

        # 更新过滤标签
        counts = self.pm.count_by_severity()
        self.filter_label.setText(
            "✗ %d  ⚠ %d  ℹ %d  💡 %d" % (
                counts["error"], counts["warning"],
                counts["info"], counts["hint"]
            )
        )

    def _on_jump(self, item, column):
        """双击跳转"""
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        kind, value = data

        if kind == 'file':
            filepath = value
            if self.main_window:
                self.main_window.tabs.open_file(filepath)
        elif kind == 'problem':
            prob = value
            if self.main_window:
                proxy = self.main_window.tabs.open_file(prob.filepath)
                if proxy and hasattr(proxy, 'sc'):
                    try:
                        proxy.sc.setCursorPosition(prob.line, prob.col)
                        proxy.sc.ensureLineVisible(prob.line)
                        proxy.sc.setFocus()
                    except Exception:
                        pass

    def _show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return

        data = item.data(0, Qt.UserRole)
        if not data:
            return

        kind, value = data
        menu = QMenu(self)

        if kind == 'problem':
            jump_act = menu.addAction("➡ 跳转到问题")
            jump_act.triggered.connect(lambda: self._on_jump(item, 0))

            copy_act = menu.addAction("📋 复制错误信息")
            copy_act.triggered.connect(
                lambda: QApplication.clipboard().setText(value.message)
            )
        elif kind == 'file':
            copy_path = menu.addAction("📋 复制文件路径")
            copy_path.triggered.connect(
                lambda: QApplication.clipboard().setText(value)
            )

        menu.exec_(self.tree.viewport().mapToGlobal(pos))