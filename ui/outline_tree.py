# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""大纲树控件（v2.24 拆出）。"""

from ui.outline_common import *  # noqa: F401,F403,F405
from ui.outline_symbols import *  # noqa: F401,F403,F405


class OutlineTree(QTreeWidget):
    """
    符号树控件。

    展示符号层级结构，支持:
    - 双击跳转
    - 右键菜单

    注意:
        渲染逻辑（筛选、排序、图标、颜色）由 OutlinePanel 负责，
        本类只负责树控件本身的行为与信号。
    """

    # 信号
    symbol_activated = pyqtSignal(int)  # 跳转到行号

    def __init__(self, parent=None, enhanced: bool = False):
        super().__init__(parent)

        self._enhanced = bool(enhanced)

        # 配置
        self.setHeaderHidden(False)
        if self._enhanced:
            self.setColumnCount(3)
            self.setHeaderLabels(["符号", "行", "类型"])
        else:
            self.setColumnCount(2)
            self.setHeaderLabels(["符号", "行"])

        self.setIndentation(14)
        self.setAnimated(True)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setExpandsOnDoubleClick(False)

        # 列宽
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(COL_SYMBOL, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_LINE, QHeaderView.ResizeToContents)
        if self._enhanced:
            header.setSectionResizeMode(COL_TYPE, QHeaderView.ResizeToContents)

        # 应用样式
        self._apply_style()

        # 连接信号
        self.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QTreeWidget {
                background-color: #252526;
                color: #d4d4d4;
                border: none;
                font-size: 12px;
                outline: none;
            }
            QTreeWidget::item {
                padding: 2px 4px;
                border-radius: 2px;
            }
            QTreeWidget::item:hover {
                background-color: #2a2d2e;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #888;
                border: none;
                padding: 2px 4px;
                font-size: 11px;
            }
        """)

    # --------------------------------------------------------
    # 交互
    # --------------------------------------------------------
    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """双击跳转"""
        line = item.data(COL_SYMBOL, Qt.UserRole + 1)
        if line is not None:
            self.symbol_activated.emit(line)

    def _show_context_menu(self, pos: QPoint):
        """右键菜单"""
        item = self.itemAt(pos)
        if item is None:
            # 空白区域
            menu = QMenu(self)
            expand_all = menu.addAction("⊞ 全部展开")
            expand_all.triggered.connect(self.expandAll)

            collapse_all = menu.addAction("⊟ 全部折叠")
            collapse_all.triggered.connect(self.collapseAll)

            menu.exec_(self.viewport().mapToGlobal(pos))
            return

        menu = QMenu(self)

        # 跳转
        goto_act = menu.addAction("➡ 跳转到定义")
        goto_act.triggered.connect(lambda: self._on_item_double_clicked(item, 0))

        menu.addSeparator()

        # 复制符号名
        symbol = item.data(COL_SYMBOL, Qt.UserRole)
        if symbol:
            copy_name = menu.addAction("📋 复制符号名称")
            copy_name.triggered.connect(lambda: QApplication.clipboard().setText(symbol.name))

            copy_line = menu.addAction(f"📋 复制行号 ({symbol.line + 1})")
            copy_line.triggered.connect(
                lambda: QApplication.clipboard().setText(str(symbol.line + 1))
            )

        menu.addSeparator()

        # 展开/折叠
        if item.isExpanded():
            collapse_act = menu.addAction("⊟ 折叠")
            collapse_act.triggered.connect(lambda: item.setExpanded(False))
        else:
            expand_act = menu.addAction("⊞ 展开")
            expand_act.triggered.connect(lambda: item.setExpanded(True))

        menu.addSeparator()

        expand_all = menu.addAction("⊞ 全部展开")
        expand_all.triggered.connect(self.expandAll)

        collapse_all = menu.addAction("⊟ 全部折叠")
        collapse_all.triggered.connect(self.collapseAll)

        menu.exec_(self.viewport().mapToGlobal(pos))


# ============================================================
# 大纲面板（合并版）
# ============================================================
