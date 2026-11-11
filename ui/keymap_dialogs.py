# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""快捷键捕获/表格控件（v2.25 从 keymap_editor 拆出）。"""

from ui.keymap_editor_common import *  # noqa: F401,F403


class KeyCaptureDialog(QDialog):
    """
    按键捕获对话框。

    用于捕获用户按下的快捷键。
    """

    def __init__(self, action_name: str = "", current_shortcut: str = "", parent=None):
        super().__init__(parent)

        self.action_name = action_name
        self.current_shortcut = current_shortcut
        self.captured_shortcut: str = ""

        self.setWindowTitle("捕获快捷键")
        self.setFixedSize(400, 220)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 说明
        info = QLabel(f"为动作 <b>{self.action_name}</b> 设置快捷键")
        info.setStyleSheet("font-size: 13px; color: #d4d4d4;")
        layout.addWidget(info)

        # 当前快捷键
        current_layout = QHBoxLayout()
        current_layout.addWidget(QLabel("当前:"))
        self.current_label = QLabel(self.current_shortcut or "（无）")
        self.current_label.setStyleSheet(
            "background-color: #2d2d2d; padding: 4px 8px; border-radius: 4px; color: #d4d4d4;"
        )
        current_layout.addWidget(self.current_label, 1)
        layout.addLayout(current_layout)

        # 新快捷键
        new_layout = QHBoxLayout()
        new_layout.addWidget(QLabel("新快捷键:"))
        self.new_label = QLabel("请按下快捷键...")
        self.new_label.setStyleSheet(
            "background-color: #0e639c; padding: 4px 8px; "
            "border-radius: 4px; color: white; font-weight: bold;"
        )
        new_layout.addWidget(self.new_label, 1)
        layout.addLayout(new_layout)

        # 提示
        hint = QLabel("提示：按下组合键，或按 Esc 取消，按 Delete 清除")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        layout.addStretch()

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 聚焦
        self.setFocus()

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)

    def keyPressEvent(self, event):
        """按键事件"""
        key = event.key()
        modifiers = event.modifiers()

        # Esc 取消
        if key == Qt.Key_Escape and modifiers == Qt.NoModifier:
            self.reject()
            return

        # Delete 清除
        if key == Qt.Key_Delete and modifiers == Qt.NoModifier:
            self.captured_shortcut = ""
            self.new_label.setText("（无）")
            return

        # 忽略单独的修饰键
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_CapsLock):
            return

        # 构建快捷键字符串
        parts = []

        if modifiers & Qt.ControlModifier:
            parts.append("Ctrl")
        if modifiers & Qt.ShiftModifier:
            parts.append("Shift")
        if modifiers & Qt.AltModifier:
            parts.append("Alt")
        if modifiers & Qt.MetaModifier:
            parts.append("Meta")

        # 键名
        key_name = self._get_key_name(key)
        if key_name:
            parts.append(key_name)

        if parts:
            shortcut = "+".join(parts)
            self.captured_shortcut = shortcut
            self.new_label.setText(shortcut)
            self.new_label.setStyleSheet(
                "background-color: #7ec850; padding: 4px 8px; "
                "border-radius: 4px; color: white; font-weight: bold;"
            )

        event.accept()

    @staticmethod
    def _get_key_name(key: int) -> str:
        """获取键名"""
        # 特殊键映射
        special_map = {
            Qt.Key_Space: "Space",
            Qt.Key_Tab: "Tab",
            Qt.Key_Backspace: "Backspace",
            Qt.Key_Return: "Return",
            Qt.Key_Enter: "Enter",
            Qt.Key_Insert: "Insert",
            Qt.Key_Delete: "Delete",
            Qt.Key_Home: "Home",
            Qt.Key_End: "End",
            Qt.Key_PageUp: "PageUp",
            Qt.Key_PageDown: "PageDown",
            Qt.Key_Up: "Up",
            Qt.Key_Down: "Down",
            Qt.Key_Left: "Left",
            Qt.Key_Right: "Right",
            Qt.Key_F1: "F1",
            Qt.Key_F2: "F2",
            Qt.Key_F3: "F3",
            Qt.Key_F4: "F4",
            Qt.Key_F5: "F5",
            Qt.Key_F6: "F6",
            Qt.Key_F7: "F7",
            Qt.Key_F8: "F8",
            Qt.Key_F9: "F9",
            Qt.Key_F10: "F10",
            Qt.Key_F11: "F11",
            Qt.Key_F12: "F12",
        }

        if key in special_map:
            return special_map[key]

        # 普通字符键
        if Qt.Key_A <= key <= Qt.Key_Z:
            return chr(key)
        if Qt.Key_0 <= key <= Qt.Key_9:
            return chr(key)

        # 符号键
        try:
            text = chr(key)
            if text.isprintable() and text != " ":
                return text.upper()
        except Exception:
            pass

        return ""

    def get_shortcut(self) -> str:
        """获取捕获的快捷键"""
        return self.captured_shortcut


