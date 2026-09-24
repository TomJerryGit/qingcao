#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为快捷键编辑器模块，包含：
- KeymapEditor：快捷键编辑器主对话框
- KeyCaptureDialog：按键捕获对话框
- KeymapTable：快捷键表格控件
- KeymapSearchBar：快捷键搜索栏
- KeymapProfile：快捷键方案（多套方案切换）
- 命令列表与分类
- 快捷键冲突检测
- 导入/导出快捷键
- 恢复默认
- 实时搜索过滤
- 分类折叠
"""

import os
import sys
import json
import time
from typing import Optional, List, Dict, Any, Tuple, Callable, Set
from dataclasses import dataclass, field
from enum import Enum, auto

from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QToolButton, QLabel, QComboBox, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QDialogButtonBox,
    QMessageBox, QFileDialog, QInputDialog, QMenu, QFrame,
    QSplitter, QTextEdit, QApplication, QStyle, QKeySequenceEdit
)
from PyQt5.QtGui import (
    QIcon,
    QColor,
    QFont,
    QKeySequence,
    QBrush,
    QPainter,
    QPen,
)
from PyQt5.QtWidgets import QAction
from PyQt5.QtCore import (
    Qt, pyqtSignal, QTimer, QSettings, QPoint, QSize
)

from app.actions import ActionManager
from app.event_bus import bus, StatusMessageEvent


# ============================================================
# 常量
# ============================================================
# 快捷键配置文件
KEYBINDINGS_FILE = "keybindings.json"
KEYMAP_DIR = "keymaps"

# 冲突颜色
CONFLICT_COLOR = QColor("#f14c4c")
DUPLICATE_COLOR = QColor("#f0ad4e")
NORMAL_COLOR = QColor("#d4d4d4")
RESERVED_COLOR = QColor("#888888")

# 保留快捷键（系统级）
RESERVED_SHORTCUTS = {
    "Ctrl+Alt+Delete",
    "Alt+F4",
    "Ctrl+Alt+F1",
    "Ctrl+Alt+F2",
}

# 分类显示名称映射
CATEGORY_DISPLAY_NAMES = {
    "文件": "文件",
    "编辑": "编辑",
    "视图": "视图",
    "搜索": "搜索",
    "工具": "工具",
    "宏": "宏",
    "帮助": "帮助",
    "插件": "插件",
    "其他": "其他",
    "File": "文件",
    "Edit": "编辑",
    "View": "视图",
    "Search": "搜索",
    "Tools": "工具",
    "Macro": "宏",
    "Help": "帮助",
    "Plugin": "插件",
    "Other": "其他",
}

# 分类排序优先级
CATEGORY_ORDER = [
    "文件", "编辑", "视图", "搜索",
    "工具", "宏", "插件", "帮助", "其他",
]


# ============================================================
# 快捷键记录
# ============================================================
@dataclass
class KeymapEntry:
    """快捷键记录"""
    name: str = ""              # 动作名称
    text: str = ""              # 显示文本
    category: str = "其他"      # 分类
    shortcut: str = ""          # 当前快捷键
    default: str = ""           # 默认快捷键
    description: str = ""       # 描述
    conflicts: List[str] = field(default_factory=list)  # 冲突的动作名

    @property
    def is_default(self) -> bool:
        """是否为默认值"""
        return self.shortcut == self.default

    @property
    def is_empty(self) -> bool:
        """是否为空快捷键"""
        return not self.shortcut

    @property
    def has_conflict(self) -> bool:
        """是否有冲突"""
        return len(self.conflicts) > 0

    def __repr__(self) -> str:
        return (f"<KeymapEntry {self.name} "
                f"'{self.shortcut}' (default: {self.default})>")


# ============================================================
# 快捷键方案
# ============================================================
@dataclass
class KeymapProfile:
    """快捷键方案"""
    name: str = "默认"
    description: str = ""
    shortcuts: Dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    author: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'description': self.description,
            'shortcuts': dict(self.shortcuts),
            'created_at': self.created_at,
            'author': self.author,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'KeymapProfile':
        return cls(
            name=d.get('name', '未命名'),
            description=d.get('description', ''),
            shortcuts=dict(d.get('shortcuts', {})),
            created_at=d.get('created_at', ''),
            author=d.get('author', ''),
        )

    def save(self, filepath: str) -> bool:
        """保存到文件"""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)) or '.',
                        exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[KeymapProfile] 保存失败: {e}")
            return False

    @classmethod
    def load(cls, filepath: str) -> Optional['KeymapProfile']:
        """从文件加载"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            print(f"[KeymapProfile] 加载失败: {e}")
            return None


