#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为宏编辑器模块，包含：
- MacroEditor：宏编辑器主对话框
- MacroListPanel：宏列表面板
- MacroCommandPanel：宏命令列表
- MacroCommandDetail：命令详情查看器
- MacroPlayer：宏回放器
- CommandEditDialog：命令编辑对话框
- ShortcutBindDialog：快捷键绑定对话框
- MacroImportDialog：宏导入对话框
- 宏列表展示与管理
- 命令序列查看与编辑
- 命令参数修改
- 命令重排序
- 命令删除
- 宏保存/加载/删除
- 宏导出/导入（JSON 格式）
- 宏回放（单次/多次）
- 宏快捷键绑定
- 宏搜索过滤
- 宏重命名
- 命令合并优化
- 统计信息
"""

import os
import sys
import json
import time
import copy
import datetime
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum, auto

from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QToolButton, QLineEdit, QListWidget,
    QListWidgetItem, QTreeWidget, QTreeWidgetItem, QSplitter,
    QTextEdit, QPlainTextEdit, QMessageBox, QFileDialog,
    QInputDialog, QMenu, QFrame, QCheckBox, QSpinBox,
    QComboBox, QGroupBox, QFormLayout, QDialogButtonBox,
    QAbstractItemView, QHeaderView, QScrollArea, QStackedWidget,
    QApplication, QStyle, QTableWidget, QTableWidgetItem
)
from PyQt5.QtGui import (
    QIcon,
    QColor,
    QFont,
    QKeySequence,
    QBrush,
    QPainter,
    QPen,
    QFontMetrics,
)
from PyQt5.QtWidgets import QAction
from PyQt5.QtCore import (
    Qt, pyqtSignal, QTimer, QSettings, QPoint, QSize, QDateTime
)

from core.commands import (
    Command, InsertCmd, DeleteCmd, ReplaceCmd, GroupCmd,
    CompoundCmd, CommandFactory, CommandSerializer,
    CMD_TYPE_INSERT, CMD_TYPE_DELETE, CMD_TYPE_REPLACE,
    CMD_TYPE_GROUP, CMD_TYPE_COMPOUND
)
from core.macro import (
    Macro, MacroCommand, MacroRecorder, MacroManager,
    MACRO_FILE_EXT, MACROS_DIR
)
from app.event_bus import (
    bus, StatusMessageEvent, NotificationEvent,
    MacroStartedEvent, MacroStoppedEvent, MacroReplayedEvent
)


# ============================================================
# 常量
# ============================================================
# 命令类型显示名称
COMMAND_TYPE_NAMES = {
    CMD_TYPE_INSERT: "插入",
    CMD_TYPE_DELETE: "删除",
    CMD_TYPE_REPLACE: "替换",
    CMD_TYPE_GROUP: "命令组",
    CMD_TYPE_COMPOUND: "复合命令",
}

# 命令类型颜色
COMMAND_TYPE_COLORS = {
    CMD_TYPE_INSERT: QColor("#7ec850"),    # 绿
    CMD_TYPE_DELETE: QColor("#f14c4c"),    # 红
    CMD_TYPE_REPLACE: QColor("#4dabf7"),   # 蓝
    CMD_TYPE_GROUP: QColor("#f0ad4e"),     # 橙
    CMD_TYPE_COMPOUND: QColor("#c586c0"),  # 紫
}

# 命令类型图标
COMMAND_TYPE_ICONS = {
    CMD_TYPE_INSERT: "➕",
    CMD_TYPE_DELETE: "➖",
    CMD_TYPE_REPLACE: "🔄",
    CMD_TYPE_GROUP: "📦",
    CMD_TYPE_COMPOUND: "🔗",
}


# ============================================================
# 宏列表面板
# ============================================================
class MacroListPanel(QWidget):
    """
    宏列表面板。

    展示所有已保存的宏，支持:
    - 宏列表显示
    - 搜索过滤
    - 新建/删除/重命名
    - 双击选中
    """

    macro_selected = pyqtSignal(object)    # Macro 对象
    macro_double_clicked = pyqtSignal(object)
    new_macro_requested = pyqtSignal()
    delete_macro_requested = pyqtSignal(object)
    rename_macro_requested = pyqtSignal(object)
    duplicate_macro_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._macros: List[Macro] = []
        self._filtered: List[Macro] = []

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 工具栏
        toolbar = QWidget()
        toolbar.setStyleSheet(
            "background-color: #2d2d2d; "
            "border-bottom: 1px solid #3c3c3c;"
        )
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(6, 4, 6, 4)
        toolbar_layout.setSpacing(4)

        # 新建按钮
        self.new_btn = QToolButton()
        self.new_btn.setText("➕")
        self.new_btn.setToolTip("新建宏")
        self.new_btn.setFixedSize(24, 24)
        self.new_btn.clicked.connect(self.new_macro_requested.emit)
        toolbar_layout.addWidget(self.new_btn)

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索宏...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_search_changed)
        toolbar_layout.addWidget(self.search_edit, 1)

        layout.addWidget(toolbar)

        # 列表
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("macro_list")
        self.list_widget.setFrameShape(QFrame.NoFrame)
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        self.list_widget.itemDoubleClicked.connect(self._on_double_clicked)
        self.list_widget.customContextMenuRequested.connect(
            self._show_context_menu
        )
        layout.addWidget(self.list_widget, 1)

        # 状态栏
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            "background-color: #2d2d2d; color: #888; "
            "font-size: 11px; padding: 4px 8px; "
            "border-top: 1px solid #3c3c3c;"
        )
        self.status_label.setFixedHeight(22)
        layout.addWidget(self.status_label)

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QListWidget#macro_list {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                font-size: 12px;
                outline: none;
                padding: 4px;
            }
            QListWidget#macro_list::item {
                padding: 6px 8px;
                border-radius: 3px;
                margin: 1px 2px;
            }
            QListWidget#macro_list::item:hover {
                background-color: #2a2d2e;
            }
            QListWidget#macro_list::item:selected {
                background-color: #094771;
                color: white;
            }
            QToolButton {
                background-color: transparent;
                color: #d4d4d4;
                border: none;
                border-radius: 3px;
                font-size: 14px;
                font-weight: bold;
            }
            QToolButton:hover {
                background-color: #3c3c3c;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #007acc;
            }
        """)

    # --------------------------------------------------------
    # 加载
    # --------------------------------------------------------
    def load_macros(self, macros: List[Macro]):
        """加载宏列表"""
        self._macros = list(macros)
        self._apply_filter()

    def _apply_filter(self):
        """应用过滤"""
        text = self.search_edit.text().strip().lower()

        self.list_widget.clear()
        self._filtered = []

        for macro in self._macros:
            if text:
                searchable = (
                    f"{macro.name} {macro.description} "
                    f"{' '.join(macro.tags)}"
                ).lower()
                if text not in searchable:
                    continue

            self._filtered.append(macro)
            item = self._create_macro_item(macro)
            self.list_widget.addItem(item)

        # 更新状态
        self.status_label.setText(
            f"{len(self._filtered)} / {len(self._macros)} 个宏"
        )

    def _create_macro_item(self, macro: Macro) -> QListWidgetItem:
        """创建宏列表项"""
        item = QListWidgetItem()

        # 名称 + 快捷键
        display = macro.name
        if macro.shortcut:
            display += f"  [{macro.shortcut}]"

        item.setText(display)

        # 提示
        tooltip_parts = [
            f"名称: {macro.name}",
            f"命令数: {macro.command_count}",
        ]
        if macro.description:
            tooltip_parts.append(f"描述: {macro.description}")
        if macro.author:
            tooltip_parts.append(f"作者: {macro.author}")
        if macro.shortcut:
            tooltip_parts.append(f"快捷键: {macro.shortcut}")
        if macro.updated_at:
            tooltip_parts.append(f"更新: {macro.updated_at[:19]}")

        item.setToolTip("\n".join(tooltip_parts))

        # 数据
        item.setData(Qt.UserRole, macro)

        # 空宏灰色显示
        if macro.is_empty:
            item.setForeground(QBrush(QColor("#666")))
        elif macro.shortcut:
            item.setForeground(QBrush(QColor("#7ec850")))

        return item

    def _on_search_changed(self, text: str):
        """搜索变化"""
        self._apply_filter()

    # --------------------------------------------------------
    # 交互
    # --------------------------------------------------------
    def _on_selection_changed(self):
        """选中变化"""
        item = self.list_widget.currentItem()
        if item:
            macro = item.data(Qt.UserRole)
            if macro:
                self.macro_selected.emit(macro)

    def _on_double_clicked(self, item: QListWidgetItem):
        """双击"""
        macro = item.data(Qt.UserRole)
        if macro:
            self.macro_double_clicked.emit(macro)

    def _show_context_menu(self, pos: QPoint):
        """右键菜单"""
        item = self.list_widget.itemAt(pos)

        menu = QMenu(self)

        # 新建
        new_act = menu.addAction("➕ 新建宏")
        new_act.triggered.connect(self.new_macro_requested.emit)

        if item:
            macro = item.data(Qt.UserRole)

            menu.addSeparator()

            # 重命名
            rename_act = menu.addAction("✏ 重命名")
            rename_act.triggered.connect(
                lambda: self.rename_macro_requested.emit(macro)
            )

            # 复制
            duplicate_act = menu.addAction("📋 创建副本")
            duplicate_act.triggered.connect(
                lambda: self.duplicate_macro_requested.emit(macro)
            )

            menu.addSeparator()

            # 删除
            delete_act = menu.addAction("🗑 删除")
            delete_act.triggered.connect(
                lambda: self.delete_macro_requested.emit(macro)
            )

        menu.exec(self.list_widget.mapToGlobal(pos))

    # --------------------------------------------------------
    # 查询
    # --------------------------------------------------------
    def get_selected_macro(self) -> Optional[Macro]:
        """获取选中的宏"""
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return None

    def select_macro(self, macro: Macro):
        """选中指定宏"""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.UserRole) is macro:
                self.list_widget.setCurrentItem(item)
                break

    def clear_selection(self):
        """清空选中"""
        self.list_widget.clearSelection()