# ============================================================
# 快捷键表格控件
# ============================================================
class KeymapTable(QTreeWidget):
    """
    快捷键表格控件。

    使用 QTreeWidget 实现分类折叠的表格。
    """

    shortcut_changed = pyqtSignal(str, str)  # action_name, new_shortcut

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setColumnCount(3)
        self.setHeaderLabels(["命令", "快捷键", "默认"])
        self.setIndentation(16)
        self.setAlternatingRowColors(True)
        self.setRootIsDecorated(True)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setSortingEnabled(False)

        # 列宽
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)

        # 双击编辑
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

        # 应用样式
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
                padding: 4px 6px;
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
                padding: 6px 8px;
                font-weight: bold;
            }
        """)

    # --------------------------------------------------------
    # 加载
    # --------------------------------------------------------
    def load_entries(self, entries: List[KeymapEntry]):
        """
        加载快捷键条目。

        参数:
            entries: KeymapEntry 列表
        """
        self.setUpdatesEnabled(False)
        try:
            self.clear()

            # 按分类分组
            categories: Dict[str, List[KeymapEntry]] = {}
            for entry in entries:
                category = CATEGORY_DISPLAY_NAMES.get(entry.category, entry.category)
                categories.setdefault(category, []).append(entry)

            # 按优先级排序分类
            sorted_categories = sorted(
                categories.keys(),
                key=lambda c: CATEGORY_ORDER.index(c) if c in CATEGORY_ORDER else 999,
            )

            # 添加分类节点
            for category in sorted_categories:
                cat_entries = categories[category]

                cat_item = QTreeWidgetItem(self)
                cat_item.setText(0, f"▼ {category}")
                cat_item.setData(0, Qt.UserRole, None)  # 分类节点

                # 加粗
                font = cat_item.font(0)
                font.setBold(True)
                cat_item.setFont(0, font)
                cat_item.setForeground(0, QBrush(QColor("#7ec850")))

                # 添加子项
                for entry in cat_entries:
                    self._add_entry_item(cat_item, entry)

                cat_item.setExpanded(True)

        finally:
            self.setUpdatesEnabled(True)

    def _add_entry_item(self, parent: QTreeWidgetItem, entry: KeymapEntry) -> QTreeWidgetItem:
        """添加条目到分类下"""
        item = QTreeWidgetItem(parent)
        item.setData(0, Qt.UserRole, entry)
        item.setData(0, Qt.UserRole + 1, entry.name)

        # 命令文本
        item.setText(0, entry.text or entry.name)
        item.setToolTip(0, entry.description or entry.text)

        # 快捷键
        if entry.shortcut:
            item.setText(1, entry.shortcut)
        else:
            item.setText(1, "（未绑定）")
            item.setForeground(1, QBrush(QColor("#666")))

        # 默认快捷键
        if entry.default:
            item.setText(2, entry.default)
            item.setForeground(2, QBrush(QColor("#888")))
        else:
            item.setText(2, "—")

        # 颜色标识
        if entry.has_conflict:
            # 冲突：红色
            item.setForeground(1, QBrush(CONFLICT_COLOR))
            item.setToolTip(
                1, "⚠ 与此快捷键冲突的动作:\n" + "\n".join(f"  • {c}" for c in entry.conflicts)
            )
        elif not entry.is_default and entry.shortcut:
            # 自定义：橙色
            item.setForeground(1, QBrush(DUPLICATE_COLOR))
        elif entry.shortcut in RESERVED_SHORTCUTS:
            # 保留：灰色
            item.setForeground(1, QBrush(RESERVED_COLOR))

        return item

    # --------------------------------------------------------
    # 双击编辑
    # --------------------------------------------------------
    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """双击项"""
        entry = item.data(0, Qt.UserRole)
        if not isinstance(entry, KeymapEntry):
            # 分类节点
            item.setExpanded(not item.isExpanded())
            return

        # 仅快捷键列可编辑
        if column != 1:
            return

        self._edit_shortcut(item, entry)

    def _edit_shortcut(self, item: QTreeWidgetItem, entry: KeymapEntry):
        """编辑快捷键"""
        dlg = KeyCaptureDialog(
            action_name=entry.text or entry.name, current_shortcut=entry.shortcut, parent=self
        )

        if dlg.exec() == QDialog.Accepted:
            new_shortcut = dlg.get_shortcut()

            if new_shortcut != entry.shortcut:
                entry.shortcut = new_shortcut
                self._update_item(item, entry)
                self.shortcut_changed.emit(entry.name, new_shortcut)

    def _update_item(self, item: QTreeWidgetItem, entry: KeymapEntry):
        """更新条目显示"""
        # 快捷键
        if entry.shortcut:
            item.setText(1, entry.shortcut)
        else:
            item.setText(1, "（未绑定）")
            item.setForeground(1, QBrush(QColor("#666")))
            return

        # 颜色
        if entry.has_conflict:
            item.setForeground(1, QBrush(CONFLICT_COLOR))
        elif not entry.is_default:
            item.setForeground(1, QBrush(DUPLICATE_COLOR))
        elif entry.shortcut in RESERVED_SHORTCUTS:
            item.setForeground(1, QBrush(RESERVED_COLOR))
        else:
            item.setForeground(1, QBrush(NORMAL_COLOR))

    # --------------------------------------------------------
    # 查询
    # --------------------------------------------------------
    def get_all_entries(self) -> List[KeymapEntry]:
        """获取所有条目"""
        entries = []

        def _collect(item):
            entry = item.data(0, Qt.UserRole)
            if isinstance(entry, KeymapEntry):
                entries.append(entry)
            for i in range(item.childCount()):
                _collect(item.child(i))

        for i in range(self.topLevelItemCount()):
            _collect(self.topLevelItem(i))

        return entries

    def get_conflict_count(self) -> int:
        """获取冲突数量"""
        return sum(1 for e in self.get_all_entries() if e.has_conflict)

    def get_modified_count(self) -> int:
        """获取已修改数量"""
        return sum(1 for e in self.get_all_entries() if not e.is_default and e.shortcut)

    def filter_entries(self, text: str):
        """
        过滤条目。

        参数:
            text: 过滤文本
        """
        text = text.strip().lower()

        def _filter_item(item) -> bool:
            """返回 True 表示匹配或子孙匹配"""
            entry = item.data(0, Qt.UserRole)
            self_match = False

            if isinstance(entry, KeymapEntry):
                self_match = (
                    text in (entry.text or "").lower()
                    or text in entry.name.lower()
                    or text in entry.shortcut.lower()
                    or text in entry.description.lower()
                )

            # 检查子项
            any_child_match = False
            for i in range(item.childCount()):
                child = item.child(i)
                if _filter_item(child):
                    any_child_match = True

            visible = self_match or any_child_match
            item.setHidden(not visible)

            # 有匹配的子项则展开
            if any_child_match:
                item.setExpanded(True)

            return visible

        if not text:
            # 显示所有
            for i in range(self.topLevelItemCount()):
                item = self.topLevelItem(i)
                self._show_all_recursive(item)
        else:
            for i in range(self.topLevelItemCount()):
                item = self.topLevelItem(i)
                _filter_item(item)

    def _show_all_recursive(self, item):
        """递归显示所有"""
        item.setHidden(False)
        for i in range(item.childCount()):
            self._show_all_recursive(item.child(i))


# ============================================================
# 快捷键编辑器对话框
# ============================================================