# ============================================================
# 按键捕获对话框
# ============================================================
class KeyCaptureDialog(QDialog):
    """
    按键捕获对话框。

    用于捕获用户按下的快捷键。
    """

    def __init__(self, action_name: str = "",
                 current_shortcut: str = "",
                 parent=None):
        super().__init__(parent)

        self.action_name = action_name
        self.current_shortcut = current_shortcut
        self.captured_shortcut: str = ""

        self.setWindowTitle("捕获快捷键")
        self.setFixedSize(400, 220)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowStaysOnTopHint
        )

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 说明
        info = QLabel(
            f"为动作 <b>{self.action_name}</b> 设置快捷键"
        )
        info.setStyleSheet("font-size: 13px; color: #d4d4d4;")
        layout.addWidget(info)

        # 当前快捷键
        current_layout = QHBoxLayout()
        current_layout.addWidget(QLabel("当前:"))
        self.current_label = QLabel(self.current_shortcut or "（无）")
        self.current_label.setStyleSheet(
            "background-color: #2d2d2d; padding: 4px 8px; "
            "border-radius: 4px; color: #d4d4d4;"
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
        hint = QLabel(
            "提示：按下组合键，或按 Esc 取消，按 Delete 清除"
        )
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        layout.addStretch()

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
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
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt,
                    Qt.Key_Meta, Qt.Key_CapsLock):
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
            if text.isprintable() and text != ' ':
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
                category = CATEGORY_DISPLAY_NAMES.get(
                    entry.category, entry.category
                )
                categories.setdefault(category, []).append(entry)

            # 按优先级排序分类
            sorted_categories = sorted(
                categories.keys(),
                key=lambda c: (
                    CATEGORY_ORDER.index(c)
                    if c in CATEGORY_ORDER else 999
                )
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

    def _add_entry_item(self, parent: QTreeWidgetItem,
                          entry: KeymapEntry) -> QTreeWidgetItem:
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
                1,
                f"⚠ 与此快捷键冲突的动作:\n"
                + "\n".join(f"  • {c}" for c in entry.conflicts)
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
            action_name=entry.text or entry.name,
            current_shortcut=entry.shortcut,
            parent=self
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
        return sum(
            1 for e in self.get_all_entries() if e.has_conflict
        )

    def get_modified_count(self) -> int:
        """获取已修改数量"""
        return sum(
            1 for e in self.get_all_entries()
            if not e.is_default and e.shortcut
        )

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
class KeymapEditor(QDialog):
    """
    快捷键编辑器对话框。

    功能:
    - 显示所有命令及其快捷键
    - 双击编辑快捷键
    - 搜索过滤
    - 冲突检测
    - 恢复默认
    - 导入/导出
    - 多方案切换

    信号:
        keymap_changed(str, str): 快捷键变更（动作名, 新快捷键）
        keymap_reset(): 恢复默认
    """

    keymap_changed = pyqtSignal(str, str)
    keymap_reset = pyqtSignal()

    def __init__(self, action_manager: ActionManager, parent=None):
        """
        参数:
            action_manager: ActionManager 实例
            parent: 父窗口
        """
        super().__init__(parent)

        self.act_mgr = action_manager
        self._settings = QSettings("QingCao", "KeymapEditor")

        # 条目列表
        self._entries: List[KeymapEntry] = []

        # 冲突映射：shortcut -> [action_names]
        self._conflicts: Dict[str, List[str]] = {}

        # 构建 UI
        self.setWindowTitle("快捷键编辑器")
        self.resize(700, 600)

        self._build_ui()

        # 加载
        QTimer.singleShot(0, self._load_entries)

    # --------------------------------------------------------
    # UI 构建
    # --------------------------------------------------------
    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ========== 顶部工具栏 ==========
        top_bar = self._build_top_bar()
        layout.addWidget(top_bar)

        # ========== 表格 ==========
        self.table = KeymapTable()
        self.table.shortcut_changed.connect(self._on_shortcut_changed)
        layout.addWidget(self.table, 1)

        # ========== 状态栏 ==========
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            "color: #888; font-size: 11px; padding: 4px;"
        )
        layout.addWidget(self.status_label)

        # ========== 底部按钮 ==========
        bottom_bar = self._build_bottom_bar()
        layout.addWidget(bottom_bar)

        # 应用样式
        self._apply_style()

    def _build_top_bar(self) -> QWidget:
        """构建顶部工具栏"""
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索命令或快捷键...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_edit, 1)

        # 只看冲突
        self.conflict_only_cb = QCheckBox("只看冲突")
        self.conflict_only_cb.toggled.connect(self._on_conflict_filter)
        layout.addWidget(self.conflict_only_cb)

        # 只看已修改
        self.modified_only_cb = QCheckBox("只看已修改")
        self.modified_only_cb.toggled.connect(self._on_modified_filter)
        layout.addWidget(self.modified_only_cb)

        return bar

    def _build_bottom_bar(self) -> QWidget:
        """构建底部按钮栏"""
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 恢复默认
        self.reset_btn = QPushButton("↺ 恢复默认")
        self.reset_btn.clicked.connect(self._reset_to_defaults)
        layout.addWidget(self.reset_btn)

        # 导入
        self.import_btn = QPushButton("📥 导入")
        self.import_btn.clicked.connect(self._import_keymap)
        layout.addWidget(self.import_btn)

        # 导出
        self.export_btn = QPushButton("📤 导出")
        self.export_btn.clicked.connect(self._export_keymap)
        layout.addWidget(self.export_btn)

        layout.addStretch()

        # 保存
        self.save_btn = QPushButton("💾 保存")
        self.save_btn.setStyleSheet(
            "background-color: #7ec850; color: white;"
        )
        self.save_btn.clicked.connect(self._save_keymap)
        layout.addWidget(self.save_btn)

        # 关闭
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        layout.addWidget(self.close_btn)

        return bar

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #007acc;
            }
            QCheckBox {
                color: #d4d4d4;
                font-size: 12px;
                spacing: 4px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #555;
                border-radius: 2px;
                background-color: #3c3c3c;
            }
            QCheckBox::indicator:checked {
                background-color: #007acc;
                border-color: #007acc;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0a4d7a;
            }
        """)

    # --------------------------------------------------------
    # 加载条目
    # --------------------------------------------------------
    def _load_entries(self):
        """从 ActionManager 加载条目"""
        entries = []

        try:
            for name, action in self.act_mgr.actions.items():
                if not action.text():
                    continue

                entry = KeymapEntry(
                    name=name,
                    text=action.text(),
                    category=self.act_mgr.categories.get(name, "其他"),
                    shortcut=action.shortcut().toString(),
                    default=self.act_mgr.defaults.get(name, ""),
                    description=self.act_mgr.descriptions.get(name, ""),
                )
                entries.append(entry)

            # 排序
            entries.sort(key=lambda e: (e.category, e.text))

            self._entries = entries

            # 检测冲突
            self._detect_conflicts()

            # 加载到表格
            self.table.load_entries(entries)

            # 更新状态
            self._update_status()

        except Exception as e:
            print(f"[KeymapEditor] 加载失败: {e}")
            QMessageBox.warning(self, "加载失败", str(e))

    # --------------------------------------------------------
    # 冲突检测
    # --------------------------------------------------------
    def _detect_conflicts(self):
        """检测快捷键冲突"""
        # 构建映射：快捷键 -> [动作名]
        shortcut_map: Dict[str, List[str]] = {}

        for entry in self._entries:
            if not entry.shortcut:
                continue
            shortcut_map.setdefault(entry.shortcut, []).append(entry.name)

        # 记录冲突
        self._conflicts = {
            sc: names for sc, names in shortcut_map.items()
            if len(names) > 1
        }

        # 更新每个条目的冲突信息
        for entry in self._entries:
            if entry.shortcut in self._conflicts:
                entry.conflicts = [
                    n for n in self._conflicts[entry.shortcut]
                    if n != entry.name
                ]
            else:
                entry.conflicts = []

    # --------------------------------------------------------
    # 事件处理
    # --------------------------------------------------------
    def _on_shortcut_changed(self, action_name: str, new_shortcut: str):
        """快捷键变更"""
        # 更新 ActionManager
        if new_shortcut:
            try:
                self.act_mgr.set_shortcut(action_name, new_shortcut)
            except Exception:
                pass
        else:
            # 清除快捷键
            action = self.act_mgr.get(action_name)
            if action:
                action.setShortcut(QKeySequence())

        # 更新条目
        for entry in self._entries:
            if entry.name == action_name:
                entry.shortcut = new_shortcut
                break

        # 重新检测冲突
        self._detect_conflicts()

        # 刷新显示
        self.table.load_entries(self._entries)

        # 发射信号
        self.keymap_changed.emit(action_name, new_shortcut)

        # 更新状态
        self._update_status()

    def _on_search_changed(self, text: str):
        """搜索变化"""
        self.table.filter_entries(text)

    def _on_conflict_filter(self, checked: bool):
        """只看冲突"""
        if checked:
            # 过滤出冲突项
            self._filter_by_predicate(
                lambda e: e.has_conflict
            )
        else:
            self.table.filter_entries(self.search_edit.text())

    def _on_modified_filter(self, checked: bool):
        """只看已修改"""
        if checked:
            self._filter_by_predicate(
                lambda e: not e.is_default and e.shortcut
            )
        else:
            self.table.filter_entries(self.search_edit.text())

    def _filter_by_predicate(self, predicate: Callable[[KeymapEntry], bool]):
        """按条件过滤显示"""
        # 简单实现：直接重载表格
        filtered = [e for e in self._entries if predicate(e)]

        if not filtered:
            self.table.clear()
            empty_item = QTreeWidgetItem(self.table)
            empty_item.setText(0, "没有符合条件的项")
            empty_item.setForeground(0, QBrush(QColor("#888")))
            self.status_label.setText("0 项匹配")
            return

        self.table.load_entries(filtered)
        self.status_label.setText(f"{len(filtered)} 项匹配")

    def _update_status(self):
        """更新状态栏"""
        total = len(self._entries)
        conflicts = self.table.get_conflict_count()
        modified = self.table.get_modified_count()

        parts = [f"共 {total} 个命令"]

        if modified > 0:
            parts.append(f"{modified} 个已修改")

        if conflicts > 0:
            parts.append(f"⚠ {conflicts} 个冲突")

        self.status_label.setText(" · ".join(parts))

        # 冲突时变色
        if conflicts > 0:
            self.status_label.setStyleSheet(
                "color: #f14c4c; font-size: 11px; padding: 4px; "
                "font-weight: bold;"
            )
        else:
            self.status_label.setStyleSheet(
                "color: #888; font-size: 11px; padding: 4px;"
            )

    # --------------------------------------------------------
    # 恢复默认
    # --------------------------------------------------------
    def _reset_to_defaults(self):
        """恢复默认快捷键"""
        reply = QMessageBox.question(
            self, "确认恢复默认",
            "确定要将所有快捷键恢复为默认值吗？\n\n"
            "此操作会覆盖你的自定义快捷键。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            # 恢复每个动作
            for entry in self._entries:
                action = self.act_mgr.get(entry.name)
                if action:
                    if entry.default:
                        action.setShortcut(QKeySequence(entry.default))
                    else:
                        action.setShortcut(QKeySequence())

                    entry.shortcut = entry.default

            # 重新加载
            self.table.load_entries(self._entries)
            self._detect_conflicts()
            self.table.load_entries(self._entries)

            # 更新状态
            self._update_status()

            # 发射信号
            self.keymap_reset.emit()

            # 提示
            bus.emit_status("已恢复默认快捷键", 2000, "success")

        except Exception as e:
            QMessageBox.warning(self, "恢复失败", str(e))

    # --------------------------------------------------------
    # 导入/导出
    # --------------------------------------------------------
    def _import_keymap(self):
        """导入快捷键配置"""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "导入快捷键配置",
            "",
            "JSON 文件 (*.json);;所有文件 (*.*)"
        )

        if not filepath:
            return

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, dict):
                QMessageBox.warning(
                    self, "导入失败", "配置文件格式错误"
                )
                return

            # 确认
            reply = QMessageBox.question(
                self, "确认导入",
                f"将导入 {len(data)} 个快捷键配置。\n\n"
                f"是否覆盖当前设置？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply != QMessageBox.Yes:
                return

            # 应用
            applied = 0
            for name, shortcut in data.items():
                action = self.act_mgr.get(name)
                if action:
                    try:
                        action.setShortcut(QKeySequence(shortcut))
                        applied += 1
                    except Exception:
                        pass

            # 刷新
            self._load_entries()

            QMessageBox.information(
                self, "导入成功",
                f"已导入 {applied} 个快捷键配置。"
            )

        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))

    def _export_keymap(self):
        """导出快捷键配置"""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出快捷键配置",
            KEYBINDINGS_FILE,
            "JSON 文件 (*.json);;所有文件 (*.*)"
        )

        if not filepath:
            return

        try:
            # 收集所有非默认快捷键
            data = {}
            for entry in self._entries:
                if entry.shortcut and entry.shortcut != entry.default:
                    data[entry.name] = entry.shortcut

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False,
                          sort_keys=True)

            QMessageBox.information(
                self, "导出成功",
                f"已导出 {len(data)} 个自定义快捷键。"
            )

        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    # --------------------------------------------------------
    # 保存
    # --------------------------------------------------------
    def _save_keymap(self):
        """保存快捷键配置到文件"""
        try:
            # 保存
            success = self.act_mgr.save_custom(KEYBINDINGS_FILE)

            if success:
                bus.emit_status(
                    "快捷键配置已保存", 2000, "success"
                )
                QMessageBox.information(
                    self, "保存成功",
                    f"快捷键已保存到 {KEYBINDINGS_FILE}。\n\n"
                    f"重启编辑器后生效。"
                )
            else:
                QMessageBox.warning(
                    self, "保存失败", "无法写入配置文件"
                )

        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    # --------------------------------------------------------
    # 调试
    # --------------------------------------------------------
    def dump(self) -> str:
        """导出编辑器信息"""
        lines = ["KeymapEditor", "=" * 60]
        lines.append(f"命令总数: {len(self._entries)}")
        lines.append(f"冲突数: {len(self._conflicts)}")
        lines.append(f"已修改: {self.table.get_modified_count()}")

        if self._conflicts:
            lines.append("")
            lines.append("冲突列表:")
            for shortcut, names in self._conflicts.items():
                lines.append(f"  {shortcut}: {', '.join(names)}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<KeymapEditor entries={len(self._entries)} "
                f"conflicts={len(self._conflicts)}>")


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication, QMainWindow
    from app.actions import ActionManager, create_action

    app = QApplication(sys.argv)

    # 创建主窗口
    win = QMainWindow()
    win.setWindowTitle("KeymapEditor 测试")
    win.resize(900, 700)
    win.show()

    # 创建动作管理器
    mgr = ActionManager()

    def dummy():
        pass

    # 添加测试动作
    actions_data = [
        ("file.new", "新建文件", "Ctrl+N"),
        ("file.open", "打开文件", "Ctrl+O"),
        ("file.save", "保存文件", "Ctrl+S"),
        ("file.save_as", "另存为", "Ctrl+Shift+S"),
        ("file.close", "关闭", "Ctrl+W"),
        ("file.exit", "退出", "Ctrl+Q"),
        ("edit.undo", "撤销", "Ctrl+Z"),
        ("edit.redo", "重做", "Ctrl+Y"),
        ("edit.cut", "剪切", "Ctrl+X"),
        ("edit.copy", "复制", "Ctrl+C"),
        ("edit.paste", "粘贴", "Ctrl+V"),
        ("edit.find", "查找", "Ctrl+F"),
        ("edit.replace", "替换", "Ctrl+H"),
        ("edit.goto_line", "跳转到行", "Ctrl+G"),
        ("edit.toggle_comment", "注释切换", "Ctrl+/"),
        ("view.zoom_in", "放大", "Ctrl+="),
        ("view.zoom_out", "缩小", "Ctrl+-"),
        ("view.fullscreen", "全屏", "F11"),
        ("view.distraction_free", "无干扰模式", "Shift+F11"),
        ("tools.command_palette", "命令面板", "Ctrl+Shift+P"),
        ("tools.macro_record", "录制宏", "Ctrl+Shift+R"),
        ("tools.macro_play", "回放宏", "Ctrl+Shift+M"),
        ("help.about", "关于", "F1"),
    ]

    for name, text, shortcut in actions_data:
        create_action(win, name, text, shortcut, dummy, mgr)

    # 制造一个冲突
    create_action(win, "edit.duplicate", "复制行", "Ctrl+C", dummy, mgr)

    print(f"已注册 {len(mgr.actions)} 个动作")
    print()

    # 打开编辑器
    dlg = KeymapEditor(mgr)
    dlg.show()

    # 3 秒后打印信息
    from PyQt5.QtCore import QTimer

    def print_info():
        print("=== KeymapEditor 信息 ===")
        print(dlg.dump())
        print()

    QTimer.singleShot(3000, print_info)

    # 8 秒后退出
    QTimer.singleShot(8000, app.quit)

    sys.exit(app.exec())