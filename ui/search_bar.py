# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""搜索栏（v2.24 拆出）。"""

from ui.panels_common import *


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
        self.match_label.setStyleSheet("color: #7ec850; font-size: 11px; padding: 0 8px;")
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
        if self.main_window and hasattr(self.main_window, "prefs"):
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
            forward = direction == SearchDirection.FORWARD

            # 在 Python 层找下一个 / 上一个
            match = None
            if forward:
                match = next((s for s in spans if s[0] > pos), None)
            else:
                match = next((s for s in reversed(spans) if s[1] <= pos), None)

            # 循环到另一端
            if match is None:
                match = spans[0] if forward else spans[-1]
                self._show_message("已从另一端继续搜索", "info")

            # 选中并居中
            proxy.set_selection(match[0], match[1])
            try:
                line = proxy.sc.SendScintilla(proxy.sc.SCI_LINEFROMPOSITION, match[0])
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
            self.match_label.setStyleSheet("color: #f14c4c; font-size: 11px; padding: 0 8px;")
        elif total > 0:
            self.match_label.setText(f"{current}/{total}")
            self.match_label.setStyleSheet("color: #7ec850; font-size: 11px; padding: 0 8px;")
        else:
            self.match_label.setText("")
            self.match_label.setStyleSheet("color: #7ec850; font-size: 11px; padding: 0 8px;")

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
            buffer_text = proxy.get_text() if hasattr(proxy, "get_text") else proxy.sc.text()
            preview_lines = []
            for start, _end in spans[:5]:
                line_no = buffer_text.encode("utf-8")[:start].count(b"\n") + 1
                text_lines = buffer_text.split("\n")
                line_text = text_lines[line_no - 1] if 0 < line_no <= len(text_lines) else ""
                preview_lines.append(f"  行 {line_no}: {line_text.strip()[:60]}")

            count = len(spans)
            preview = "\n".join(preview_lines)
            if count > 5:
                preview += f"\n  ... 及其他 {count - 5} 处"

            msg = f"将替换 {count} 处匹配。\n\n{preview}\n\n替换为: {replace_text}\n\n是否继续？"

            reply = QMessageBox.question(
                self, "确认替换", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
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
                pattern,
                replace_text,
                case_sensitive=getattr(options, "case_sensitive", False),
                is_regex=getattr(options, "is_regex", False),
                whole_word=getattr(options, "whole_word", False),
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
            settings.setValue("search_history", self._search_history[:MAX_SEARCH_HISTORY])
            settings.setValue("replace_history", self._replace_history[:MAX_SEARCH_HISTORY])
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
            bus.emit_event(StatusMessageEvent(message=message, timeout=2000, level=level))
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

            if not hasattr(self, "_original_qss") or not self._original_qss:
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
