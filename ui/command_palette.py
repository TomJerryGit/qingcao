#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为命令面板模块，包含：
- CommandPalette：命令面板（模糊搜索所有命令）
- FilePalette：文件快速切换面板（Ctrl+P）
- SymbolPalette：符号跳转面板（Ctrl+R）
- LineJumpPalette：行号跳转（:数字）
- 模糊匹配算法
- 快捷键显示
- 分类筛选
- 命令历史
- 图标支持
- 弹性动画
- 键盘导航
"""

import os
import re
import sys
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPalette, QPen
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.actions import ActionManager
from app.event_bus import StatusMessageEvent, bus


# ============================================================
# 常量
# ============================================================
# 面板最大显示条目
MAX_DISPLAY_ITEMS = 100

# 面板默认尺寸
DEFAULT_WIDTH = 500
DEFAULT_HEIGHT = 400
MIN_HEIGHT = 200

# 动画时长（毫秒）
ANIMATION_DURATION = 180

# 模糊匹配分数
SCORE_EXACT_MATCH = 1000
SCORE_PREFIX_MATCH = 500
SCORE_WORD_BOUNDARY = 200
SCORE_SUBSTRING = 100
SCORE_FUZZY_CHAR = 10
SCORE_FUZZY_GAP = -1
SCORE_RECENCY_BONUS = 50
SCORE_FREQUENCY_BONUS = 30


# ============================================================
# 面板模式枚举
# ============================================================
class PaletteMode(Enum):
    """面板模式"""
    COMMAND = auto()   # 命令模式（Ctrl+Shift+P）
    FILE = auto()      # 文件切换（Ctrl+P）
    SYMBOL = auto()    # 符号跳转（Ctrl+R）
    LINE = auto()      # 行号跳转（:数字）
    THEME = auto()     # 主题切换
    PLUGIN = auto()    # 插件命令
    GOTO_LINE = auto() # 跳转到行


# ============================================================
# 条目数据
# ============================================================
@dataclass
class PaletteItem:
    """
    面板条目。

    封装命令/文件/符号的显示与执行信息。
    """

    # 显示
    title: str = ""
    subtitle: str = ""
    category: str = ""
    icon: str = ""

    # 执行
    action_name: str = ""       # ActionManager 中的名称
    callback: Optional[Callable] = None  # 直接回调（优先级高于 action_name）
    data: Any = None            # 附加数据（如文件路径、行号）

    # 排序辅助
    score: int = 0
    last_used: float = 0.0
    use_count: int = 0

    # 关键词（用于搜索）
    keywords: List[str] = field(default_factory=list)

    def get_search_text(self) -> str:
        """获取用于搜索的文本"""
        parts = [self.title, self.subtitle, self.category]
        parts.extend(self.keywords)
        return " ".join(p for p in parts if p).lower()

    def __repr__(self) -> str:
        return f"<PaletteItem {self.title!r} category={self.category!r}>"


# ============================================================
# 模糊匹配算法
# ============================================================
def fuzzy_match(pattern: str, text: str) -> Tuple[bool, int]:
    """
    模糊匹配算法。

    参数:
        pattern: 搜索模式（小写）
        text: 目标文本（小写）

    返回:
        (是否匹配, 匹配分数)
        分数越高越相关
    """
    if not pattern:
        return (True, 0)

    if not text:
        return (False, 0)

    # 完全匹配
    if pattern == text:
        return (True, SCORE_EXACT_MATCH)

    # 前缀匹配
    if text.startswith(pattern):
        return (True, SCORE_PREFIX_MATCH - len(text))

    # 单词边界匹配（如 "sv" 匹配 "save file"）
    words = re.split(r'[\s\-_.]+', text)
    if any(w.startswith(pattern) for w in words):
        return (True, SCORE_WORD_BOUNDARY)

    # 子串匹配
    idx = text.find(pattern)
    if idx >= 0:
        # 子串越靠前分数越高
        return (True, SCORE_SUBSTRING - idx)

    # 逐字符模糊匹配
    pattern_idx = 0
    text_idx = 0
    score = 0
    last_match_idx = -1
    matched_positions = []

    while pattern_idx < len(pattern) and text_idx < len(text):
        if pattern[pattern_idx] == text[text_idx]:
            matched_positions.append(text_idx)
            # 字符连续则加分
            if last_match_idx >= 0 and text_idx == last_match_idx + 1:
                score += SCORE_FUZZY_CHAR * 2
            else:
                score += SCORE_FUZZY_CHAR
            last_match_idx = text_idx
            pattern_idx += 1
        text_idx += 1

    # 未完全匹配
    if pattern_idx < len(pattern):
        return (False, 0)

    # 匹配越紧凑分数越高
    if len(matched_positions) > 1:
        span = matched_positions[-1] - matched_positions[0] + 1
        gaps = span - len(matched_positions)
        score -= gaps * abs(SCORE_FUZZY_GAP)

    # 匹配位置越靠前分数越高
    score -= matched_positions[0] if matched_positions else 0

    return (True, max(1, score))


# ============================================================
# 命令面板基类
# ============================================================
class BasePalette(QDialog):
    """
    命令面板基类。

    提供:
    - 输入框
    - 结果列表
    - 键盘导航（上下箭头、回车、Esc）
    - 模糊搜索
    - 弹性动画
    """

    # 信号
    item_selected = pyqtSignal(object)  # PaletteItem

    def __init__(self, parent=None, mode: PaletteMode = PaletteMode.COMMAND):
        super().__init__(parent)

        self.mode = mode
        self.items: List[PaletteItem] = []
        self.filtered_items: List[PaletteItem] = []
        self.selected_index: int = 0

        # 使用历史（标题 -> 使用时间/次数）
        self._usage_history: Dict[str, Tuple[float, int]] = {}

        # 设置窗口属性
        self.setWindowFlags(
            Qt.Popup | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setModal(True)

        self.setFixedWidth(DEFAULT_WIDTH)
        self.setMinimumHeight(MIN_HEIGHT)
        self.resize(DEFAULT_WIDTH, DEFAULT_HEIGHT)

        # 构建 UI
        self._build_ui()

        # 动画
        self._animation: Optional[QPropertyAnimation] = None

    # --------------------------------------------------------
    # UI 构建
    # --------------------------------------------------------
    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 输入框容器
        input_frame = QFrame(self)
        input_frame.setObjectName("input_frame")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 10, 12, 10)
        input_layout.setSpacing(8)

        # 前缀标签（模式标识）
        self.prefix_label = QLabel(self._get_prefix_text())
        self.prefix_label.setObjectName("prefix_label")
        input_layout.addWidget(self.prefix_label)

        # 输入框
        self.input_edit = QLineEdit()
        self.input_edit.setObjectName("input_edit")
        self.input_edit.setPlaceholderText(self._get_placeholder())
        self.input_edit.setFrame(False)
        self.input_edit.textChanged.connect(self._on_text_changed)
        self.input_edit.returnPressed.connect(self._on_return_pressed)
        input_layout.addWidget(self.input_edit, 1)

        layout.addWidget(input_frame)

        # 结果列表
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("result_list")
        self.list_widget.setFrameShape(QFrame.NoFrame)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.itemActivated.connect(self._on_item_activated)
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self.list_widget, 1)

        # 状态栏
        self.status_label = QLabel("")
        self.status_label.setObjectName("status_label")
        self.status_label.setFixedHeight(24)
        layout.addWidget(self.status_label)

        # 应用样式
        self._apply_style()

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QDialog {
                background-color: #252526;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
            }
            QFrame#input_frame {
                background-color: #2d2d2d;
                border-bottom: 1px solid #3c3c3c;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QLabel#prefix_label {
                color: #7ec850;
                font-weight: bold;
                font-size: 13px;
                padding: 0 4px;
            }
            QLineEdit#input_edit {
                background: transparent;
                border: none;
                color: #d4d4d4;
                font-size: 14px;
                padding: 2px;
                selection-background-color: #094771;
            }
            QListWidget#result_list {
                background-color: #252526;
                border: none;
                color: #d4d4d4;
                font-size: 13px;
                padding: 4px;
                outline: none;
            }
            QListWidget#result_list::item {
                padding: 6px 10px;
                border-radius: 4px;
            }
            QListWidget#result_list::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QListWidget#result_list::item:hover {
                background-color: #2a2d2e;
            }
            QLabel#status_label {
                background-color: #007acc;
                color: #ffffff;
                font-size: 11px;
                padding: 4px 12px;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
            }
        """)

    def _get_prefix_text(self) -> str:
        """获取前缀标签文本"""
        prefix_map = {
            PaletteMode.COMMAND: "⌘ ",
            PaletteMode.FILE: "📂 ",
            PaletteMode.SYMBOL: "🔣 ",
            PaletteMode.LINE: ":",
            PaletteMode.THEME: "🎨 ",
            PaletteMode.PLUGIN: "🧩 ",
            PaletteMode.GOTO_LINE: "→ ",
        }
        return prefix_map.get(self.mode, "> ")

    def _get_placeholder(self) -> str:
        """获取输入框占位符"""
        placeholder_map = {
            PaletteMode.COMMAND: "输入命令...",
            PaletteMode.FILE: "输入文件名或路径...",
            PaletteMode.SYMBOL: "输入符号名称...",
            PaletteMode.LINE: "输入行号...",
            PaletteMode.THEME: "输入主题名称...",
            PaletteMode.PLUGIN: "输入插件命令...",
            PaletteMode.GOTO_LINE: "输入行号跳转...",
        }
        return placeholder_map.get(self.mode, "输入...")

    # --------------------------------------------------------
    # 条目设置
    # --------------------------------------------------------
    def set_items(self, items: List[PaletteItem]):
        """设置条目列表"""
        self.items = items
        self._refresh()

    def add_item(self, item: PaletteItem):
        """添加单个条目"""
        self.items.append(item)
        self._refresh()

    def set_usage_history(self, history: Dict[str, Tuple[float, int]]):
        """设置使用历史（标题 -> (时间戳, 次数)）"""
        self._usage_history = history or {}

    # --------------------------------------------------------
    # 搜索与过滤
    # --------------------------------------------------------
    def _on_text_changed(self, text: str):
        """输入变化"""
        # 行号模式特殊处理
        if self.mode == PaletteMode.LINE or text.startswith(':'):
            self._handle_line_input(text)
            return

        self._filter_items(text)

    def _handle_line_input(self, text: str):
        """处理行号输入"""
        # 移除前缀冒号
        num_str = text.lstrip(':')

        if not num_str:
            self.list_widget.clear()
            self.status_label.setText("输入行号后回车跳转")
            return

        try:
            line = int(num_str)
            self.status_label.setText(f"跳转到行 {line}")
        except ValueError:
            self.status_label.setText("无效行号")

    def _filter_items(self, query: str):
        """过滤条目"""
        query = query.strip().lower()

        self.list_widget.clear()
        self.filtered_items = []

        if not query:
            # 无搜索词时，按使用频率和时间排序
            display_items = self._sort_by_usage(self.items)
        else:
            # 模糊匹配
            scored_items = []
            for item in self.items:
                match_text = item.get_search_text()
                matched, score = fuzzy_match(query, match_text)

                if matched:
                    # 应用使用历史的加分
                    final_score = score + self._get_usage_score(item)
                    item_copy = PaletteItem(
                        title=item.title,
                        subtitle=item.subtitle,
                        category=item.category,
                        icon=item.icon,
                        action_name=item.action_name,
                        callback=item.callback,
                        data=item.data,
                        score=final_score,
                        keywords=item.keywords,
                    )
                    scored_items.append((final_score, item_copy))

            # 按分数降序排序
            scored_items.sort(key=lambda x: x[0], reverse=True)
            display_items = [item for _, item in scored_items]

        # 限制显示数量
        display_items = display_items[:MAX_DISPLAY_ITEMS]
        self.filtered_items = display_items

        # 添加到列表
        for item in display_items:
            list_item = self._create_list_item(item)
            self.list_widget.addItem(list_item)

        # 选中第一项
        if display_items:
            self.list_widget.setCurrentRow(0)
            self.selected_index = 0

        # 更新状态栏
        self._update_status(len(display_items), len(self.items))

    def _usage_key(self, item: PaletteItem) -> str:
        """P3-2: 生成更唯一的 key

        原实现用 item.title 作 key，不同命令（同名）会串用
        同一份历史分数。优先用 action_name；其次回调/数据的 id。
        """
        if item.action_name:
            return f"action:{item.action_name}"
        if item.callback is not None:
            return f"cb:{id(item.callback)}"
        if item.data is not None:
            return f"data:{id(item.data)}"
        return f"title:{item.title}"

    def _get_usage_score(self, item: PaletteItem) -> int:
        """根据使用历史计算加分"""
        key = self._usage_key(item)
        if key not in self._usage_history:
            return 0

        last_used, use_count = self._usage_history[key]

        # 最近使用的加分
        elapsed = time.time() - last_used
        if elapsed < 60:  # 1 分钟内
            recency_bonus = SCORE_RECENCY_BONUS
        elif elapsed < 600:  # 10 分钟内
            recency_bonus = SCORE_RECENCY_BONUS // 2
        elif elapsed < 3600:  # 1 小时内
            recency_bonus = SCORE_RECENCY_BONUS // 4
        else:
            recency_bonus = 0

        # 使用频率加分
        frequency_bonus = min(
            use_count * SCORE_FREQUENCY_BONUS // 10,
            SCORE_FREQUENCY_BONUS
        )

        return recency_bonus + frequency_bonus

    def _sort_by_usage(self, items: List[PaletteItem]) -> List[PaletteItem]:
        """按使用历史排序"""
        def sort_key(item: PaletteItem) -> Tuple[int, int, str]:
            key = item.title
            if key in self._usage_history:
                last_used, use_count = self._usage_history[key]
                # 使用过：按次数降序，时间降序
                return (-use_count, -last_used, item.title)
            else:
                # 未使用过：排在后面，按标题字母序
                return (0, 0, item.title)

        return sorted(items, key=sort_key)

    def _create_list_item(self, item: PaletteItem) -> QListWidgetItem:
        """创建列表条目"""
        list_item = QListWidgetItem()

        # 标题 + 分类
        text = item.title
        if item.subtitle:
            text += f"  {item.subtitle}"

        list_item.setText(text)

        # 设置数据
        list_item.setData(Qt.UserRole, item)

        # 设置工具提示
        tooltip_parts = [item.title]
        if item.subtitle:
            tooltip_parts.append(item.subtitle)
        if item.category:
            tooltip_parts.append(f"分类: {item.category}")
        list_item.setToolTip("\n".join(tooltip_parts))

        return list_item

    def _update_status(self, shown: int, total: int):
        """更新状态栏"""
        if shown == 0:
            self.status_label.setText("无匹配结果")
        elif shown == total:
            self.status_label.setText(f"共 {total} 项")
        else:
            self.status_label.setText(f"显示 {shown} / {total} 项")

    # --------------------------------------------------------
    # 键盘导航
    # --------------------------------------------------------
    def keyPressEvent(self, event):
        """键盘事件"""
        key = event.key()

        if key == Qt.Key_Escape:
            self.reject()
            return

        if key == Qt.Key_Up:
            self._move_selection(-1)
            return

        if key == Qt.Key_Down:
            self._move_selection(1)
            return

        if key == Qt.Key_PageUp:
            self._move_selection(-10)
            return

        if key == Qt.Key_PageDown:
            self._move_selection(10)
            return

        if key == Qt.Key_Return or key == Qt.Key_Enter:
            self._on_return_pressed()
            return

        if key == Qt.Key_Tab:
            # Tab 键可切换到下一分类（如果有分类）
            self._cycle_category()
            return

        # 传递给输入框
        super().keyPressEvent(event)

    def _move_selection(self, delta: int):
        """移动选中项"""
        count = self.list_widget.count()
        if count == 0:
            return

        new_row = self.selected_index + delta
        new_row = max(0, min(new_row, count - 1))

        self.list_widget.setCurrentRow(new_row)
        self.selected_index = new_row

    def _cycle_category(self):
        """循环切换分类（保留接口）"""
        pass

    def _on_row_changed(self, row: int):
        """选中行变化"""
        self.selected_index = row

        # 更新状态栏显示当前项
        item = self.list_widget.item(row)
        if item:
            data = item.data(Qt.UserRole)
            if isinstance(data, PaletteItem):
                detail = data.title
                if data.category:
                    detail = f"[{data.category}] {detail}"
                self.status_label.setText(detail)

    def _on_return_pressed(self):
        """回车键"""
        # 行号模式
        if self.mode == PaletteMode.LINE:
            self._execute_line_jump()
            return

        if self.input_edit.text().startswith(':'):
            self._execute_line_jump()
            return

        # 常规选中
        self._on_item_activated(self.list_widget.currentItem())

    def _execute_line_jump(self):
        """执行行号跳转"""
        text = self.input_edit.text().lstrip(':')
        try:
            line = int(text)
            item = PaletteItem(
                title=f"跳转到行 {line}",
                data=line,
            )
            self.item_selected.emit(item)
            self.accept()
        except ValueError:
            self.status_label.setText("无效行号")
            return

    def _on_item_activated(self, list_item: QListWidgetItem):
        """条目激活"""
        if list_item is None:
            return

        item = list_item.data(Qt.UserRole)
        if not isinstance(item, PaletteItem):
            return

        # 记录使用历史
        self._record_usage(item)

        # 发射信号
        self.item_selected.emit(item)

        self.accept()

    def _record_usage(self, item: PaletteItem):
        """记录使用历史"""
        # P3-2: 用 _usage_key 生成 key
        key = self._usage_key(item)
        now = time.time()

        if key in self._usage_history:
            _, count = self._usage_history[key]
            self._usage_history[key] = (now, count + 1)
        else:
            self._usage_history[key] = (now, 1)

    def get_usage_history(self) -> Dict[str, Tuple[float, int]]:
        """获取使用历史"""
        return dict(self._usage_history)

    # --------------------------------------------------------
    # 显示与动画
    # --------------------------------------------------------
    def showEvent(self, event):
        """显示事件（带弹性动画）"""
        super().showEvent(event)

        # 清空输入
        self.input_edit.clear()

        # 聚焦输入框
        self.input_edit.setFocus()

        # 刷新列表
        self._refresh()

        # 透明度动画
        self.setWindowOpacity(0.0)

        self._animation = QPropertyAnimation(self, b"windowOpacity")
        self._animation.setDuration(ANIMATION_DURATION)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._animation.start()

    def _refresh(self):
        """刷新列表"""
        self._filter_items(self.input_edit.text())

    # --------------------------------------------------------
    # 位置调整
    # --------------------------------------------------------
    def center_on_parent(self):
        """在父窗口上居中"""
        parent = self.parent()
        if parent:
            parent_geo = parent.geometry()
            x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - self.height()) // 3
            self.move(x, y)