# ============================================================
# 命令编辑对话框
# ============================================================
class CommandEditDialog(QDialog):
    """
    命令编辑对话框。

    编辑单个命令的参数。
    """

    def __init__(self, command: Command, parent=None):
        super().__init__(parent)

        self.command = command
        self.setWindowTitle("编辑命令")
        self.resize(500, 350)

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 命令类型
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("类型:"))

        cmd_type = self.command.command_type
        type_name = COMMAND_TYPE_NAMES.get(cmd_type, cmd_type)
        type_label = QLabel(type_name)
        type_label.setStyleSheet(
            f"color: {COMMAND_TYPE_COLORS.get(cmd_type, QColor('#d4d4d4')).name()};"
            f"font-weight: bold; font-size: 13px;"
        )
        type_layout.addWidget(type_label)
        type_layout.addStretch()
        layout.addLayout(type_layout)

        # 分隔
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #3c3c3c;")
        layout.addWidget(line)

        # 表单
        form = QFormLayout()

        if isinstance(self.command, InsertCmd):
            self._build_insert_form(form)
        elif isinstance(self.command, DeleteCmd):
            self._build_delete_form(form)
        elif isinstance(self.command, ReplaceCmd):
            self._build_replace_form(form)
        elif isinstance(self.command, GroupCmd):
            self._build_group_form(form)
        else:
            form.addRow(QLabel("此命令类型不支持编辑"))

        layout.addLayout(form)

        layout.addStretch()

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_insert_form(self, form: QFormLayout):
        """构建插入命令表单"""
        # 位置
        self.pos_spin = QSpinBox()
        self.pos_spin.setRange(0, 999999999)
        self.pos_spin.setValue(self.command.pos)
        form.addRow("位置:", self.pos_spin)

        # 文本
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlainText(self.command.text)
        self.text_edit.setMaximumHeight(150)
        form.addRow("文本:", self.text_edit)

    def _build_delete_form(self, form: QFormLayout):
        """构建删除命令表单"""
        # 位置
        self.pos_spin = QSpinBox()
        self.pos_spin.setRange(0, 999999999)
        self.pos_spin.setValue(self.command.pos)
        form.addRow("位置:", self.pos_spin)

        # 长度
        self.length_spin = QSpinBox()
        self.length_spin.setRange(0, 999999999)
        self.length_spin.setValue(self.command.length)
        form.addRow("长度:", self.length_spin)

        # 被删除内容（只读）
        try:
            deleted_text = self.command.deleted_text.decode(
                'utf-8', errors='replace'
            )
        except Exception:
            deleted_text = ""

        deleted_edit = QPlainTextEdit()
        deleted_edit.setPlainText(deleted_text)
        deleted_edit.setReadOnly(True)
        deleted_edit.setMaximumHeight(100)
        form.addRow("已删除内容:", deleted_edit)

    def _build_replace_form(self, form: QFormLayout):
        """构建替换命令表单"""
        # 位置
        self.pos_spin = QSpinBox()
        self.pos_spin.setRange(0, 999999999)
        self.pos_spin.setValue(self.command.pos)
        form.addRow("位置:", self.pos_spin)

        # 长度
        self.length_spin = QSpinBox()
        self.length_spin.setRange(0, 999999999)
        self.length_spin.setValue(self.command.length)
        form.addRow("长度:", self.length_spin)

        # 原文
        self.old_edit = QPlainTextEdit()
        self.old_edit.setPlainText(self.command.old_text)
        self.old_edit.setMaximumHeight(80)
        form.addRow("原文本:", self.old_edit)

        # 新文
        self.new_edit = QPlainTextEdit()
        self.new_edit.setPlainText(self.command.new_text)
        self.new_edit.setMaximumHeight(80)
        form.addRow("新文本:", self.new_edit)

    def _build_group_form(self, form: QFormLayout):
        """构建命令组表单"""
        # 描述
        count_label = QLabel(f"包含 {len(self.command.cmds)} 条子命令")
        count_label.setStyleSheet("color: #888;")
        form.addRow("结构:", count_label)

        # 子命令列表（只读）
        sub_list = QTextEdit()
        sub_list.setReadOnly(True)
        sub_list.setMaximumHeight(180)

        lines = []
        for i, cmd in enumerate(self.command.cmds):
            cmd_type = cmd.command_type
            type_name = COMMAND_TYPE_NAMES.get(cmd_type, cmd_type)
            desc = (cmd.describe() if hasattr(cmd, 'describe')
                    else str(cmd))
            lines.append(f"{i + 1}. [{type_name}] {desc}")

        sub_list.setPlainText("\n".join(lines))
        form.addRow("子命令:", sub_list)

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QLabel {
                color: #d4d4d4;
                font-size: 12px;
            }
            QSpinBox, QPlainTextEdit, QTextEdit {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px;
                font-size: 12px;
            }
            QSpinBox:focus, QPlainTextEdit:focus, QTextEdit:focus {
                border-color: #007acc;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 16px;
                font-size: 12px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)

    def get_command(self) -> Optional[Command]:
        """获取编辑后的命令"""
        try:
            if isinstance(self.command, InsertCmd):
                return InsertCmd(
                    self.pos_spin.value(),
                    self.text_edit.toPlainText()
                )

            elif isinstance(self.command, DeleteCmd):
                return DeleteCmd(
                    self.pos_spin.value(),
                    self.length_spin.value(),
                    self.command.deleted_text
                )

            elif isinstance(self.command, ReplaceCmd):
                return ReplaceCmd(
                    self.pos_spin.value(),
                    self.length_spin.value(),
                    self.old_edit.toPlainText(),
                    self.new_edit.toPlainText()
                )

            elif isinstance(self.command, GroupCmd):
                return self.command

            return self.command

        except Exception as e:
            print(f"[CommandEditDialog] 应用失败: {e}")
            return self.command


