#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为通用面板组件模块，包含：
- SearchBar：单文件查找/替换工具栏
- ReplaceConfirmDialog：替换确认对话框
- GotoLineDialog：跳转到行对话框
- EncodingDialog：编码选择对话框
- LineEndingDialog：行尾符选择对话框
- ThemeChooserDialog：主题选择器
- InputDialog：通用输入对话框
- ProgressDialog：进度对话框
- MessageBar：消息提示条
- StatusIndicator：状态指示器
- InlineSearchPanel：内嵌搜索面板
"""

import os
import re
import time
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QEvent, QPoint, QSettings, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPalette,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QStyle,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.event_bus import SearchFinishedEvent, SearchStartedEvent, StatusMessageEvent, bus
from core.search import ReplaceEngine, SearchEngine, SearchMatch, SearchOptions, SearchResult


# ============================================================
# 常量
# ============================================================
# 搜索栏高度
SEARCH_BAR_HEIGHT = 38

# 搜索防抖延迟（毫秒）
SEARCH_DEBOUNCE_MS = 300

# 搜索历史最大长度
MAX_SEARCH_HISTORY = 30

# 常用编码
ENCODINGS = [
    ("UTF-8", "utf-8"),
    ("UTF-8 with BOM", "utf-8-sig"),
    ("GBK", "gbk"),
    ("GB2312", "gb2312"),
    ("GB18030", "gb18030"),
    ("Big5", "big5"),
    ("Shift-JIS", "shift_jis"),
    ("EUC-KR", "euc-kr"),
    ("ISO-8859-1", "iso-8859-1"),
    ("Windows-1252", "windows-1252"),
    ("UTF-16 LE", "utf-16-le"),
    ("UTF-16 BE", "utf-16-be"),
    ("ASCII", "ascii"),
]

# 行尾符
LINE_ENDINGS = [
    ("LF (\\n)", "\n"),
    ("CRLF (\\r\\n)", "\r\n"),
    ("CR (\\r)", "\r"),
]


# ============================================================
# 搜索方向枚举
# ============================================================
class SearchDirection(Enum):
    """搜索方向"""
    FORWARD = auto()
    BACKWARD = auto()


# ============================================================
# 搜索栏
# ============================================================
class SearchBar(QToolBar):
    """
    单文件查找/替换工具栏。

    功能:
    - 查找/替换输入
    - 正则/大小写/全词/转义选项
    - 上一个/下一个
    - 高亮全部
    - 替换/全部替换
    - 实时高亮（防抖）
    - 搜索历史
    - 匹配计数
    - 循环搜索提示

    信号:
        search_requested(str, SearchOptions): 搜索请求
        replace_requested(str, str, bool): 替换请求（查找, 替换, 全部）
        close_requested(): 关闭请求
    """

    search_requested = pyqtSignal(str, object)
    replace_requested = pyqtSignal(str, str, bool)
    close_requested = pyqtSignal()

    def __init__(self, main_window=None, parent=None):
        """
        参数:
            main_window: 主窗口（用于访问 tabs）
            parent: 父控件
        """
        super().__init__("搜索", parent)

        self.main_window = main_window
        self.setObjectName("SearchBar")
        self.setMovable(False)
        self.setFloatable(False)

        # 状态
        self._last_pattern = ""
        self._current_match_index = 0
        self._total_matches = 0
        self._search_options = SearchOptions()

        # 搜索历史
        self._search_history: List[str] = []
        self._replace_history: List[str] = []

        # 防抖定时器
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._do_highlight)

        # 加载历史
        self._load_history()

        # 构建 UI
        self._build_ui()

        # 应用样式
        self._apply_style()

    # --------------------------------------------------------
    # UI 构建
    # --------------------------------------------------------
    def _build_ui(self):
        """构建 UI"""
        # 查找输入
        find_label = QLabel("查找:")
        find_label.setStyleSheet("color: #d4d4d4; padding: 0 4px;")
        self.addWidget(find_label)

        self.pattern_edit = QLineEdit()
        self.pattern_edit.setPlaceholderText("搜索内容...")
        self.pattern_edit.setClearButtonEnabled(True)
        self.pattern_edit.setMinimumWidth(180)
        self.pattern_edit.setMaximumWidth(300)
        self.pattern_edit.textChanged.connect(self._on_pattern_changed)
        self.pattern_edit.returnPressed.connect(self._on_return_pressed)
        self.addWidget(self.pattern_edit)

        # 替换输入
        replace_label = QLabel("替换:")
        replace_label.setStyleSheet("color: #d4d4d4; padding: 0 4px;")
        self.addWidget(replace_label)

        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("替换为...")
        self.replace_edit.setClearButtonEnabled(True)
        self.replace_edit.setMinimumWidth(150)
        self.replace_edit.setMaximumWidth(250)
        self.replace_edit.returnPressed.connect(self._on_replace_pressed)
        self.addWidget(self.replace_edit)

        self.addSeparator()

        # 正则
        self.regex_cb = QCheckBox(".*")
        self.regex_cb.setToolTip("正则表达式")
        self.regex_cb.toggled.connect(self._on_option_changed)
        self.addWidget(self.regex_cb)

        # 大小写
        self.case_cb = QCheckBox("Aa")
        self.case_cb.setToolTip("区分大小写")
        self.case_cb.toggled.connect(self._on_option_changed)
        self.addWidget(self.case_cb)

        # 全词
        self.whole_word_cb = QCheckBox("W")
        self.whole_word_cb.setToolTip("全词匹配")
        self.whole_word_cb.toggled.connect(self._on_option_changed)
        self.addWidget(self.whole_word_cb)

        # 转义
        self.escape_cb = QCheckBox("\\")
        self.escape_cb.setToolTip("转义特殊字符")
        self.escape_cb.toggled.connect(self._on_option_changed)
        self.addWidget(self.escape_cb)

        self.addSeparator()

        # 上一个
        self.prev_btn = QToolButton()
        self.prev_btn.setText("↑")
        self.prev_btn.setToolTip("上一个 (Shift+Enter)")
        self.prev_btn.clicked.connect(self._on_prev_clicked)
        self.addWidget(self.prev_btn)

        # 下一个
        self.next_btn = QToolButton()
        self.next_btn.setText("↓")
        self.next_btn.setToolTip("下一个 (Enter)")
        self.next_btn.clicked.connect(self._on_next_clicked)
        self.addWidget(self.next_btn)

        # 高亮全部
        self.highlight_btn = QToolButton()
        self.highlight_btn.setText("◎")
        self.highlight_btn.setToolTip("高亮全部")
        self.highlight_btn.clicked.connect(self._on_highlight_clicked)
        self.addWidget(self.highlight_btn)

        self.addSeparator()

        # 替换
        self.replace_btn = QToolButton()
        self.replace_btn.setText("↻")
        self.replace_btn.setToolTip("替换当前")
        self.replace_btn.clicked.connect(self._on_replace_clicked)
        self.addWidget(self.replace_btn)

        # 全部替换
        self.replace_all_btn = QToolButton()
        self.replace_all_btn.setText("⇄")
        self.replace_all_btn.setToolTip("全部替换")
        self.replace_all_btn.clicked.connect(self._on_replace_all_clicked)
        self.addWidget(self.replace_all_btn)

        self.addSeparator()

        # 匹配计数
        self.match_label = QLabel("")
        self.match_label.setStyleSheet(
            "color: #7ec850; font-size: 11px; padding: 0 8px;"
        )
        self.match_label.setMinimumWidth(80)
        self.addWidget(self.match_label)

        self.addSeparator()

        # 关闭
        self.close_btn = QToolButton()
        self.close_btn.setText("✕")
        self.close_btn.setToolTip("关闭 (Esc)")
        self.close_btn.clicked.connect(self._on_close_clicked)
        self.addWidget(self.close_btn)

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QToolBar#SearchBar {
                background-color: #252526;
                border-top: 1px solid #3c3c3c;
                spacing: 2px;
                padding: 3px;
            }
            QToolBar#SearchBar QLabel {
                color: #d4d4d4;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 12px;
                selection-background-color: #094771;
            }
            QLineEdit:focus {
                border-color: #007acc;
            }
            QCheckBox {
                color: #d4d4d4;
                font-size: 11px;
                font-weight: bold;
                spacing: 2px;
                padding: 0 4px;
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
            QToolButton {
                background-color: transparent;
                color: #d4d4d4;
                border: none;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 14px;
                font-weight: bold;
                min-width: 22px;
            }
            QToolButton:hover {
                background-color: #3c3c3c;
            }
            QToolButton:pressed {
                background-color: #094771;
            }
            QToolButton:disabled {
                color: #666;
            }
        """)

    # --------------------------------------------------------
    # 输入事件
    # --------------------------------------------------------
    def _on_pattern_changed(self, text: str):
        """查找内容变化"""
        # 防抖触发高亮
        if self.main_window and hasattr(self.main_window, 'prefs'):
            if self.main_window.prefs.get("instant_search", True):
                self._debounce_timer.start()

    def _on_option_changed(self):
        """选项变化"""
        self._debounce_timer.start()

    def _on_return_pressed(self):
        """回车键"""
        modifiers = QApplication.keyboardModifiers()
        if modifiers & Qt.ShiftModifier:
            self._on_prev_clicked()
        else:
            self._on_next_clicked()

    def _on_replace_pressed(self):
        """替换输入框回车"""
        self._on_replace_clicked()

    # --------------------------------------------------------
    # 搜索操作
    # --------------------------------------------------------
    def _build_search_options(self) -> SearchOptions:
        """构建搜索选项"""
        return SearchOptions(
            pattern=self.pattern_edit.text(),
            is_regex=self.regex_cb.isChecked(),
            case_sensitive=self.case_cb.isChecked(),
            whole_word=self.whole_word_cb.isChecked(),
            escape_pattern=self.escape_cb.isChecked(),
        )

    def _on_next_clicked(self):
        """下一个"""
        self._search(SearchDirection.FORWARD)

    def _on_prev_clicked(self):
        """上一个"""
        self._search(SearchDirection.BACKWARD)

    def _search(self, direction: SearchDirection):
        """执行搜索"""
        pattern = self.pattern_edit.text()
        if not pattern:
            return

        # 记录历史
        self._add_search_history(pattern)

        # 构建选项
        options = self._build_search_options()

        # 发射信号
        self.search_requested.emit(pattern, options)

        # 获取当前编辑器
        if not self.main_window:
            return

        proxy = self.main_window.tabs.current_proxy()
        if not proxy:
            return

        try:
            # 在**编辑器缓冲区**里匹配（provider 只在保存时同步，
            # 会漏掉刚输入的文字 —— 见 EditorProxy._buffer_find_all 说明）
            spans = []
            try:
                spans = proxy._buffer_find_all(options)
            except Exception:
                spans = []

            if not spans:
                self._update_match_count(0, 0, False)
                self._show_message("未找到匹配", "warning")
                return

            pos = proxy.get_current_pos()
            forward = (direction == SearchDirection.FORWARD)

            # 在 Python 层找下一个 / 上一个
            match = None
            if forward:
                match = next((s for s in spans if s[0] > pos), None)
            else:
                match = next(
                    (s for s in reversed(spans) if s[1] <= pos), None
                )

            # 循环到另一端
            if match is None:
                match = spans[0] if forward else spans[-1]
                self._show_message("已从另一端继续搜索", "info")

            # 选中并居中
            proxy.set_selection(match[0], match[1])
            try:
                line = proxy.sc.SendScintilla(
                    proxy.sc.SCI_LINEFROMPOSITION, match[0]
                )
                proxy.sc.ensureLineVisible(line)
            except Exception:
                pass

            # 更新计数（显示 "1/总数"，未跟踪当前索引）
            self._update_match_count(1, len(spans), True)

        except Exception as e:
            print(f"[SearchBar] 搜索失败: {e}")

    def _do_highlight(self):
        """执行高亮（防抖后）"""
        pattern = self.pattern_edit.text()
        if not pattern:
            self._clear_highlight()
            return

        if not self.main_window:
            return

        proxy = self.main_window.tabs.current_proxy()
        if not proxy:
            return

        try:
            count = proxy.highlight_all(pattern)
            self._update_match_count(count, count, count > 0)
        except Exception as e:
            print(f"[SearchBar] 高亮失败: {e}")

    def _clear_highlight(self):
        """清除高亮"""
        if not self.main_window:
            return

        proxy = self.main_window.tabs.current_proxy()
        if proxy:
            try:
                proxy.clear_highlights()
            except Exception:
                pass

        self._update_match_count(0, 0, False)

    def _update_match_count(self, current: int, total: int, found: bool):
        """更新匹配计数"""
        if total == 0 and not found:
            self.match_label.setText("无匹配")
            self.match_label.setStyleSheet(
                "color: #f14c4c; font-size: 11px; padding: 0 8px;"
            )
        elif total > 0:
            self.match_label.setText(f"{current}/{total}")
            self.match_label.setStyleSheet(
                "color: #7ec850; font-size: 11px; padding: 0 8px;"
            )
        else:
            self.match_label.setText("")
            self.match_label.setStyleSheet(
                "color: #7ec850; font-size: 11px; padding: 0 8px;"
            )

    # --------------------------------------------------------
    # 替换操作
    # --------------------------------------------------------
    def _on_replace_clicked(self):
        """替换当前匹配"""
        pattern = self.pattern_edit.text()
        replace_text = self.replace_edit.text()

        if not pattern:
            return

        if not self.main_window:
            return

        proxy = self.main_window.tabs.current_proxy()
        if not proxy:
            return

        try:
            if not proxy.sc.hasSelectedText():
                self._search(SearchDirection.FORWARD)
                return

            # 检查选区是否匹配
            selected = proxy.get_selected_text()

            # 执行替换
            proxy.sc.replaceSelectedText(replace_text)

            # 记录历史
            self._add_replace_history(replace_text)

            # 继续搜索下一个
            self._search(SearchDirection.FORWARD)

        except Exception as e:
            print(f"[SearchBar] 替换失败: {e}")

    def _on_replace_all_clicked(self):
        """全部替换"""
        pattern = self.pattern_edit.text()
        replace_text = self.replace_edit.text()

        if not pattern:
            return

        if not self.main_window:
            return

        proxy = self.main_window.tabs.current_proxy()
        if not proxy:
            return

        try:
            # 在**编辑器缓冲区**里统计匹配（provider 是保存时的快照，
            # 会漏掉未保存的编辑 —— 见 EditorProxy._buffer_find_all 说明）
            options = self._build_search_options()
            spans = []
            try:
                spans = proxy._buffer_find_all(options)
            except Exception:
                spans = []

            if not spans:
                self._show_message("没有可替换的匹配", "info")
                return

            # 预览：从缓冲区文本取行号与行内容
            buffer_text = proxy.get_text() if hasattr(proxy, 'get_text') \
                else proxy.sc.text()
            preview_lines = []
            for start, _end in spans[:5]:
                line_no = buffer_text.encode("utf-8")[:start].count(b"\n") + 1
                text_lines = buffer_text.split("\n")
                line_text = (text_lines[line_no - 1]
                             if 0 < line_no <= len(text_lines) else "")
                preview_lines.append(
                    f"  行 {line_no}: {line_text.strip()[:60]}"
                )

            count = len(spans)
            preview = "\n".join(preview_lines)
            if count > 5:
                preview += f"\n  ... 及其他 {count - 5} 处"

            msg = (f"将替换 {count} 处匹配。\n\n"
                   f"{preview}\n\n"
                   f"替换为: {replace_text}\n\n"
                   f"是否继续？")

            reply = QMessageBox.question(
                self, "确认替换", msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply != QMessageBox.Yes:
                return

            # 执行替换 —— 直接在缓冲区上替换。
            #
            # 修复（审计用例 test_replace_all_reverts_editor_to_provider_snapshot）：
            #   原实现在 provider 快照上替换，再用
            #   `proxy.sc.setText(provider.read_text())` 覆盖编辑器 ——
            #   快照不含未保存的编辑，于是这些编辑被**静默丢弃**。
            #   现在走 replace_all_in_buffer，未保存内容得以保留。
            replaced = proxy.replace_all_in_buffer(
                pattern, replace_text,
                case_sensitive=getattr(options, 'case_sensitive', False),
                is_regex=getattr(options, 'is_regex', False),
                whole_word=getattr(options, 'whole_word', False),
            )

            # 记录历史
            self._add_replace_history(replace_text)

            # 清除高亮
            self._clear_highlight()

            # 状态提示
            self._show_message(f"已替换 {replaced} 处", "success")

        except Exception as e:
            print(f"[SearchBar] 全部替换失败: {e}")
            self._show_message(f"替换失败: {e}", "error")

    def _on_highlight_clicked(self):
        """高亮全部"""
        self._do_highlight()

    def _on_close_clicked(self):
        """关闭搜索栏"""
        self._clear_highlight()
        self.hide()
        self.close_requested.emit()

        # 焦点返回编辑器
        if self.main_window:
            proxy = self.main_window.tabs.current_proxy()
            if proxy:
                try:
                    proxy.sc.setFocus()
                except Exception:
                    pass

    # --------------------------------------------------------
    # 搜索历史
    # --------------------------------------------------------
    def _load_history(self):
        """加载历史"""
        try:
            settings = QSettings("QingCao", "SearchBar")

            history = settings.value("search_history", [])
            if isinstance(history, str):
                history = [history] if history else []
            self._search_history = list(history)[:MAX_SEARCH_HISTORY]

            replace_history = settings.value("replace_history", [])
            if isinstance(replace_history, str):
                replace_history = [replace_history] if replace_history else []
            self._replace_history = list(replace_history)[:MAX_SEARCH_HISTORY]

        except Exception:
            pass

    def _save_history(self):
        """保存历史"""
        try:
            settings = QSettings("QingCao", "SearchBar")
            settings.setValue(
                "search_history",
                self._search_history[:MAX_SEARCH_HISTORY]
            )
            settings.setValue(
                "replace_history",
                self._replace_history[:MAX_SEARCH_HISTORY]
            )
        except Exception:
            pass

    def _add_search_history(self, text: str):
        """添加搜索历史"""
        if not text:
            return

        if text in self._search_history:
            self._search_history.remove(text)

        self._search_history.insert(0, text)
        self._search_history = self._search_history[:MAX_SEARCH_HISTORY]
        self._save_history()

    def _add_replace_history(self, text: str):
        """添加替换历史"""
        if not text:
            return

        if text in self._replace_history:
            self._replace_history.remove(text)

        self._replace_history.insert(0, text)
        self._replace_history = self._replace_history[:MAX_SEARCH_HISTORY]
        self._save_history()

    def get_search_history(self) -> List[str]:
        """获取搜索历史"""
        return list(self._search_history)

    def get_replace_history(self) -> List[str]:
        """获取替换历史"""
        return list(self._replace_history)

    # --------------------------------------------------------
    # 显示
    # --------------------------------------------------------
    def show_and_focus(self, text: str = ""):
        """显示并聚焦"""
        self.show()

        if text:
            self.pattern_edit.setText(text)

        # 聚焦并全选
        self.pattern_edit.setFocus()
        self.pattern_edit.selectAll()

        # 如果有内容则触发高亮
        if self.pattern_edit.text():
            self._debounce_timer.start()

    def _show_message(self, message: str, level: str = "info"):
        """显示状态消息"""
        try:
            bus.emit_event(StatusMessageEvent(
                message=message, timeout=2000, level=level
            ))
        except Exception:
            pass

    def keyPressEvent(self, event):
        """键盘事件"""
        if event.key() == Qt.Key_Escape:
            self._on_close_clicked()
            return

        super().keyPressEvent(event)

    # --------------------------------------------------------
    # 调试
    # --------------------------------------------------------
    # C: SearchBar 主题刷新
    def refresh_theme(self, theme):
        """主题变更时刷新样式"""
        try:
            from infrastructure.theme_loader import adapt_qss_colors
            if not hasattr(self, '_original_qss') or not self._original_qss:
                self._original_qss = self.styleSheet()
            if self._original_qss:
                qss = adapt_qss_colors(self._original_qss, theme)
                self.setStyleSheet(qss)
        except Exception as e:
            print(f"[SearchBar] refresh_theme 失败: {e}")

    def dump(self) -> str:
        """导出搜索栏信息"""
        lines = ["SearchBar", "=" * 60]
        lines.append(f"查找: {self.pattern_edit.text()}")
        lines.append(f"替换: {self.replace_edit.text()}")
        lines.append(f"正则: {self.regex_cb.isChecked()}")
        lines.append(f"大小写: {self.case_cb.isChecked()}")
        lines.append(f"全词: {self.whole_word_cb.isChecked()}")
        lines.append(f"转义: {self.escape_cb.isChecked()}")
        lines.append(f"历史: {len(self._search_history)} 条")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<SearchBar pattern={self.pattern_edit.text()!r}>"


# ============================================================
# 替换确认对话框
# ============================================================
class ReplaceConfirmDialog(QDialog):
    """
    替换确认对话框。

    显示替换预览，让用户确认。
    """

    def __init__(self, pattern: str, replacement: str,
                 matches: List[SearchMatch], parent=None):
        super().__init__(parent)

        self.setWindowTitle("确认替换")
        self.resize(600, 400)

        self._pattern = pattern
        self._replacement = replacement
        self._matches = matches

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 信息
        info = QLabel(
            f"将替换 <b>{len(self._matches)}</b> 处匹配。"
        )
        info.setStyleSheet("font-size: 13px; padding: 8px;")
        layout.addWidget(info)

        # 预览
        preview_label = QLabel("预览:")
        layout.addWidget(preview_label)

        preview_edit = QPlainTextEdit()
        preview_edit.setReadOnly(True)

        preview_lines = []
        for match in self._matches[:50]:
            preview_lines.append(
                f"行 {match.line}: {match.line_text.strip()}"
            )
            preview_lines.append(f"  → {self._replacement}")

        if len(self._matches) > 50:
            preview_lines.append(f"\n... 及其他 {len(self._matches) - 50} 处")

        preview_edit.setPlainText("\n".join(preview_lines))
        layout.addWidget(preview_edit)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Yes | QDialogButtonBox.No
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


# ============================================================
# 跳转到行对话框
# ============================================================
class GotoLineDialog(QDialog):
    """
    跳转到行对话框。
    """

    def __init__(self, max_line: int, current_line: int = 1, parent=None):
        super().__init__(parent)

        self.setWindowTitle("跳转到行")
        self.setFixedSize(300, 120)

        self._max_line = max_line
        self._current_line = current_line

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QFormLayout(self)

        # 行号输入
        self.line_spin = QSpinBox()
        self.line_spin.setRange(1, max(1, self._max_line))
        self.line_spin.setValue(self._current_line)
        self.line_spin.selectAll()
        layout.addRow("行号:", self.line_spin)

        # 提示
        info = QLabel(f"范围: 1 - {self._max_line}")
        info.setStyleSheet("color: #888; font-size: 11px;")
        layout.addRow("", info)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_line(self) -> int:
        """获取选中的行号"""
        return self.line_spin.value()


# ============================================================
# 编码选择对话框
# ============================================================
class EncodingDialog(QDialog):
    """
    编码选择对话框。
    """

    def __init__(self, current_encoding: str = "utf-8", parent=None):
        super().__init__(parent)

        self.setWindowTitle("选择编码")
        self.resize(320, 400)

        self._current_encoding = current_encoding.lower()

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索编码...")
        self.search_edit.textChanged.connect(self._on_filter)
        layout.addWidget(self.search_edit)

        # 列表
        self.list_widget = QListWidget()

        current_row = 0
        for i, (display_name, enc_name) in enumerate(ENCODINGS):
            item = QListWidgetItem(f"{display_name}  ({enc_name})")
            item.setData(Qt.UserRole, enc_name)

            if enc_name == self._current_encoding:
                current_row = i
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            self.list_widget.addItem(item)

        self.list_widget.setCurrentRow(current_row)
        self.list_widget.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.list_widget)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_filter(self, text: str):
        """过滤编码列表"""
        text = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(text not in item.text().lower())

    def get_encoding(self) -> str:
        """获取选中的编码"""
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return self._current_encoding