# ============================================================
# 命令面板
# ============================================================
class CommandPalette(BasePalette):
    """
    命令面板。

    显示所有已注册的命令，支持模糊搜索。

    用法:
        palette = CommandPalette(action_manager, parent)
        palette.exec()
    """

    def __init__(self, action_manager: ActionManager,
                 parent=None,
                 mode: PaletteMode = PaletteMode.COMMAND,
                 tab_mgr=None,
                 outline=None):
        """
        参数:
            action_manager: ActionManager 实例
            parent: 父窗口
            mode: 面板模式
            tab_mgr: 标签管理器（用于文件切换）
            outline: 大纲面板（用于符号跳转）
        """
        self.action_manager = action_manager
        self.tab_mgr = tab_mgr
        self.outline = outline

        super().__init__(parent, mode)

        # 加载条目
        self._load_items()

        # 连接信号
        self.item_selected.connect(self._execute_item)

    def _load_items(self):
        """加载条目"""
        items = []

        if self.mode == PaletteMode.COMMAND:
            items = self._load_commands()
        elif self.mode == PaletteMode.FILE:
            items = self._load_files()
        elif self.mode == PaletteMode.SYMBOL:
            items = self._load_symbols()
        elif self.mode == PaletteMode.THEME:
            items = self._load_themes()
        elif self.mode == PaletteMode.PLUGIN:
            items = self._load_plugin_commands()

        self.set_items(items)

    def _load_commands(self) -> List[PaletteItem]:
        """加载所有命令"""
        items = []

        for name, action in self.action_manager.actions.items():
            if not action.text():
                continue

            # 获取快捷键
            shortcut = action.shortcut().toString()

            # 获取分类
            category = self.action_manager.categories.get(name, "其他")

            # 获取描述
            description = self.action_manager.descriptions.get(name, "")

            item = PaletteItem(
                title=action.text(),
                subtitle=shortcut,
                category=category,
                action_name=name,
                keywords=[name, description],
            )

            # 如果有图标
            try:
                icon = action.icon()
                if not icon.isNull():
                    item.icon = "has_icon"
            except Exception:
                pass

            items.append(item)

        return items

    def _load_files(self) -> List[PaletteItem]:
        """加载已打开的文件"""
        items = []

        if not self.tab_mgr:
            return items

        try:
            for i in range(self.tab_mgr.count()):
                widget = self.tab_mgr.widget(i)
                title = self.tab_mgr.tabText(i)

                filepath = None
                if hasattr(widget, 'proxy'):
                    proxy = widget.proxy
                    if proxy and proxy.document:
                        filepath = proxy.document.filepath

                # 获取目录作为副标题
                subtitle = ""
                if filepath:
                    subtitle = os.path.dirname(filepath)
                    if len(subtitle) > 60:
                        subtitle = "..." + subtitle[-57:]

                item = PaletteItem(
                    title=title,
                    subtitle=subtitle,
                    category="打开的文件",
                    data={'index': i, 'filepath': filepath},
                    keywords=[filepath or ""],
                )
                items.append(item)

            # 添加最近文件
            from PyQt5.QtCore import QSettings
            settings = QSettings("QingCao", "Editor")
            recent = settings.value("recent_files", [])
            if isinstance(recent, str):
                recent = [recent] if recent else []

            open_paths = set()
            for i in range(self.tab_mgr.count()):
                w = self.tab_mgr.widget(i)
                if hasattr(w, 'proxy') and w.proxy and w.proxy.document:
                    if w.proxy.document.filepath:
                        open_paths.add(w.proxy.document.filepath)

            for filepath in recent[:20]:
                if not filepath or not os.path.exists(filepath):
                    continue
                if filepath in open_paths:
                    continue

                item = PaletteItem(
                    title=os.path.basename(filepath),
                    subtitle=os.path.dirname(filepath),
                    category="最近文件",
                    data={'filepath': filepath},
                    keywords=[filepath],
                )
                items.append(item)

        except Exception as e:
            print(f"[CommandPalette] 加载文件失败: {e}")

        return items

    def _load_symbols(self) -> List[PaletteItem]:
        """加载当前文件的符号"""
        items = []

        if not self.outline:
            return items

        try:
            symbols = self.outline.get_all_symbols()
            for name, line in symbols:
                item = PaletteItem(
                    title=name,
                    subtitle=f"行 {line + 1}",
                    category="符号",
                    data={'line': line},
                )
                items.append(item)
        except Exception as e:
            print(f"[CommandPalette] 加载符号失败: {e}")

        return items

    def _load_themes(self) -> List[PaletteItem]:
        """加载主题"""
        items = []

        themes_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "themes"
        )

        if os.path.isdir(themes_dir):
            for filename in sorted(os.listdir(themes_dir)):
                if filename.endswith('.json'):
                    theme_name = os.path.splitext(filename)[0]
                    theme_path = os.path.join(themes_dir, filename)

                    item = PaletteItem(
                        title=theme_name,
                        subtitle="主题",
                        category="主题",
                        data={'theme_path': theme_path},
                    )
                    items.append(item)

        return items

    def _load_plugin_commands(self) -> List[PaletteItem]:
        """加载插件命令"""
        items = []

        for name, action in self.action_manager.actions.items():
            if name.startswith("plugin."):
                shortcut = action.shortcut().toString()
                item = PaletteItem(
                    title=action.text(),
                    subtitle=shortcut,
                    category="插件",
                    action_name=name,
                )
                items.append(item)

        return items

    def _execute_item(self, item: PaletteItem):
        """执行选中的条目"""
        try:
            # 优先使用回调
            if item.callback:
                item.callback()
                return

            # 使用 action_name
            if item.action_name:
                action = self.action_manager.get(item.action_name)
                if action:
                    action.trigger()
                    return

            # 根据模式处理数据
            if self.mode == PaletteMode.FILE:
                self._execute_file_item(item)
            elif self.mode == PaletteMode.SYMBOL:
                self._execute_symbol_item(item)
            elif self.mode == PaletteMode.THEME:
                self._execute_theme_item(item)

        except Exception as e:
            print(f"[CommandPalette] 执行失败: {e}")
            try:
                bus.emit_status(f"执行失败: {e}", 3000, "error")
            except Exception:
                pass

    def _execute_file_item(self, item: PaletteItem):
        """执行文件切换"""
        data = item.data
        if not isinstance(data, dict):
            return

        if 'index' in data and self.tab_mgr:
            self.tab_mgr.setCurrentIndex(data['index'])
        elif 'filepath' in data:
            filepath = data['filepath']
            if os.path.exists(filepath) and self.tab_mgr:
                self.tab_mgr.open_file(filepath)

    def _execute_symbol_item(self, item: PaletteItem):
        """执行符号跳转"""
        data = item.data
        if not isinstance(data, dict) or 'line' not in data:
            return

        line = data['line']
        win = self.parent()
        if win and hasattr(win, 'tabs'):
            editor = win.tabs.currentWidget()
            if editor:
                try:
                    editor.setCursorPosition(line, 0)
                    editor.ensureLineVisible(line)
                    editor.setFocus()
                except Exception:
                    pass

    def _execute_theme_item(self, item: PaletteItem):
        """执行主题切换"""
        data = item.data
        if not isinstance(data, dict):
            return

        theme_path = data.get('theme_path')
        if theme_path and os.path.exists(theme_path):
            try:
                from infrastructure.theme_loader import ThemeLoader
                loader = ThemeLoader()
                theme = loader.load(theme_path)
                win = self.parent()
                if win and hasattr(win, 'tabs'):
                    for i in range(win.tabs.count()):
                        loader.apply(win.tabs.widget(i), theme)
                    qss = getattr(theme, 'qss', '')
                    if qss:
                        win.setStyleSheet(qss)
            except Exception as e:
                print(f"[CommandPalette] 应用主题失败: {e}")


