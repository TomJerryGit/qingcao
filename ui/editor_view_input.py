# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""输入/交互职责（v2.24 从 editor_view.py 拆出）。"""

from ui.editor_view_common import *  # noqa: F401,F403,F405


class EditorInputMixin:
    def keyPressEvent(self, event: QKeyEvent):
        """
        按键事件处理。

        智能处理:
        - 括号/引号自动包裹选区
        - 右括号/引号跳过
        - Tab/Shift+Tab 缩进
        - Home 键智能跳转
        - Ctrl+Backspace 按词删除
        - Backspace 删除成对符号
        - Esc 清除多光标
        - 代码片段触发
        - F9 切换断点（D3）
        """
        # D3: F9 切换当前行断点。
        # 刻意**放在 Vim 模式之前**，且刻意**不注册全局 QShortcut**：
        #   * 多标签场景下，每个编辑器各有一个全局 QShortcut 会造成
        #     Qt 的 ambiguous shortcut（P8-1 的教训）；
        #   * 放在 keyPressEvent 里天然只作用于**获得焦点的**编辑器。
        if event.key() == Qt.Key_F9 and not event.modifiers():
            self._toggle_breakpoint_at_line(self.getCursorPosition()[0])
            event.accept()
            return

        # Vim 模式：优先让 VimMode 处理
        # （VimMode.handle_key 返回 True 表示已消化，直接 return）
        vim = getattr(self, "_vim_mode", None)
        if vim is not None and getattr(vim, "enabled", False):
            try:
                if vim.handle_key(event):
                    return
            except Exception as e:
                print(f"[EditorWidget] VimMode 处理失败: {e}")

        key = event.key()
        text = event.text()
        modifiers = event.modifiers()

        # Esc：清除多光标
        if key == Qt.Key_Escape:
            if self.SendScintilla(QsciScintilla.SCI_GETSELECTIONS) > 1:
                self.proxy.clear_multi_cursors()
                return

        # Ctrl+Space：强制弹出本地补全（P10）
        if key == Qt.Key_Space and modifiers == Qt.ControlModifier:
            if self.trigger_local_completion(force=True):
                return

        # 括号/引号包裹选区
        if text in PAIRS and self.hasSelectedText():
            self._wrap_selection(text)
            return

        # 右括号/引号跳过
        if text in REVERSE_PAIRS and not modifiers:
            if self._try_skip_close(text):
                return

        # Tab 键
        if key == Qt.Key_Tab and not modifiers:
            if self._handle_tab():
                return
            # 默认插入 Tab
            self.SendScintilla(QsciScintilla.SCI_TAB)
            return

        # Shift+Tab 反缩进
        if key == Qt.Key_Backtab or (key == Qt.Key_Tab and modifiers == Qt.ShiftModifier):
            self.SendScintilla(QsciScintilla.SCI_BACKTAB)
            return

        # Home 键智能跳转
        if key == Qt.Key_Home and not modifiers:
            self._smart_home()
            return

        # Ctrl+Backspace 按词删除
        if key == Qt.Key_Backspace and modifiers == Qt.ControlModifier:
            self._delete_word_left()
            return

        # Backspace 删除成对符号
        if key == Qt.Key_Backspace and not modifiers:
            if self._try_delete_pair():
                return

        # 默认处理
        super().keyPressEvent(event)

    def _wrap_selection(self, open_char: str):
        """
        用成对符号包裹选区。

        修复说明（P1-1）:
            - QScintilla 在 UTF-8 模式下位置为字节偏移，
              而 Python str 的 len() 是字符数，两者对中文不一致。
            - 这里使用 encode('utf-8') 后的字节长度重新计算选区。
        """
        close_char = PAIRS[open_char]

        sel_start = self.SendScintilla(QsciScintilla.SCI_GETSELECTIONSTART)
        sel_end = self.SendScintilla(QsciScintilla.SCI_GETSELECTIONEND)
        selected = self.selectedText()

        # 构建包裹后的文本
        wrapped = open_char + selected + close_char

        # 替换
        self.SendScintilla(QsciScintilla.SCI_REPLACESEL, wrapped.encode("utf-8"))

        # 重新选中原内容（跳过左右符号）
        # 注意：QScintilla 位置是字节偏移，必须用 encode 后的长度
        open_len = len(open_char.encode("utf-8"))
        sel_len = len(selected.encode("utf-8"))

        new_start = sel_start + open_len
        new_end = new_start + sel_len
        self.SendScintilla(QsciScintilla.SCI_SETSELECTIONSTART, new_start)
        self.SendScintilla(QsciScintilla.SCI_SETSELECTIONEND, new_end)

    def _try_skip_close(self, close_char: str) -> bool:
        """尝试跳过右符号"""
        pos = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)
        length = self.SendScintilla(QsciScintilla.SCI_GETLENGTH)

        if pos >= length:
            return False

        next_char = chr(self.SendScintilla(QsciScintilla.SCI_GETCHARAT, pos))

        if next_char == close_char:
            self.SendScintilla(QsciScintilla.SCI_GOTOPOS, pos + 1)
            return True

        return False

    def _handle_tab(self) -> bool:
        """
        处理 Tab 键。

        返回:
            True 表示已处理，False 表示使用默认行为
        """
        # 有选区时缩进所有行
        if self.hasSelectedText():
            self.SendScintilla(QsciScintilla.SCI_TAB)
            return True

        # 无选区，检查代码片段触发
        line, col = self.getCursorPosition()
        line_text = self.text(line)

        before = line_text[:col]
        word = ""
        for i in range(len(before) - 1, -1, -1):
            ch = before[i]
            if ch.isalnum() or ch == "_":
                word = ch + word
            else:
                break

        if not word:
            return False

        # 修复说明（P1-4）: 优先查询用户片段 SnippetManager
        try:
            from core.snippets import get_snippet_manager

            mgr = get_snippet_manager()
            snippet = mgr.get(word)
            if snippet:
                body = snippet.body
                if isinstance(body, list):
                    body = "\n".join(body)
                if body:
                    word_len_bytes = len(word.encode("utf-8"))
                    cur = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)
                    self.SendScintilla(QsciScintilla.SCI_SETSELECTIONSTART, cur - word_len_bytes)
                    self.SendScintilla(QsciScintilla.SCI_SETSELECTIONEND, cur)
                    self.SendScintilla(QsciScintilla.SCI_REPLACESEL, body.encode("utf-8"))
                    return True
        except Exception as e:
            print(f"[EditorWidget] SnippetManager 触发失败: {e}")

        # 回退到内置片段
        if word in self.proxy.SNIPPETS:
            try:
                self.proxy.expand_snippet(word)
                return True
            except Exception:
                pass

        return False

    def _smart_home(self):
        """
        Home 键智能循环跳转。

        修复说明（P1-2）:
            - 原实现中 `line_start + indent` 直接把字符长度当作
              字节偏移，遇到含 tab 或全角空格的行时位置会有偏差。
            - 修复为使用行首缩进部分的 UTF-8 字节长度。
        """
        line, col = self.getCursorPosition()
        line_text = self.text(line)

        # 计算行首非空白位置（字符数）
        stripped = line_text.lstrip()
        indent = len(line_text) - len(stripped)

        # 获取行首位置（字节偏移）
        line_start = self.SendScintilla(QsciScintilla.SCI_POSITIONFROMLINE, line)

        # 计算行首缩进的字节长度
        indent_bytes = len(line_text[:indent].encode("utf-8"))

        # P1-B4: col 是字节偏移，必须与 indent_bytes 比较（而非字符数 indent）
        # 否则全角空格（U+3000，UTF-8 下 3 字节）行为异常
        if col > indent_bytes:
            # 跳到行首非空白
            target = line_start + indent_bytes
        elif col == indent_bytes and indent_bytes > 0:
            # 跳到绝对行首
            target = line_start
        elif col == 0:
            # 循环回到行首非空白
            target = line_start + indent_bytes
        else:
            # 默认跳到行首
            target = line_start

        self.SendScintilla(QsciScintilla.SCI_GOTOPOS, target)

    def _delete_word_left(self):
        """按词删除（向左）"""
        pos = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)

        if pos <= 0:
            return

        # 使用 Scintilla 内置的按词删除
        # SCI_DELWORDLEFT 会删除到前一个词边界
        start = self.SendScintilla(QsciScintilla.SCI_WORDSTARTPOSITION, pos, True)

        if start < pos:
            self.SendScintilla(QsciScintilla.SCI_DELETERANGE, start, pos - start)
        else:
            # 回退到删除单个字符
            self.SendScintilla(QsciScintilla.SCI_DELETEBACK)

    def _try_delete_pair(self) -> bool:
        """
        尝试删除成对符号。

        修复说明（P1-3）:
            - SCI_GETCHARAT 返回的是字节值（0-255）。
              若光标处是中文字符的某个字节，chr() 会返回奇怪字符，
              极少数情况下可能恰好与括号字符相同。
            - 这里增加 ASCII 范围判断（0x20 < byte < 0x7F），
              只在纯 ASCII 括号场景下处理。
        """
        pos = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)

        if pos <= 0:
            return False

        length = self.SendScintilla(QsciScintilla.SCI_GETLENGTH)

        # 获取光标前后字符的字节值
        prev_byte = self.SendScintilla(QsciScintilla.SCI_GETCHARAT, pos - 1)

        if pos >= length:
            return False

        next_byte = self.SendScintilla(QsciScintilla.SCI_GETCHARAT, pos)

        # 只处理纯 ASCII 可打印字符
        if not (0x20 < prev_byte < 0x7F) or not (0x20 < next_byte < 0x7F):
            return False

        prev_char = chr(prev_byte)
        next_char = chr(next_byte)

        # 检查是否为成对符号
        if prev_char in PAIRS and PAIRS[prev_char] == next_char:
            # 同时删除两个字符
            self.SendScintilla(QsciScintilla.SCI_DELETERANGE, pos - 1, 2)
            return True

        return False

    # ========================================================
    # 字符输入回调
    # ========================================================

    def _on_char_added(self, char_code: int):
        """字符输入后的回调

        P1-4: 引号自动闭合 + 尊重偏好

        原实现用 `if char != close_char` 跳过所有引号（因为
        PAIRS['"'] == '"'），导致：
          - 输入 " 不会自动补 "
          - 而偏好设置里 auto_close_quotes 是打开的

        新实现：
          - 引号也自动闭合
          - 尊重 auto_close_brackets / auto_close_quotes 偏好
          - 引号闭合前检查前一个字符，避免在 don't 里误闭合
        """
        try:
            char = chr(char_code)

            # P10: 输入标识符字符后自动弹出本地补全
            # （关键字 + 文档词 + 词频排序，均来自 LocalCompleter）
            if char.isascii() and (char.isalnum() or char == "_"):
                self.trigger_local_completion()

            if char not in PAIRS:
                return
            if self.hasSelectedText():
                return

            close_char = PAIRS[char]

            if char == close_char:
                # 引号场景
                if not self.prefs.get("auto_close_quotes", True):
                    return
                # 前面是标识符字符时不闭合（如 don't）
                pos = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)
                if pos >= 2:
                    prev_byte = self.SendScintilla(QsciScintilla.SCI_GETCHARAT, pos - 2)
                    if 0x20 < prev_byte < 0x7F:
                        prev_char = chr(prev_byte)
                        if prev_char.isalnum() or prev_char == "_":
                            return
            else:
                # 括号场景
                if not self.prefs.get("auto_close_brackets", True):
                    return

            # 插入闭合符号
            pos = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)
            self.SendScintilla(QsciScintilla.SCI_INSERTTEXT, pos, close_char.encode("utf-8"))
            # 光标保持在原位置
            self.SendScintilla(QsciScintilla.SCI_GOTOPOS, pos)
        except Exception:
            pass

    # ========================================================
    # 光标与拖尾
    # ========================================================

    def _on_cursor_moved(self, line: int, col: int):
        """光标移动回调"""
        # 光标拖尾
        if self._cursor_trail_enabled:
            self._update_cursor_trail()

    def _update_cursor_trail(self):
        """更新光标拖尾"""
        try:
            pos = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)
            now = time.time()

            self._cursor_trail_points.append((pos, now))

            # 清除旧指示器
            length = self.SendScintilla(QsciScintilla.SCI_GETLENGTH)
            self.SendScintilla(QsciScintilla.SCI_SETINDICATORCURRENT, INDICATOR_CURSOR_TRAIL)
            self.SendScintilla(QsciScintilla.SCI_INDICATORCLEARRANGE, 0, length)

            # 绘制新拖尾
            valid = []
            for p, t in self._cursor_trail_points:
                if now - t < CURSOR_TRAIL_DURATION:
                    self.SendScintilla(QsciScintilla.SCI_INDICATORFILLRANGE, p, 1)
                    valid.append((p, t))
            self._cursor_trail_points = valid

        except Exception:
            pass

    # ========================================================
    # 缩进彩虹线
    # ========================================================

    def set_rainbow_enabled(self, enabled: bool):
        """启用/禁用缩进彩虹线"""
        self._rainbow_enabled = enabled
        self.viewport().update()

    def contextMenuEvent(self, event: QContextMenuEvent):
        """右键上下文菜单"""
        menu = QMenu(self)

        # 撤销/重做
        proxy = self.proxy
        if proxy:
            undo_act = menu.addAction("↩ 撤销")
            undo_act.setEnabled(proxy.can_undo())
            undo_act.triggered.connect(proxy.undo)

            redo_act = menu.addAction("↪ 重做")
            redo_act.setEnabled(proxy.can_redo())
            redo_act.triggered.connect(proxy.redo)

        menu.addSeparator()

        # 剪切/复制/粘贴
        has_selection = self.hasSelectedText()

        cut_act = menu.addAction("✂ 剪切")
        cut_act.setEnabled(has_selection)
        cut_act.triggered.connect(self.cut)

        copy_act = menu.addAction("📋 复制")
        copy_act.setEnabled(has_selection)
        copy_act.triggered.connect(self.copy)

        paste_act = menu.addAction("📋 粘贴")
        paste_act.triggered.connect(self.paste)

        menu.addSeparator()

        # 选区操作
        if has_selection:
            select_next = menu.addAction("🔷 选中下一个相同项")
            select_next.triggered.connect(proxy.select_next_occurrence)

            calc_act = menu.addAction("🧮 计算表达式")
            calc_act.triggered.connect(proxy.eval_expression)

            comment_act = menu.addAction("💬 注释/取消注释")
            comment_act.triggered.connect(proxy.toggle_line_comment)

            menu.addSeparator()

            upper_act = menu.addAction("🔠 转为大写")
            upper_act.triggered.connect(proxy.to_upper)

            lower_act = menu.addAction("🔡 转为小写")
            lower_act.triggered.connect(proxy.to_lower)

            toggle_case = menu.addAction("🔤 大小写切换")
            toggle_case.triggered.connect(proxy.toggle_case)

            menu.addSeparator()

        # 列编辑器（核心功能）
        #
        # 与 Edit 菜单「列编辑器…」(Alt+Shift+I) 走**同一个** API
        # （ui/column_editor_dialog.show_column_editor）：
        # 在矩形选区（SC_SEL_RECTANGLE）/ 多光标 / 当前选区的多行上
        # 逐行插入文本或递增数字，整次编辑只产生一条撤销命令。
        col_act = menu.addAction("📊 列编辑器…")
        col_act.triggered.connect(self.open_column_editor)

        # 行操作
        line_ops = menu.addMenu("📝 行操作")
        line_ops.addAction("上移行", proxy.move_line_up)
        line_ops.addAction("下移行", proxy.move_line_down)
        line_ops.addAction("复制行", proxy.duplicate_line)
        line_ops.addAction("删除行", proxy.delete_line)

        # 书签
        line, _ = self.getCursorPosition()
        is_bookmarked = bool(self.markersAtLine(line) & (1 << MARKER_BOOKMARK))
        bookmark_text = "🔖 移除书签" if is_bookmarked else "🔖 添加书签"

        bookmark_act = menu.addAction(bookmark_text)
        bookmark_act.triggered.connect(proxy.toggle_bookmark)

        # 断点（D3）：右键菜单入口，与 F9 / 装订线单击等价
        is_breakpoint = bool(self.markersAtLine(line) & (1 << MARKER_BREAKPOINT))
        bp_text = "🔴 移除断点 (F9)" if is_breakpoint else "🔴 添加断点 (F9)"
        bp_act = menu.addAction(bp_text)
        bp_act.triggered.connect(
            lambda _checked=False, ln=line: self._toggle_breakpoint_at_line(ln)
        )

        menu.addSeparator()

        # 查找
        find_act = menu.addAction("🔍 查找...")
        find_act.triggered.connect(self._trigger_find)

        goto_line = menu.addAction("📍 跳转到行...")
        goto_line.triggered.connect(self._trigger_goto_line)

        menu.addSeparator()

        # 插入日期时间
        datetime_act = menu.addAction("📅 插入日期时间")
        datetime_act.triggered.connect(proxy.insert_datetime)

        # 清理
        clean_menu = menu.addMenu("🧹 清理")
        clean_menu.addAction("清除行尾空白", proxy.trim_trailing_whitespace)
        clean_menu.addAction("删除空行", proxy.remove_blank_lines)

        menu.addSeparator()

        # 全选
        select_all = menu.addAction("全选")
        select_all.triggered.connect(self.selectAll)

        # v2.4：插件编辑器右键菜单贡献 + 代码操作入口
        try:
            win = self.window()
            collector = getattr(win, "collect_editor_context_actions", None)
            if callable(collector):
                entries = collector(self) or []
                if entries or getattr(win, "_plugin_code_action_providers", None):
                    menu.addSeparator()
                for entry in entries:
                    label = entry.get("label") or "插件操作"
                    callback = entry.get("callback")
                    act = menu.addAction(label)
                    if callable(callback):
                        act.triggered.connect(lambda _checked=False, f=callback: f())
                if getattr(win, "_plugin_code_action_providers", None):
                    ca = menu.addAction("💡 代码操作…")
                    ca.triggered.connect(lambda: win.show_plugin_code_actions(self))
        except Exception as e:
            print(f"[EditorWidget] 插件右键菜单注入失败: {e}")

        # 显示菜单
        menu.exec_(event.globalPos())

    # ========================================================
    # 插件扩展点 v2.4：hover / 装饰
    # ========================================================

    def event(self, event):
        """hover：把插件 hover 提供者的文本作为工具提示（v2.4）"""
        try:
            if event.type() == QEvent.ToolTip:
                text = self._plugin_hover_text()
                if text:
                    QToolTip.showText(event.globalPos(), text, self)
                    return True
        except Exception:
            pass
        return super().event(event)

    def _plugin_hover_text(self) -> str:
        """收集插件 hover 文本（无提供者/异常时返回空串）"""
        try:
            win = self.window()
            collector = getattr(win, "collect_plugin_hover", None)
            if not callable(collector):
                return ""
            from PyQt5.QtGui import QCursor

            local = self.mapFromGlobal(QCursor.pos())
            sci_pos = self.SendScintilla(QsciScintilla.SCI_POSITIONFROMPOINT, local.x(), local.y())
            if sci_pos is None or sci_pos < 0:
                return ""
            line = self.SendScintilla(QsciScintilla.SCI_LINEFROMPOSITION, sci_pos)
            line_start = self.SendScintilla(QsciScintilla.SCI_POSITIONFROMLINE, line)
            col = max(0, sci_pos - line_start)
            return (
                collector(self._completion_key(), line, col, language=self._completion_language())
                or ""
            )
        except Exception:
            return ""

    def add_plugin_decoration(self, start_line: int, end_line: int, color: str = "#FFCC00") -> bool:
        """给行区间加插件装饰（背景色块，不修改文本）"""
        try:
            from PyQt5.QtGui import QColor

            if not color:
                return False
            start_line = max(0, int(start_line))
            end_line = max(start_line, int(end_line))
            end_line = min(end_line, max(0, self.lines() - 1))
            self.setIndicatorDrawUnder(True, INDICATOR_PLUGIN)
            self.setIndicatorForegroundColor(QColor(color), INDICATOR_PLUGIN)
            self.fillIndicatorRange(start_line, 0, end_line, 0x7FFFFFFF, INDICATOR_PLUGIN)
            return True
        except Exception as e:
            print(f"[EditorWidget] 插件装饰失败: {e}")
            return False

    def _trigger_find(self):
        """触发查找面板"""
        win = self.window()
        if hasattr(win, "show_search"):
            win.show_search()

    def _trigger_goto_line(self):
        """触发跳转到行"""
        from PyQt5.QtWidgets import QInputDialog

        total_lines = self.SendScintilla(QsciScintilla.SCI_GETLINECOUNT)
        line, ok = QInputDialog.getInt(self, "跳转到行", "行号:", 1, 1, total_lines)
        if ok:
            self.setCursorPosition(line - 1, 0)
            self.ensureLineVisible(line - 1)

    # ========================================================
    # 拖放支持
    # ========================================================

    def dragEnterEvent(self, event: QDragEnterEvent):
        """拖入事件"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent):
        """放下事件"""
        if not event.mimeData().hasUrls():
            super().dropEvent(event)
            return

        urls = event.mimeData().urls()

        for url in urls:
            if url.isLocalFile():
                filepath = url.toLocalFile()
                if os.path.isfile(filepath):
                    self.file_dropped.emit(filepath)

        event.acceptProposedAction()

    # ========================================================
    # 焦点事件
    # ========================================================

    def focusInEvent(self, event):
        """获得焦点"""
        super().focusInEvent(event)
        self.focus_received.emit()

    # ========================================================
    # 快捷键
    # ========================================================

    def copy(self):
        """重写复制，无选区时忽略"""
        if self.hasSelectedText():
            super().copy()

    def cut(self):
        """重写剪切，无选区时忽略"""
        if self.hasSelectedText():
            super().cut()

    # ========================================================
    # 便捷方法
    # ========================================================