# ============================================================
# 行尾符选择对话框
# ============================================================
class LineEndingDialog(QDialog):
    """
    行尾符选择对话框。
    """

    def __init__(self, current_eol: str = "\n", parent=None):
        super().__init__(parent)

        self.setWindowTitle("选择行尾符")
        self.setFixedSize(300, 220)

        self._current_eol = current_eol

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 说明
        info = QLabel("选择行尾符：")
        layout.addWidget(info)

        # 列表
        self.list_widget = QListWidget()

        current_row = 0
        for i, (display_name, eol_name) in enumerate(LINE_ENDINGS):
            item = QListWidgetItem(display_name)
            item.setData(Qt.UserRole, eol_name)

            if eol_name == self._current_eol:
                current_row = i
                font = item.font()
                font.setBold(True)
                item.setFont(font)

            self.list_widget.addItem(item)

        self.list_widget.setCurrentRow(current_row)
        self.list_widget.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.list_widget)

        # 提示
        hint = QLabel(
            "转换后文件将被标记为已修改，保存后生效。"
        )
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_eol(self) -> str:
        """获取选中的行尾符"""
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return self._current_eol


# ============================================================
# 主题选择对话框
# ============================================================
class ThemeChooserDialog(QDialog):
    """
    主题选择对话框。
    """

    def __init__(self, themes_dir: str, current_theme: str = "",
                 parent=None):
        super().__init__(parent)

        self.setWindowTitle("选择主题")
        self.resize(400, 500)

        self._themes_dir = themes_dir
        self._current_theme = current_theme
        self._selected_theme: Optional[str] = None

        self._build_ui()
        self._load_themes()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索主题...")
        self.search_edit.textChanged.connect(self._on_filter)
        layout.addWidget(self.search_edit)

        # 列表
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.accept)
        self.list_widget.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self.list_widget)

        # 预览
        self.preview_label = QLabel("选择主题以预览")
        self.preview_label.setStyleSheet(
            "background-color: #1e1e1e; color: #888; "
            "border: 1px solid #3c3c3c; padding: 8px; "
            "font-size: 12px;"
        )
        self.preview_label.setFixedHeight(60)
        layout.addWidget(self.preview_label)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_themes(self):
        """加载主题列表"""
        self.list_widget.clear()

        # 添加"跟随系统"选项
        system_item = QListWidgetItem("跟随系统")
        system_item.setData(Qt.UserRole, "__system__")
        self.list_widget.addItem(system_item)

        # 扫描主题目录
        if os.path.isdir(self._themes_dir):
            for filename in sorted(os.listdir(self._themes_dir)):
                if filename.endswith('.json'):
                    theme_name = os.path.splitext(filename)[0]
                    theme_path = os.path.join(self._themes_dir, filename)

                    item = QListWidgetItem(theme_name)
                    item.setData(Qt.UserRole, theme_path)

                    if theme_path == self._current_theme:
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
                        self.list_widget.setCurrentItem(item)

                    self.list_widget.addItem(item)

    def _on_filter(self, text: str):
        """过滤主题"""
        text = text.lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(text not in item.text().lower())

    def _on_selection(self):
        """选中项变化"""
        item = self.list_widget.currentItem()
        if item:
            theme_path = item.data(Qt.UserRole)
            if theme_path and theme_path != "__system__":
                self.preview_label.setText(
                    f"主题文件: {os.path.basename(theme_path)}"
                )
            else:
                self.preview_label.setText("跟随系统主题")

    def get_theme(self) -> Optional[str]:
        """获取选中的主题路径"""
        item = self.list_widget.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return None


