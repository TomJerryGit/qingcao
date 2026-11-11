# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""搜索结果树（v2.25 从 global_search_panel 拆出）。"""

from ui.global_search_panel_common import *  # noqa: F401,F403


class SearchResultTree(QTreeWidget):
    """
    搜索结果树。

    显示搜索结果，支持:
    - 文件分组
    - 匹配项展开
    - 双击跳转
    - 右键菜单
    """

    # 信号
    match_activated = pyqtSignal(str, int, int, int, int)  # filepath, start, end, line, col
    file_activated = pyqtSignal(str, int)  # filepath, line

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setColumnCount(3)
        self.setHeaderLabels(["文件 / 匹配内容", "行", "列"])
        self.setIndentation(16)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setSortingEnabled(False)

        # 列宽
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)

        # 连接信号
        self.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # 样式
        self._apply_style()

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QTreeWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                font-size: 12px;
                outline: none;
            }
            QTreeWidget::item {
                padding: 3px 4px;
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
                color: #cccccc;
                border: none;
                border-bottom: 1px solid #3c3c3c;
                padding: 4px 6px;
                font-weight: bold;
            }
        """)

    def refresh_theme(self, theme):
        """主题变更时刷新样式

        ★ 真实桌面验证发现的缺陷：
            `SearchResultTree` 在 `_apply_style()` 里**写死深色**，
            但它没有 `refresh_theme` 方法，而主题刷新走的是
            `ThemeLoader.notify_widgets()` → 只调用**拥有
            `refresh_theme` 的控件**。于是：编辑器与其它面板都跟着
            主题变成浅色时，**"文件 / 匹配内容"这块结果树仍然是黑的**，
            像一块缺角。

            修复：与其它面板一致的实现 —— 首次保存原始 QSS，
            之后用 `adapt_qss_colors()` 按主题换算。
        """
        try:
            from infrastructure.theme_loader import adapt_qss_colors

            if not getattr(self, "_original_qss", ""):
                self._original_qss = self.styleSheet()
            if self._original_qss:
                self.setStyleSheet(adapt_qss_colors(self._original_qss, theme))
        except Exception as e:
            print(f"[SearchResultTree] refresh_theme 失败: {e}")

    # --------------------------------------------------------
    # 添加结果
    # --------------------------------------------------------
    def add_file_result(self, filepath: str, matches: List[SearchMatch]) -> QTreeWidgetItem:
        """
        添加文件结果。

        参数:
            filepath: 文件路径
            matches: 匹配列表

        返回:
            文件节点
        """
        # 文件节点
        file_item = QTreeWidgetItem(self)
        file_item.setData(0, Qt.UserRole + 1, NODE_TYPE_FILE)
        file_item.setData(0, Qt.UserRole + 2, filepath)

        # 显示相对路径（如果可能）
        display_name = os.path.basename(filepath)
        display_dir = os.path.dirname(filepath)

        if display_dir:
            display = f"{display_name}  —  {display_dir}"
        else:
            display = display_name

        file_item.setText(0, f"📄 {display}")
        file_item.setText(1, f"{len(matches)} 项")
        file_item.setToolTip(0, filepath)

        # 字体加粗
        font = file_item.font(0)
        font.setBold(True)
        file_item.setFont(0, font)

        # 添加匹配项
        for match in matches:
            match_item = QTreeWidgetItem(file_item)
            match_item.setData(0, Qt.UserRole + 1, NODE_TYPE_MATCH)
            match_item.setData(0, Qt.UserRole + 2, filepath)
            match_item.setData(0, Qt.UserRole + 3, match.start)
            match_item.setData(0, Qt.UserRole + 4, match.end)
            match_item.setData(0, Qt.UserRole + 5, match.line)
            match_item.setData(0, Qt.UserRole + 6, match.col)

            # 显示行内容（带高亮）
            line_text = match.line_text.strip()
            if len(line_text) > PREVIEW_CONTEXT_LENGTH:
                # 定位到匹配位置附近
                match_in_line = match.text
                if match_in_line and match_in_line in line_text:
                    idx = line_text.find(match_in_line)
                    start = max(0, idx - 30)
                    end = min(len(line_text), idx + len(match_in_line) + 30)
                    prefix = "..." if start > 0 else ""
                    suffix = "..." if end < len(line_text) else ""
                    line_text = prefix + line_text[start:end] + suffix

            match_item.setText(0, line_text)
            match_item.setText(1, str(match.line))
            match_item.setText(2, str(match.col))

            # 匹配文本加粗
            font = match_item.font(0)
            font.setBold(False)
            match_item.setFont(0, font)

            # 设置颜色
            match_item.setForeground(0, QBrush(QColor("#cccccc")))

        # 默认展开文件节点
        file_item.setExpanded(True)

        return file_item

    def add_file_result_batch(self, filepath: str, matches: List[SearchMatch]):
        """批量添加（性能优化，禁用更新）"""
        self.setUpdatesEnabled(False)
        try:
            self.add_file_result(filepath, matches)
        finally:
            self.setUpdatesEnabled(True)

    # --------------------------------------------------------
    # 清空
    # --------------------------------------------------------
    def clear_results(self):
        """清空所有结果"""
        self.clear()

    def get_file_count(self) -> int:
        """获取文件数量"""
        count = 0
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.data(0, Qt.UserRole + 1) == NODE_TYPE_FILE:
                count += 1
        return count

    def get_match_count(self) -> int:
        """获取匹配总数"""
        count = 0
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            for j in range(item.childCount()):
                count += 1
        return count

    def get_all_results(self) -> Dict[str, List[SearchMatch]]:
        """获取所有结果（文件路径 -> 匹配列表）"""
        results = {}

        for i in range(self.topLevelItemCount()):
            file_item = self.topLevelItem(i)
            filepath = file_item.data(0, Qt.UserRole + 2)
            if not filepath:
                continue

            matches = []
            for j in range(file_item.childCount()):
                match_item = file_item.child(j)
                try:
                    match = SearchMatch(
                        start=match_item.data(0, Qt.UserRole + 3),
                        end=match_item.data(0, Qt.UserRole + 4),
                        line=match_item.data(0, Qt.UserRole + 5),
                        col=match_item.data(0, Qt.UserRole + 6),
                        text="",
                        line_text=match_item.text(0),
                    )
                    matches.append(match)
                except Exception:
                    continue

            results[filepath] = matches

        return results

    # --------------------------------------------------------
    # 双击跳转
    # --------------------------------------------------------
    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """双击项"""
        node_type = item.data(0, Qt.UserRole + 1)

        if node_type == NODE_TYPE_MATCH:
            # 匹配项：跳转到具体位置
            filepath = item.data(0, Qt.UserRole + 2)
            start = item.data(0, Qt.UserRole + 3)
            end = item.data(0, Qt.UserRole + 4)
            line = item.data(0, Qt.UserRole + 5)
            col = item.data(0, Qt.UserRole + 6)

            if filepath:
                self.match_activated.emit(filepath, start, end, line, col)

        elif node_type == NODE_TYPE_FILE:
            # 文件节点：跳转到第一行
            filepath = item.data(0, Qt.UserRole + 2)
            if filepath:
                line = 0
                if item.childCount() > 0:
                    line = item.child(0).data(0, Qt.UserRole + 5)
                self.file_activated.emit(filepath, line)

    # --------------------------------------------------------
    # 右键菜单
    # --------------------------------------------------------
    def _show_context_menu(self, pos):
        """显示右键菜单"""
        item = self.itemAt(pos)
        if item is None:
            return

        menu = QMenu(self)
        node_type = item.data(0, Qt.UserRole + 1)

        if node_type == NODE_TYPE_MATCH:
            filepath = item.data(0, Qt.UserRole + 2)

            # 打开
            open_act = menu.addAction("📂 打开")
            open_act.triggered.connect(lambda: self._on_item_double_clicked(item, 0))

            menu.addSeparator()

            # 复制
            copy_line_act = menu.addAction("📋 复制此行内容")
            copy_line_act.triggered.connect(lambda: self._copy_to_clipboard(item.text(0)))

            if filepath:
                copy_path_act = menu.addAction("📋 复制文件路径")
                copy_path_act.triggered.connect(lambda: self._copy_to_clipboard(filepath))

                menu.addSeparator()

                # 在文件管理器中显示
                reveal_act = menu.addAction("📁 在文件管理器中显示")
                reveal_act.triggered.connect(lambda: self._reveal_in_explorer(filepath))

        elif node_type == NODE_TYPE_FILE:
            filepath = item.data(0, Qt.UserRole + 2)

            # 展开/折叠
            if item.isExpanded():
                collapse_act = menu.addAction("⊟ 折叠")
                collapse_act.triggered.connect(lambda: item.setExpanded(False))
            else:
                expand_act = menu.addAction("⊞ 展开")
                expand_act.triggered.connect(lambda: item.setExpanded(True))

            menu.addSeparator()

            # 复制路径
            if filepath:
                copy_path_act = menu.addAction("📋 复制文件路径")
                copy_path_act.triggered.connect(lambda: self._copy_to_clipboard(filepath))

                reveal_act = menu.addAction("📁 在文件管理器中显示")
                reveal_act.triggered.connect(lambda: self._reveal_in_explorer(filepath))

        menu.addSeparator()

        # 全部展开/折叠
        expand_all_act = menu.addAction("⊞ 全部展开")
        expand_all_act.triggered.connect(self.expandAll)

        collapse_all_act = menu.addAction("⊟ 全部折叠")
        collapse_all_act.triggered.connect(self.collapseAll)

        menu.addSeparator()

        # 清空
        clear_act = menu.addAction("🗑 清空结果")
        clear_act.triggered.connect(self.clear_results)

        menu.exec(self.viewport().mapToGlobal(pos))

    def _copy_to_clipboard(self, text: str):
        """复制到剪贴板"""
        try:
            QApplication.clipboard().setText(text)
        except Exception:
            pass

    def _reveal_in_explorer(self, filepath: str):
        """在文件管理器中显示"""
        import subprocess

        try:
            if sys.platform == "win32":
                # P1-B1: /select, 必须作为单个参数
                subprocess.Popen(["explorer", f"/select,{filepath.replace('/', chr(92))}"])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", filepath])
            else:
                folder = os.path.dirname(filepath)
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            print(f"[SearchResultTree] 打开失败: {e}")


# ============================================================
# 全局搜索面板
# ============================================================