# ============================================================
# 快捷键绑定对话框
# ============================================================
class ShortcutBindDialog(QDialog):
    """快捷键绑定对话框"""

    def __init__(self, macro_name: str, current_shortcut: str = "",
                 parent=None):
        super().__init__(parent)

        self.macro_name = macro_name
        self.current_shortcut = current_shortcut
        self.shortcut: str = current_shortcut

        self.setWindowTitle("绑定快捷键")
        self.setFixedSize(400, 200)

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 说明
        info = QLabel(f"为宏 <b>{self.macro_name}</b> 绑定快捷键")
        info.setStyleSheet("font-size: 13px; color: #d4d4d4;")
        layout.addWidget(info)

        # 当前
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
        hint = QLabel("按 Esc 取消，按 Delete 清除")
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

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QLabel {
                color: #d4d4d4;
                font-size: 12px;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)

    def keyPressEvent(self, event):
        """按键事件"""
        key = event.key()
        modifiers = event.modifiers()

        if key == Qt.Key_Escape and modifiers == Qt.NoModifier:
            self.reject()
            return

        if key == Qt.Key_Delete and modifiers == Qt.NoModifier:
            self.shortcut = ""
            self.new_label.setText("（无）")
            return

        # 忽略单独的修饰键
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return

        # 构建快捷键
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
            self.shortcut = "+".join(parts)
            self.new_label.setText(self.shortcut)
            self.new_label.setStyleSheet(
                "background-color: #7ec850; padding: 4px 8px; "
                "border-radius: 4px; color: white; font-weight: bold;"
            )

        event.accept()

    @staticmethod
    def _get_key_name(key: int) -> str:
        """获取键名"""
        special = {
            Qt.Key_Space: "Space",
            Qt.Key_Tab: "Tab",
            Qt.Key_Return: "Return",
            Qt.Key_Enter: "Enter",
            Qt.Key_Home: "Home",
            Qt.Key_End: "End",
            Qt.Key_PageUp: "PageUp",
            Qt.Key_PageDown: "PageDown",
            Qt.Key_Up: "Up",
            Qt.Key_Down: "Down",
            Qt.Key_Left: "Left",
            Qt.Key_Right: "Right",
            Qt.Key_Insert: "Insert",
            Qt.Key_Delete: "Delete",
            Qt.Key_Backspace: "Backspace",
        }

        if key in special:
            return special[key]

        if Qt.Key_F1 <= key <= Qt.Key_F12:
            return f"F{key - Qt.Key_F1 + 1}"

        if Qt.Key_A <= key <= Qt.Key_Z:
            return chr(key)
        if Qt.Key_0 <= key <= Qt.Key_9:
            return chr(key)

        try:
            text = chr(key)
            if text.isprintable() and text != ' ':
                return text.upper()
        except Exception:
            pass

        return ""


# ============================================================
# 宏回放器
# ============================================================
class MacroPlayer(QDialog):
    """
    宏回放器。

    提供宏回放的进度和控制。
    """

    def __init__(self, macro: Macro, proxy, parent=None):
        super().__init__(parent)

        self.macro = macro
        self.proxy = proxy
        self._cancelled = False

        self.setWindowTitle(f"回放宏: {macro.name}")
        self.setFixedSize(400, 160)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowContextHelpButtonHint
        )

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 宏名
        name_label = QLabel(f"宏: {self.macro.name}")
        name_label.setStyleSheet(
            "font-size: 13px; font-weight: bold;"
        )
        layout.addWidget(name_label)

        # 命令数
        count_label = QLabel(
            f"共 {self.macro.command_count} 条命令"
        )
        count_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(count_label)

        # 进度条
        from PyQt5.QtWidgets import QProgressBar
        self.progress = QProgressBar()
        self.progress.setRange(0, self.macro.command_count)
        layout.addWidget(self.progress)

        # 状态
        self.status_label = QLabel("准备回放...")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.status_label)

        # 取消按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QLabel {
                color: #d4d4d4;
            }
            QProgressBar {
                background-color: #2d2d2d;
                border: none;
                border-radius: 3px;
                height: 20px;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #0e639c;
                border-radius: 3px;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)

    def _on_cancel(self):
        """取消"""
        self._cancelled = True

    def is_cancelled(self) -> bool:
        """是否已取消"""
        return self._cancelled

    def update_progress(self, current: int, status: str = ""):
        """更新进度"""
        self.progress.setValue(current)
        if status:
            self.status_label.setText(status)
        QApplication.processEvents()

    def replay(self) -> bool:
        """
        执行回放。

        返回:
            是否成功完成
        """
        if not self.proxy or not self.macro:
            return False

        try:
            # 禁用 Scintilla 通知
            try:
                self.proxy.sc.SendScintilla(
                    self.proxy.sc.SCI_SETMODEVENTMASK, 0
                )
            except Exception:
                pass

            total = len(self.macro.commands)

            for i, macro_cmd in enumerate(self.macro.commands):
                if self._cancelled:
                    return False

                try:
                    cmd = Command.from_dict(macro_cmd.command_data)
                    cmd.execute(self.proxy.sc)
                except Exception as e:
                    print(f"[MacroPlayer] 回放命令失败: {e}")

                # 更新进度
                if i % 10 == 0 or i == total - 1:
                    self.update_progress(
                        i + 1,
                        f"回放中 {i + 1}/{total}"
                    )

            # 恢复通知
            try:
                from PyQt5.Qsci import QsciScintilla
                mask = (QsciScintilla.SC_MOD_INSERTTEXT |
                        QsciScintilla.SC_MOD_DELETETEXT)
                self.proxy.sc.SendScintilla(
                    self.proxy.sc.SCI_SETMODEVENTMASK, mask
                )
            except Exception:
                pass

            # 标记修改
            try:
                self.proxy.sc.setModified(True)
            except Exception:
                pass

            return not self._cancelled

        except Exception as e:
            print(f"[MacroPlayer] 回放失败: {e}")
            return False