# ============================================================
# 通用输入对话框
# ============================================================
class InputDialog(QDialog):
    """
    通用输入对话框。

    支持单行/多行文本输入。
    """

    def __init__(self, title: str, label: str,
                 default: str = "", multiline: bool = False,
                 parent=None):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.resize(400, 200 if multiline else 130)

        self._multiline = multiline

        self._build_ui(title, label, default)

    def _build_ui(self, title: str, label: str, default: str):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 标签
        if label:
            lbl = QLabel(label)
            layout.addWidget(lbl)

        # 输入
        if self._multiline:
            self.input_edit = QPlainTextEdit()
            self.input_edit.setPlainText(default)
        else:
            self.input_edit = QLineEdit()
            self.input_edit.setText(default)
            self.input_edit.selectAll()
            self.input_edit.returnPressed.connect(self.accept)

        layout.addWidget(self.input_edit)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 焦点
        self.input_edit.setFocus()

    def get_text(self) -> str:
        """获取输入文本"""
        if self._multiline:
            return self.input_edit.toPlainText()
        return self.input_edit.text()


# ============================================================
# 进度对话框
# ============================================================
class ProgressDialog(QDialog):
    """
    进度对话框。

    可取消的进度显示。
    """

    def __init__(self, title: str = "处理中",
                 maximum: int = 100, parent=None):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setFixedSize(400, 130)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowContextHelpButtonHint
        )

        self._cancelled = False

        self._build_ui(title, maximum)

    def _build_ui(self, title: str, maximum: int):
        """构建 UI"""
        layout = QVBoxLayout(self)

        # 消息
        self.message_label = QLabel(title)
        self.message_label.setStyleSheet("font-size: 13px;")
        layout.addWidget(self.message_label)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, maximum)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # 状态
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.status_label)

        # 取消按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self._on_cancel)
        layout.addWidget(buttons)

    def _on_cancel(self):
        """取消"""
        self._cancelled = True
        self.reject()

    def set_value(self, value: int):
        """设置进度值"""
        self.progress_bar.setValue(value)

    def set_maximum(self, maximum: int):
        """设置最大值"""
        self.progress_bar.setMaximum(maximum)

    def set_message(self, message: str):
        """设置消息"""
        self.message_label.setText(message)

    def set_status(self, status: str):
        """设置状态"""
        self.status_label.setText(status)

    def is_cancelled(self) -> bool:
        """是否已取消"""
        return self._cancelled

    def increment(self, delta: int = 1):
        """增加进度"""
        self.progress_bar.setValue(
            self.progress_bar.value() + delta
        )