# ============================================================
# 文件快速切换面板
# ============================================================
class FilePalette(CommandPalette):
    """文件快速切换面板（Ctrl+P）"""

    def __init__(self, action_manager: ActionManager,
                 tab_mgr, parent=None):
        super().__init__(
            action_manager, parent,
            mode=PaletteMode.FILE,
            tab_mgr=tab_mgr,
        )


# ============================================================
# 符号跳转面板
# ============================================================
class SymbolPalette(CommandPalette):
    """符号跳转面板（Ctrl+R）"""

    def __init__(self, action_manager: ActionManager,
                 tab_mgr, outline, parent=None):
        super().__init__(
            action_manager, parent,
            mode=PaletteMode.SYMBOL,
            tab_mgr=tab_mgr,
            outline=outline,
        )


# ============================================================
# 行号跳转面板
# ============================================================
class LineJumpPalette(BasePalette):
    """行号跳转面板（:数字）"""

    def __init__(self, parent=None):
        super().__init__(parent, PaletteMode.LINE)

        # 只显示提示
        self.list_widget.hide()

    def _get_prefix_text(self) -> str:
        return ":"

    def _get_placeholder(self) -> str:
        return "输入行号后回车跳转"

    def showEvent(self, event):
        """显示事件"""
        super().showEvent(event)

        # 隐藏列表
        self.list_widget.hide()

        # 调整大小
        self.setFixedHeight(100)

    def _on_text_changed(self, text: str):
        """输入变化"""
        num_str = text.lstrip(':')
        if num_str:
            try:
                line = int(num_str)
                self.status_label.setText(f"跳转到行 {line}")
            except ValueError:
                self.status_label.setText("无效行号")
        else:
            self.status_label.setText("输入行号")