# ============================================================
# 宏编辑器主对话框
# ============================================================
class MacroEditor(QDialog):
    """
    宏编辑器主对话框。

    功能:
    - 左侧：宏列表
    - 右侧：宏详情（命令序列）
    - 顶部：工具栏
    - 底部：按钮

    信号:
        macro_saved(str): 宏保存
        macro_deleted(str): 宏删除
        macro_replayed(str): 宏回放
    """

    macro_saved = pyqtSignal(str)
    macro_deleted = pyqtSignal(str)
    macro_replayed = pyqtSignal(str)

    def __init__(self, macro_recorder: Optional[MacroRecorder] = None,
                 macro_manager: Optional[MacroManager] = None,
                 action_manager=None,
                 main_window=None,
                 parent=None):
        """
        参数:
            macro_recorder: 宏录制器
            macro_manager: 宏管理器
            action_manager: 动作管理器
            main_window: 主窗口
            parent: 父窗口
        """
        super().__init__(parent or main_window)

        self.macro_recorder = macro_recorder
        self.macro_manager = macro_manager or MacroManager()
        self.act_mgr = action_manager
        self.main_window = main_window

        self._settings = QSettings("QingCao", "MacroEditor")

        # 当前选中的宏
        self._current_macro: Optional[Macro] = None

        self.setWindowTitle("宏编辑器")
        self.resize(900, 600)

        self._build_ui()
        self._connect_signals()
        self._apply_style()

        # 加载宏列表
        QTimer.singleShot(0, self._load_macros)

    # --------------------------------------------------------
    # UI 构建
    # --------------------------------------------------------
    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 顶部工具栏
        toolbar = self._build_toolbar()
        layout.addWidget(toolbar)

        # 主分割器
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：宏列表
        self.macro_list = MacroListPanel()
        splitter.addWidget(self.macro_list)

        # 右侧：宏详情
        right_panel = self._build_right_panel()
        splitter.addWidget(right_panel)

        # 设置比例
        splitter.setSizes([250, 650])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter, 1)

        # 底部按钮
        bottom = self._build_bottom_bar()
        layout.addWidget(bottom)

    def _build_toolbar(self) -> QWidget:
        """构建顶部工具栏"""
        toolbar = QWidget()
        toolbar.setStyleSheet(
            "background-color: #2d2d2d; border-radius: 4px;"
        )
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # 新建
        self.new_btn = QPushButton("➕ 新建")
        self.new_btn.clicked.connect(self._on_new_macro)
        layout.addWidget(self.new_btn)

        # 从录制器导入
        self.import_recorded_btn = QPushButton("⏺ 导入录制")
        self.import_recorded_btn.setToolTip(
            "将当前宏录制器的内容导入为新宏"
        )
        self.import_recorded_btn.clicked.connect(
            self._on_import_from_recorder
        )
        layout.addWidget(self.import_recorded_btn)

        # 分隔
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("background-color: #3c3c3c;")
        layout.addWidget(sep)

        # 回放
        self.play_btn = QPushButton("▶ 回放")
        self.play_btn.setToolTip("回放当前选中的宏")
        self.play_btn.clicked.connect(self._on_play_macro)
        self.play_btn.setEnabled(False)
        layout.addWidget(self.play_btn)

        # 回放多次
        self.play_n_btn = QPushButton("▶▶ 回放N次")
        self.play_n_btn.setToolTip("回放多次")
        self.play_n_btn.clicked.connect(self._on_play_macro_n)
        self.play_n_btn.setEnabled(False)
        layout.addWidget(self.play_n_btn)

        # 分隔
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("background-color: #3c3c3c;")
        layout.addWidget(sep2)

        # 绑定快捷键
        self.bind_btn = QPushButton("⌨ 绑定快捷键")
        self.bind_btn.clicked.connect(self._on_bind_shortcut)
        self.bind_btn.setEnabled(False)
        layout.addWidget(self.bind_btn)

        layout.addStretch()

        # 刷新
        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.clicked.connect(self._load_macros)
        layout.addWidget(self.refresh_btn)

        return toolbar

    def _build_right_panel(self) -> QWidget:
        """构建右侧面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 宏信息
        info_frame = QFrame()
        info_frame.setStyleSheet(
            "background-color: #2d2d2d; border-radius: 4px;"
        )
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(10, 8, 10, 8)
        info_layout.setSpacing(4)

        # 名称
        self.macro_name_label = QLabel("未选择宏")
        self.macro_name_label.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #7ec850;"
        )
        info_layout.addWidget(self.macro_name_label)

        # 元信息
        meta_layout = QHBoxLayout()
        self.macro_meta_label = QLabel("")
        self.macro_meta_label.setStyleSheet(
            "color: #888; font-size: 11px;"
        )
        meta_layout.addWidget(self.macro_meta_label)
        meta_layout.addStretch()
        info_layout.addLayout(meta_layout)

        # 描述
        self.macro_desc_label = QLabel("")
        self.macro_desc_label.setStyleSheet(
            "color: #d4d4d4; font-size: 12px;"
        )
        self.macro_desc_label.setWordWrap(True)
        info_layout.addWidget(self.macro_desc_label)

        layout.addWidget(info_frame)

        # 命令列表标题
        cmd_title_layout = QHBoxLayout()

        cmd_title = QLabel("命令序列")
        cmd_title.setStyleSheet(
            "font-size: 13px; font-weight: bold; padding: 4px 0;"
        )
        cmd_title_layout.addWidget(cmd_title)

        cmd_title_layout.addStretch()

        # 编辑按钮
        self.edit_cmd_btn = QToolButton()
        self.edit_cmd_btn.setText("✏")
        self.edit_cmd_btn.setToolTip("编辑选中的命令")
        self.edit_cmd_btn.setFixedSize(24, 24)
        self.edit_cmd_btn.clicked.connect(self._on_edit_command)
        cmd_title_layout.addWidget(self.edit_cmd_btn)

        # 上移
        self.move_up_btn = QToolButton()
        self.move_up_btn.setText("⬆")
        self.move_up_btn.setToolTip("上移命令")
        self.move_up_btn.setFixedSize(24, 24)
        self.move_up_btn.clicked.connect(self._on_move_up)
        cmd_title_layout.addWidget(self.move_up_btn)

        # 下移
        self.move_down_btn = QToolButton()
        self.move_down_btn.setText("⬇")
        self.move_down_btn.setToolTip("下移命令")
        self.move_down_btn.setFixedSize(24, 24)
        self.move_down_btn.clicked.connect(self._on_move_down)
        cmd_title_layout.addWidget(self.move_down_btn)

        # 删除
        self.delete_cmd_btn = QToolButton()
        self.delete_cmd_btn.setText("🗑")
        self.delete_cmd_btn.setToolTip("删除命令")
        self.delete_cmd_btn.setFixedSize(24, 24)
        self.delete_cmd_btn.clicked.connect(self._on_delete_command)
        cmd_title_layout.addWidget(self.delete_cmd_btn)

        layout.addLayout(cmd_title_layout)

        # 命令列表
        self.command_tree = QTreeWidget()
        self.command_tree.setObjectName("command_tree")
        self.command_tree.setColumnCount(3)
        self.command_tree.setHeaderLabels(["#", "命令", "描述"])
        self.command_tree.setIndentation(14)
        self.command_tree.setAlternatingRowColors(True)
        self.command_tree.setUniformRowHeights(True)
        self.command_tree.setSelectionMode(
            QAbstractItemView.SingleSelection
        )
        self.command_tree.setContextMenuPolicy(Qt.CustomContextMenu)

        # 列宽
        header = self.command_tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.command_tree.setColumnWidth(0, 40)

        self.command_tree.itemDoubleClicked.connect(
            lambda item, col: self._on_edit_command()
        )
        self.command_tree.customContextMenuRequested.connect(
            self._show_command_context_menu
        )

        layout.addWidget(self.command_tree, 1)

        # 命令统计
        self.cmd_stats_label = QLabel("")
        self.cmd_stats_label.setStyleSheet(
            "color: #888; font-size: 11px; padding: 4px 0;"
        )
        layout.addWidget(self.cmd_stats_label)

        return panel

    def _build_bottom_bar(self) -> QWidget:
        """构建底部按钮栏"""
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 保存
        self.save_btn = QPushButton("💾 保存宏")
        self.save_btn.setStyleSheet(
            "background-color: #7ec850; color: white;"
        )
        self.save_btn.clicked.connect(self._on_save_macro)
        self.save_btn.setEnabled(False)
        layout.addWidget(self.save_btn)

        # 另存为
        self.save_as_btn = QPushButton("💾 另存为...")
        self.save_as_btn.clicked.connect(self._on_save_as)
        self.save_as_btn.setEnabled(False)
        layout.addWidget(self.save_as_btn)

        # 分隔
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("background-color: #3c3c3c;")
        layout.addWidget(sep)

        # 导出
        self.export_btn = QPushButton("📤 导出")
        self.export_btn.clicked.connect(self._on_export)
        self.export_btn.setEnabled(False)
        layout.addWidget(self.export_btn)

        # 导入
        self.import_btn = QPushButton("📥 导入")
        self.import_btn.clicked.connect(self._on_import)
        layout.addWidget(self.import_btn)

        layout.addStretch()

        # 关闭
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        return bar

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QTreeWidget#command_tree {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                font-size: 12px;
                outline: none;
            }
            QTreeWidget#command_tree::item {
                padding: 4px 6px;
                border-radius: 2px;
            }
            QTreeWidget#command_tree::item:hover {
                background-color: #2a2d2e;
            }
            QTreeWidget#command_tree::item:selected {
                background-color: #094771;
                color: white;
            }
            QHeaderView::section {
                background-color: #2d2d2d;
                color: #ccc;
                border: none;
                border-bottom: 1px solid #3c3c3c;
                padding: 4px 6px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
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
            QPushButton:disabled {
                background-color: #3c3c3c;
                color: #666;
            }
            QToolButton {
                background-color: transparent;
                color: #d4d4d4;
                border: none;
                border-radius: 3px;
                font-size: 14px;
            }
            QToolButton:hover {
                background-color: #3c3c3c;
            }
        """)

    def _connect_signals(self):
        """连接信号"""
        # 宏列表
        self.macro_list.macro_selected.connect(self._on_macro_selected)
        self.macro_list.new_macro_requested.connect(self._on_new_macro)
        self.macro_list.delete_macro_requested.connect(
            self._on_delete_macro
        )
        self.macro_list.rename_macro_requested.connect(
            self._on_rename_macro
        )
        self.macro_list.duplicate_macro_requested.connect(
            self._on_duplicate_macro
        )

    # --------------------------------------------------------
    # 加载宏列表
    # --------------------------------------------------------
    def _load_macros(self):
        """加载宏列表"""
        try:
            # 从磁盘加载
            if self.macro_manager:
                self.macro_manager.load_all(MACROS_DIR)

            macros = self.macro_manager.list_macros()

            # 添加当前录制的宏（如果未保存）
            if (self.macro_recorder and
                    self.macro_recorder.has_commands()):
                current = self.macro_recorder.current_macro
                # 检查是否已在列表中
                if current.name not in [m.name for m in macros]:
                    macros.insert(0, current)

            self.macro_list.load_macros(macros)

            # 恢复选中
            if macros and not self.macro_list.get_selected_macro():
                self.macro_list.select_macro(macros[0])

        except Exception as e:
            print(f"[MacroEditor] 加载宏失败: {e}")

    # --------------------------------------------------------
    # 宏选中
    # --------------------------------------------------------
    def _on_macro_selected(self, macro: Macro):
        """宏被选中"""
        self._current_macro = macro
        self._refresh_macro_detail()

        # 启用/禁用按钮
        has_macro = macro is not None
        is_empty = macro.is_empty if macro else True

        self.play_btn.setEnabled(has_macro and not is_empty)
        self.play_n_btn.setEnabled(has_macro and not is_empty)
        self.bind_btn.setEnabled(has_macro)
        self.save_btn.setEnabled(has_macro)
        self.save_as_btn.setEnabled(has_macro)
        self.export_btn.setEnabled(has_macro and not is_empty)

    def _refresh_macro_detail(self):
        """刷新宏详情"""
        macro = self._current_macro

        if not macro:
            self.macro_name_label.setText("未选择宏")
            self.macro_meta_label.setText("")
            self.macro_desc_label.setText("")
            self.command_tree.clear()
            self.cmd_stats_label.setText("")
            return

        # 名称
        self.macro_name_label.setText(macro.name)

        # 元信息
        meta_parts = []
        meta_parts.append(f"{macro.command_count} 条命令")

        if macro.shortcut:
            meta_parts.append(f"⌨ {macro.shortcut}")

        if macro.author:
            meta_parts.append(f"👤 {macro.author}")

        if macro.updated_at:
            try:
                date = macro.updated_at[:10]
                meta_parts.append(f"📅 {date}")
            except Exception:
                pass

        self.macro_meta_label.setText(" · ".join(meta_parts))

        # 描述
        self.macro_desc_label.setText(
            macro.description or "（无描述）"
        )

        # 命令列表
        self._load_command_tree(macro)

    def _load_command_tree(self, macro: Macro):
        """加载命令树"""
        self.command_tree.setUpdatesEnabled(False)
        try:
            self.command_tree.clear()

            if macro.is_empty:
                empty_item = QTreeWidgetItem(self.command_tree)
                empty_item.setText(0, "")
                empty_item.setText(1, "（无命令）")
                empty_item.setForeground(1, QBrush(QColor("#666")))
                self.cmd_stats_label.setText("")
                return

            for i, macro_cmd in enumerate(macro.commands):
                try:
                    cmd = Command.from_dict(macro_cmd.command_data)
                    self._add_command_item(i, cmd, macro_cmd)
                except Exception as e:
                    # 解析失败
                    error_item = QTreeWidgetItem(self.command_tree)
                    error_item.setText(0, str(i + 1))
                    error_item.setText(1, "⚠ 无法解析")
                    error_item.setForeground(1, QBrush(QColor("#f14c4c")))

            # 统计
            stats = self._compute_stats(macro)
            self.cmd_stats_label.setText(
                f"共 {macro.command_count} 条命令 · "
                f"插入 {stats['inserts']} · "
                f"删除 {stats['deletes']} · "
                f"替换 {stats['replaces']}"
            )

        finally:
            self.command_tree.setUpdatesEnabled(True)

    def _add_command_item(self, index: int, cmd: Command,
                          macro_cmd: MacroCommand):
        """添加命令项"""
        item = QTreeWidgetItem(self.command_tree)

        # 序号
        item.setText(0, str(index + 1))

        # 命令类型
        cmd_type = cmd.command_type
        type_icon = COMMAND_TYPE_ICONS.get(cmd_type, "•")
        type_name = COMMAND_TYPE_NAMES.get(cmd_type, cmd_type)
        item.setText(1, f"{type_icon} {type_name}")

        # 描述
        desc = cmd.describe() if hasattr(cmd, 'describe') else str(cmd)
        item.setText(2, desc)

        # 颜色
        color = COMMAND_TYPE_COLORS.get(cmd_type)
        if color:
            item.setForeground(1, QBrush(color))

        # 时间偏移
        if macro_cmd.timestamp_offset > 0:
            tooltip = f"时间偏移: {macro_cmd.timestamp_offset:.3f}s"
            item.setToolTip(2, tooltip)

        # 数据
        item.setData(0, Qt.UserRole, index)

        # 命令组展开
        if isinstance(cmd, GroupCmd):
            for j, sub_cmd in enumerate(cmd.cmds):
                sub_item = QTreeWidgetItem(item)
                sub_item.setText(0, f"{index + 1}.{j + 1}")

                sub_type = sub_cmd.command_type
                sub_icon = COMMAND_TYPE_ICONS.get(sub_type, "•")
                sub_name = COMMAND_TYPE_NAMES.get(sub_type, sub_type)
                sub_item.setText(1, f"{sub_icon} {sub_name}")

                sub_desc = (sub_cmd.describe()
                            if hasattr(sub_cmd, 'describe')
                            else str(sub_cmd))
                sub_item.setText(2, sub_desc)

                sub_color = COMMAND_TYPE_COLORS.get(sub_type)
                if sub_color:
                    sub_item.setForeground(1, QBrush(sub_color))

            item.setExpanded(True)

    def _compute_stats(self, macro: Macro) -> Dict[str, int]:
        """统计命令类型"""
        stats = {'inserts': 0, 'deletes': 0, 'replaces': 0}

        for macro_cmd in macro.commands:
            try:
                cmd = Command.from_dict(macro_cmd.command_data)

                if isinstance(cmd, InsertCmd):
                    stats['inserts'] += 1
                elif isinstance(cmd, DeleteCmd):
                    stats['deletes'] += 1
                elif isinstance(cmd, ReplaceCmd):
                    stats['replaces'] += 1
                elif isinstance(cmd, GroupCmd):
                    for sub in cmd.cmds:
                        if isinstance(sub, InsertCmd):
                            stats['inserts'] += 1
                        elif isinstance(sub, DeleteCmd):
                            stats['deletes'] += 1
                        elif isinstance(sub, ReplaceCmd):
                            stats['replaces'] += 1
            except Exception:
                continue

        return stats

    # --------------------------------------------------------
    # 新建宏
    # --------------------------------------------------------
    def _on_new_macro(self):
        """新建宏"""
        name, ok = QInputDialog.getText(
            self, "新建宏", "宏名称:",
            text=f"新建宏_{datetime.datetime.now().strftime('%H%M%S')}"
        )

        if not ok or not name:
            return

        # 创建
        macro = Macro(name=name)
        macro.author = self.act_mgr.get("author", "") if self.act_mgr else ""

        # 添加到管理器
        if self.macro_manager:
            self.macro_manager.add(macro)

        # 刷新列表
        self._load_macros()
        self.macro_list.select_macro(macro)

    def _on_import_from_recorder(self):
        """从录制器导入"""
        if not self.macro_recorder or not self.macro_recorder.has_commands():
            QMessageBox.information(
                self, "无可导入内容",
                "宏录制器当前没有内容。\n\n"
                "请先使用 Ctrl+Shift+R 录制宏，再进行导入。"
            )
            return

        # 复制当前录制的宏
        source = self.macro_recorder.current_macro

        # 询问名称
        name, ok = QInputDialog.getText(
            self, "导入录制内容",
            "宏名称:",
            text=source.name
        )

        if not ok or not name:
            return

        # 创建副本
        import copy
        new_macro = copy.deepcopy(source)
        new_macro.name = name
        new_macro.created_at = datetime.datetime.now().isoformat()
        new_macro.updated_at = new_macro.created_at

        # 添加
        if self.macro_manager:
            if not self.macro_manager.add(new_macro, overwrite=False):
                QMessageBox.warning(
                    self, "添加失败",
                    f"宏 '{name}' 已存在"
                )
                return

        # 刷新
        self._load_macros()
        self.macro_list.select_macro(new_macro)

        QMessageBox.information(
            self, "导入成功",
            f"已从录制器导入 {new_macro.command_count} 条命令。"
        )

    # --------------------------------------------------------
    # 删除/重命名/复制
    # --------------------------------------------------------
    def _on_delete_macro(self, macro: Macro):
        """删除宏"""
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除宏 '{macro.name}' 吗？\n\n"
            f"该操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        if self.macro_manager:
            self.macro_manager.remove(macro.name)

        # 尝试删除磁盘文件
        try:
            filepath = os.path.join(
                MACROS_DIR,
                f"{MacroRecorder._sanitize_filename(macro.name)}{MACRO_FILE_EXT}"
            )
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass

        self._current_macro = None
        self._load_macros()
        self._refresh_macro_detail()

        self.macro_deleted.emit(macro.name)

    def _on_rename_macro(self, macro: Macro):
        """重命名宏"""
        new_name, ok = QInputDialog.getText(
            self, "重命名宏", "新名称:",
            text=macro.name
        )

        if not ok or not new_name or new_name == macro.name:
            return

        if self.macro_manager:
            success = self.macro_manager.rename(macro.name, new_name)
            if not success:
                QMessageBox.warning(
                    self, "重命名失败",
                    f"名称 '{new_name}' 已存在。"
                )
                return

        self._load_macros()

    def _on_duplicate_macro(self, macro: Macro):
        """复制宏"""
        new_name = f"{macro.name} 副本"

        # 处理重名
        base = new_name
        counter = 1
        existing = [m.name for m in self.macro_manager.list_macros()]
        while new_name in existing:
            counter += 1
            new_name = f"{base} {counter}"

        # 深拷贝
        import copy
        new_macro = copy.deepcopy(macro)
        new_macro.name = new_name
        new_macro.shortcut = ""  # 清除快捷键
        new_macro.created_at = datetime.datetime.now().isoformat()
        new_macro.updated_at = new_macro.created_at

        if self.macro_manager:
            self.macro_manager.add(new_macro)

        self._load_macros()
        self.macro_list.select_macro(new_macro)

    # --------------------------------------------------------
    # 命令操作
    # --------------------------------------------------------
    def _get_selected_command_index(self) -> int:
        """获取选中的命令索引"""
        item = self.command_tree.currentItem()
        if item:
            index = item.data(0, Qt.UserRole)
            if index is not None:
                return index
        return -1

    def _on_edit_command(self):
        """编辑命令"""
        index = self._get_selected_command_index()
        if index < 0 or not self._current_macro:
            return

        try:
            macro_cmd = self._current_macro.commands[index]
            cmd = Command.from_dict(macro_cmd.command_data)

            # 打开编辑对话框
            dlg = CommandEditDialog(cmd, self)
            if dlg.exec() == QDialog.Accepted:
                new_cmd = dlg.get_command()
                if new_cmd:
                    macro_cmd.command_data = new_cmd.to_dict()
                    self._current_macro.updated_at = (
                        datetime.datetime.now().isoformat()
                    )
                    self._load_command_tree(self._current_macro)

        except Exception as e:
            QMessageBox.warning(self, "编辑失败", str(e))

    def _on_move_up(self):
        """上移命令"""
        index = self._get_selected_command_index()
        if index <= 0 or not self._current_macro:
            return

        commands = self._current_macro.commands
        commands[index], commands[index - 1] = (
            commands[index - 1], commands[index]
        )

        self._load_command_tree(self._current_macro)

        # 选中移动后的位置
        self._select_command_at(index - 1)

    def _on_move_down(self):
        """下移命令"""
        index = self._get_selected_command_index()
        if not self._current_macro:
            return

        commands = self._current_macro.commands
        if index < 0 or index >= len(commands) - 1:
            return

        commands[index], commands[index + 1] = (
            commands[index + 1], commands[index]
        )

        self._load_command_tree(self._current_macro)
        self._select_command_at(index + 1)

    def _select_command_at(self, index: int):
        """选中指定索引的命令"""
        for i in range(self.command_tree.topLevelItemCount()):
            item = self.command_tree.topLevelItem(i)
            if item.data(0, Qt.UserRole) == index:
                self.command_tree.setCurrentItem(item)
                break

    def _on_delete_command(self):
        """删除命令"""
        index = self._get_selected_command_index()
        if index < 0 or not self._current_macro:
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除第 {index + 1} 条命令吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        del self._current_macro.commands[index]
        self._current_macro.updated_at = (
            datetime.datetime.now().isoformat()
        )

        self._load_command_tree(self._current_macro)

    def _show_command_context_menu(self, pos: QPoint):
        """命令右键菜单"""
        item = self.command_tree.itemAt(pos)
        if not item:
            return

        self.command_tree.setCurrentItem(item)

        menu = QMenu(self)

        # 编辑
        edit_act = menu.addAction("✏ 编辑")
        edit_act.triggered.connect(self._on_edit_command)

        menu.addSeparator()

        # 上移/下移
        up_act = menu.addAction("⬆ 上移")
        up_act.triggered.connect(self._on_move_up)

        down_act = menu.addAction("⬇ 下移")
        down_act.triggered.connect(self._on_move_down)

        menu.addSeparator()

        # 删除
        delete_act = menu.addAction("🗑 删除")
        delete_act.triggered.connect(self._on_delete_command)

        menu.addSeparator()

        # 复制命令描述
        copy_act = menu.addAction("📋 复制命令描述")
        copy_act.triggered.connect(self._copy_command_description)

        menu.exec(self.command_tree.viewport().mapToGlobal(pos))

    def _copy_command_description(self):
        """复制命令描述"""
        index = self._get_selected_command_index()
        if index < 0 or not self._current_macro:
            return

        try:
            macro_cmd = self._current_macro.commands[index]
            cmd = Command.from_dict(macro_cmd.command_data)
            desc = cmd.describe() if hasattr(cmd, 'describe') else str(cmd)
            QApplication.clipboard().setText(desc)
        except Exception:
            pass

    # --------------------------------------------------------
    # 回放
    # --------------------------------------------------------
    def _on_play_macro(self):
        """回放宏"""
        self._play_macro(repeat=1)

    def _on_play_macro_n(self):
        """回放宏 N 次"""
        count, ok = QInputDialog.getInt(
            self, "回放次数", "回放次数:",
            1, 1, 100
        )

        if not ok:
            return

        self._play_macro(repeat=count)

    def _play_macro(self, repeat: int = 1):
        """执行宏回放"""
        if not self._current_macro or self._current_macro.is_empty:
            return

        # 获取当前编辑器
        proxy = None
        if self.main_window and hasattr(self.main_window, 'tabs'):
            proxy = self.main_window.tabs.current_proxy()

        if not proxy:
            QMessageBox.information(
                self, "无编辑器",
                "请先打开或切换到编辑器标签。"
            )
            return

        # 创建回放器
        player = MacroPlayer(self._current_macro, proxy, self)
        player.show()

        # 执行
        for i in range(repeat):
            if player.is_cancelled():
                break

            player.status_label.setText(
                f"第 {i + 1}/{repeat} 次回放"
            )
            QApplication.processEvents()

            success = player.replay()
            if not success:
                break

        player.close()

        # 发射信号
        self.macro_replayed.emit(self._current_macro.name)

        # 状态消息
        try:
            bus.emit_status(
                f"宏 '{self._current_macro.name}' 回放完成",
                2000, "success"
            )
        except Exception:
            pass

    # --------------------------------------------------------
    # 保存
    # --------------------------------------------------------
    def _on_save_macro(self):
        """保存宏"""
        if not self._current_macro:
            return

        try:
            filepath = os.path.join(
                MACROS_DIR,
                f"{MacroRecorder._sanitize_filename(self._current_macro.name)}"
                f"{MACRO_FILE_EXT}"
            )

            os.makedirs(MACROS_DIR, exist_ok=True)

            if self._current_macro.save(filepath):
                bus.emit_status(
                    f"宏已保存: {self._current_macro.name}",
                    2000, "success"
                )
                self.macro_saved.emit(self._current_macro.name)
            else:
                QMessageBox.warning(self, "保存失败", "无法写入文件")

        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _on_save_as(self):
        """另存为"""
        if not self._current_macro:
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "另存为",
            f"{self._current_macro.name}{MACRO_FILE_EXT}",
            "青草宏文件 (*.qingcao-macro.json);;JSON 文件 (*.json)"
        )

        if not filepath:
            return

        try:
            if self._current_macro.save(filepath):
                bus.emit_status(
                    f"已保存到: {os.path.basename(filepath)}",
                    2000, "success"
                )
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    # --------------------------------------------------------
    # 导入/导出
    # --------------------------------------------------------
    def _on_export(self):
        """导出宏"""
        if not self._current_macro or self._current_macro.is_empty:
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出宏",
            f"{self._current_macro.name}.json",
            "JSON 文件 (*.json)"
        )

        if not filepath:
            return

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(
                    self._current_macro.to_dict(),
                    f, indent=2, ensure_ascii=False
                )

            bus.emit_status(
                f"已导出到: {os.path.basename(filepath)}",
                2000, "success"
            )
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _on_import(self):
        """导入宏"""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "导入宏",
            "",
            "宏文件 (*.json);;所有文件 (*.*)"
        )

        if not filepath:
            return

        try:
            macro = Macro.load(filepath)
            if not macro:
                QMessageBox.warning(self, "导入失败", "无法解析文件")
                return

            # 检查重名
            existing = [m.name for m in self.macro_manager.list_macros()]
            if macro.name in existing:
                reply = QMessageBox.question(
                    self, "名称冲突",
                    f"宏 '{macro.name}' 已存在，是否覆盖？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )

                if reply != QMessageBox.Yes:
                    # 重命名
                    new_name, ok = QInputDialog.getText(
                        self, "重命名",
                        "新名称:",
                        text=f"{macro.name} (导入)"
                    )
                    if not ok or not new_name:
                        return
                    macro.name = new_name

            if self.macro_manager:
                self.macro_manager.add(macro, overwrite=True)

            self._load_macros()
            self.macro_list.select_macro(macro)

            bus.emit_status(
                f"已导入宏: {macro.name}",
                2000, "success"
            )

        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))

    # --------------------------------------------------------
    # 快捷键绑定
    # --------------------------------------------------------
    def _on_bind_shortcut(self):
        """绑定快捷键"""
        if not self._current_macro:
            return

        dlg = ShortcutBindDialog(
            self._current_macro.name,
            self._current_macro.shortcut,
            self
        )

        if dlg.exec() == QDialog.Accepted:
            new_shortcut = dlg.shortcut

            # 从旧快捷键解除
            old_shortcut = self._current_macro.shortcut

            # 更新
            self._current_macro.shortcut = new_shortcut

            # 更新管理器中的映射
            if self.macro_manager and new_shortcut:
                self.macro_manager.bind_shortcut(
                    self._current_macro.name, new_shortcut
                )

            # 刷新
            self._load_macros()
            self.macro_list.select_macro(self._current_macro)
            self._refresh_macro_detail()

            bus.emit_status(
                f"快捷键: {new_shortcut or '（无）'}",
                2000, "success"
            )

    # --------------------------------------------------------
    # 调试
    # --------------------------------------------------------
    def dump(self) -> str:
        """导出编辑器信息"""
        lines = ["MacroEditor", "=" * 60]
        lines.append(f"宏总数: {self.macro_list.list_widget.count()}")

        if self._current_macro:
            lines.append(f"当前宏: {self._current_macro.name}")
            lines.append(
                f"命令数: {self._current_macro.command_count}"
            )
            lines.append(
                f"快捷键: {self._current_macro.shortcut or '（无）'}"
            )

        if self.macro_manager:
            lines.append(f"管理器宏数: {self.macro_manager.count()}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<MacroEditor macros={self.macro_list.list_widget.count()} "
                f"current={self._current_macro.name if self._current_macro else None}>")


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys
    import tempfile
    import shutil
    from PyQt5.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)

    # 创建测试目录
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_macro_editor_test_")
    original_cwd = os.getcwd()
    os.chdir(tmp_dir)

    try:
        # 创建主窗口
        win = QMainWindow()
        win.setWindowTitle("MacroEditor 测试")
        win.resize(1000, 700)
        win.show()

        # 创建管理器
        manager = MacroManager()

        # 创建测试宏
        macro1 = Macro(name="插入文件头", description="插入 Python 文件头")
        macro1.add_command(InsertCmd(0, "#!/usr/bin/env python\n"))
        macro1.add_command(InsertCmd(21, "# -*- coding: utf-8 -*-\n"))
        macro1.add_command(InsertCmd(45, "\n"))
        macro1.shortcut = "Ctrl+Alt+H"
        manager.add(macro1)

        macro2 = Macro(name="格式化 JSON", description="快速格式化 JSON")
        macro2.add_command(ReplaceCmd(0, 100, '{"a":1}', '{\n  "a": 1\n}'))
        manager.add(macro2)

        macro3 = Macro(name="清理行尾空白", description="清除所有行尾空白")
        macro3.add_command(DeleteCmd(10, 5))
        macro3.add_command(DeleteCmd(20, 3))
        manager.add(macro3)

        print(f"已创建 {manager.count()} 个测试宏")
        print()

        # 创建编辑器
        editor = MacroEditor(
            macro_recorder=None,
            macro_manager=manager,
        )
        editor.show()

        # 打印信息
        def print_info():
            print("=== MacroEditor 信息 ===")
            print(editor.dump())
            print()

        QTimer.singleShot(2000, print_info)

        # 退出
        def cleanup_and_quit():
            os.chdir(original_cwd)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            app.quit()

        QTimer.singleShot(6000, cleanup_and_quit)

        sys.exit(app.exec())

    except Exception as e:
        os.chdir(original_cwd)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"测试失败: {e}")
        sys.exit(1)