# ============================================================
# 消息提示条
# ============================================================
class MessageBar(QFrame):
    """
    消息提示条。

    在编辑器顶部显示临时提示信息。
    """

    # 消息级别
    LEVEL_INFO = "info"
    LEVEL_SUCCESS = "success"
    LEVEL_WARNING = "warning"
    LEVEL_ERROR = "error"

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setVisible(False)
        self.setFixedHeight(32)

        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self.hide)

        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        # 图标
        self.icon_label = QLabel()
        self.icon_label.setFixedWidth(20)
        layout.addWidget(self.icon_label)

        # 消息
        self.message_label = QLabel()
        self.message_label.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred
        )
        layout.addWidget(self.message_label, 1)

        # 关闭按钮
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.clicked.connect(self._on_close)
        layout.addWidget(close_btn)

    def _on_close(self):
        """关闭"""
        self.hide()
        self.closed.emit()

    def show_message(self, message: str, level: str = "info",
                      auto_hide_ms: int = 3000):
        """
        显示消息。

        参数:
            message: 消息内容
            level: 级别（info/success/warning/error）
            auto_hide_ms: 自动隐藏延迟（0 表示不自动隐藏）
        """
        self.message_label.setText(message)

        # 根据级别设置样式
        if level == self.LEVEL_SUCCESS:
            bg = "#1e5f3f"
            fg = "#ffffff"
            icon = "✓"
        elif level == self.LEVEL_WARNING:
            bg = "#8f5f1e"
            fg = "#ffffff"
            icon = "⚠"
        elif level == self.LEVEL_ERROR:
            bg = "#8f1e1e"
            fg = "#ffffff"
            icon = "✕"
        else:
            bg = "#1e3f5f"
            fg = "#ffffff"
            icon = "ℹ"

        self.setStyleSheet(f"""
            MessageBar {{
                background-color: {bg};
                border: none;
                border-radius: 4px;
            }}
            MessageBar QLabel {{
                color: {fg};
                font-size: 12px;
            }}
            MessageBar QToolButton {{
                background-color: transparent;
                color: {fg};
                border: none;
                font-size: 12px;
            }}
            MessageBar QToolButton:hover {{
                background-color: rgba(255, 255, 255, 40);
                border-radius: 3px;
            }}
        """)

        self.icon_label.setText(icon)
        self.setVisible(True)

        # 自动隐藏
        if auto_hide_ms > 0:
            self._auto_hide_timer.start(auto_hide_ms)