# ============================================================
# 工厂函数
# ============================================================
def create_command_palette(action_manager: ActionManager,
                            parent=None,
                            tab_mgr=None,
                            outline=None) -> CommandPalette:
    """创建命令面板"""
    return CommandPalette(
        action_manager, parent,
        mode=PaletteMode.COMMAND,
        tab_mgr=tab_mgr,
        outline=outline,
    )


def create_file_palette(action_manager: ActionManager,
                         tab_mgr,
                         parent=None) -> FilePalette:
    """创建文件切换面板"""
    return FilePalette(action_manager, tab_mgr, parent)


def create_symbol_palette(action_manager: ActionManager,
                           tab_mgr, outline,
                           parent=None) -> SymbolPalette:
    """创建符号跳转面板"""
    return SymbolPalette(action_manager, tab_mgr, outline, parent)


def create_line_palette(parent=None) -> LineJumpPalette:
    """创建行号跳转面板"""
    return LineJumpPalette(parent)


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication, QMainWindow

    from app.actions import ActionManager, create_action

    app = QApplication(sys.argv)

    # 创建主窗口
    win = QMainWindow()
    win.setWindowTitle("CommandPalette 测试")
    win.resize(1000, 700)
    win.show()

    # 创建动作管理器
    mgr = ActionManager()

    # 创建一些测试动作
    def dummy():
        print("动作触发")

    create_action(win, "file.new", "新建文件", "Ctrl+N", dummy, mgr)
    create_action(win, "file.open", "打开文件", "Ctrl+O", dummy, mgr)
    create_action(win, "file.save", "保存文件", "Ctrl+S", dummy, mgr)
    create_action(win, "file.save_as", "另存为", "Ctrl+Shift+S", dummy, mgr)
    create_action(win, "edit.undo", "撤销", "Ctrl+Z", dummy, mgr)
    create_action(win, "edit.redo", "重做", "Ctrl+Y", dummy, mgr)
    create_action(win, "edit.copy", "复制", "Ctrl+C", dummy, mgr)
    create_action(win, "edit.paste", "粘贴", "Ctrl+V", dummy, mgr)
    create_action(win, "edit.cut", "剪切", "Ctrl+X", dummy, mgr)
    create_action(win, "edit.find", "查找", "Ctrl+F", dummy, mgr)
    create_action(win, "edit.replace", "替换", "Ctrl+H", dummy, mgr)
    create_action(win, "view.zoom_in", "放大", "Ctrl+=", dummy, mgr)
    create_action(win, "view.zoom_out", "缩小", "Ctrl+-", dummy, mgr)
    create_action(win, "tools.macro_record", "录制宏", "Ctrl+Shift+R", dummy, mgr)

    print(f"已注册 {len(mgr.actions)} 个动作")
    print()

    # 测试模糊匹配算法
    print("=== 测试模糊匹配 ===")
    test_cases = [
        ("save", "保存文件"),
        ("sf", "保存文件"),
        ("undo", "撤销"),
        ("zoom", "放大"),
        ("xyz", "保存"),
    ]

    for pattern, text in test_cases:
        matched, score = fuzzy_match(pattern.lower(), text.lower())
        print(f"  '{pattern}' -> '{text}': {matched} (score={score})")

    print()

    # 创建命令面板
    palette = CommandPalette(mgr, win)
    print(f"命令面板条目数: {len(palette.items)}")

    # 显示面板
    palette.center_on_parent()
    palette.exec()

    print()
    print("使用历史:")
    for title, (ts, count) in palette.get_usage_history().items():
        print(f"  {title}: {count} 次")

    print()
    print("测试完成。")
    sys.exit(0)