# ============================================================
# 状态指示器
# ============================================================
class StatusIndicator(QLabel):
    """
    状态指示器。

    显示一个彩色圆点表示状态。
    """

    STATE_IDLE = "idle"
    STATE_RUNNING = "running"
    STATE_SUCCESS = "success"
    STATE_WARNING = "warning"
    STATE_ERROR = "error"

    def __init__(self, parent=None):
        super().__init__("●", parent)

        self.setFixedSize(16, 16)
        self.setAlignment(Qt.AlignCenter)

        self._state = self.STATE_IDLE
        self._update_style()

    def set_state(self, state: str, tooltip: str = ""):
        """设置状态"""
        self._state = state
        if tooltip:
            self.setToolTip(tooltip)
        self._update_style()

    def _update_style(self):
        """更新样式"""
        colors = {
            self.STATE_IDLE: "#888888",
            self.STATE_RUNNING: "#f0ad4e",
            self.STATE_SUCCESS: "#7ec850",
            self.STATE_WARNING: "#f0ad4e",
            self.STATE_ERROR: "#f14c4c",
        }

        color = colors.get(self._state, "#888888")
        self.setStyleSheet(f"color: {color}; font-size: 14px;")


# ============================================================
# 内嵌搜索面板
# ============================================================
class InlineSearchPanel(QWidget):
    """
    内嵌搜索面板。

    可在编辑器内部显示的浮动搜索框。
    """

    search_requested = pyqtSignal(str, object)
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedHeight(36)
        self.setVisible(False)

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        """构建 UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # 输入框
        self.pattern_edit = QLineEdit()
        self.pattern_edit.setPlaceholderText("搜索...")
        self.pattern_edit.setClearButtonEnabled(True)
        layout.addWidget(self.pattern_edit, 1)

        # 上一个
        prev_btn = QToolButton()
        prev_btn.setText("↑")
        prev_btn.setFixedSize(24, 24)
        prev_btn.clicked.connect(lambda: self._on_search(False))
        layout.addWidget(prev_btn)

        # 下一个
        next_btn = QToolButton()
        next_btn.setText("↓")
        next_btn.setFixedSize(24, 24)
        next_btn.clicked.connect(lambda: self._on_search(True))
        layout.addWidget(next_btn)

        # 关闭
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self._on_close)
        layout.addWidget(close_btn)

        # 回车
        self.pattern_edit.returnPressed.connect(
            lambda: self._on_search(True)
        )

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            InlineSearchPanel {
                background-color: #2d2d2d;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
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
            QToolButton {
                background-color: transparent;
                color: #d4d4d4;
                border: none;
                border-radius: 3px;
                font-size: 12px;
            }
            QToolButton:hover {
                background-color: #3c3c3c;
            }
        """)

    def _on_search(self, forward: bool):
        """执行搜索"""
        pattern = self.pattern_edit.text()
        if pattern:
            options = SearchOptions(pattern=pattern)
            self.search_requested.emit(pattern, options)

    def _on_close(self):
        """关闭"""
        self.setVisible(False)
        self.close_requested.emit()

    def show_and_focus(self):
        """显示并聚焦"""
        self.setVisible(True)
        self.pattern_edit.setFocus()
        self.pattern_edit.selectAll()

    def keyPressEvent(self, event):
        """键盘事件"""
        if event.key() == Qt.Key_Escape:
            self._on_close()
            return
        super().keyPressEvent(event)


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)

    # 创建主窗口
    win = QMainWindow()
    win.setWindowTitle("Panels 测试")
    win.resize(900, 700)
    win.show()

    # 测试 SearchBar
    print("=== 测试 SearchBar ===")
    search_bar = SearchBar()
    win.addToolBar(Qt.BottomToolBarArea, search_bar)
    search_bar.show()

    print(search_bar.dump())
    print()

    # 测试状态指示器
    print("=== 测试 StatusIndicator ===")
    indicator = StatusIndicator()
    win.statusBar().addPermanentWidget(indicator)
    indicator.set_state("running", "处理中...")

    # 测试消息提示条
    print("=== 测试 MessageBar ===")
    msg_bar = MessageBar(win)
    win.statusBar().addWidget(msg_bar)

    def show_message():
        msg_bar.show_message("这是一条测试消息", "success", 3000)

    QTimer.singleShot(1000, show_message)

    # 测试对话框
    def test_dialogs():
        print()
        print("=== 测试 GotoLineDialog ===")
        dlg = GotoLineDialog(1000, 100)
        if dlg.exec():
            print(f"选中行: {dlg.get_line()}")

        print()
        print("=== 测试 EncodingDialog ===")
        dlg = EncodingDialog("utf-8")
        if dlg.exec():
            print(f"选中编码: {dlg.get_encoding()}")

        print()
        print("=== 测试 LineEndingDialog ===")
        dlg = LineEndingDialog("\n")
        if dlg.exec():
            print(f"选中行尾: {repr(dlg.get_eol())}")

        print()
        print("=== 测试 InputDialog ===")
        dlg = InputDialog("测试", "请输入内容:", "默认值")
        if dlg.exec():
            print(f"输入: {dlg.get_text()}")

        app.quit()

    # 3 秒后测试对话框
    QTimer.singleShot(3000, test_dialogs)

    sys.exit(app.exec())