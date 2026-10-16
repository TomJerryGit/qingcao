# -*- coding: utf-8 -*-
"""Vim 模式"""
import re
from enum import Enum, auto

from PyQt5.QtCore import QObject, pyqtSignal


class VimState(Enum):
    NORMAL = auto()
    INSERT = auto()
    VISUAL = auto()
    VISUAL_LINE = auto()
    COMMAND = auto()
    REPLACE = auto()


class VimMode(QObject):
    """Vim 模式控制器"""

    state_changed = pyqtSignal(str)  # 新状态名
    status_message = pyqtSignal(str)  # 状态栏消息

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.state = VimState.NORMAL
        self.command_buffer = ""
        self.register = ""  # 剪贴板寄存器
        self.register_is_line = False
        self.last_search = ""
        self.count_buffer = ""  # 数字前缀
        self.enabled = False

        # v2 补全: 多寄存器 + 操作符/文本对象状态
        self.registers = {'"': ''}
        self._pending_operator = None
        self._operator_count = 1
        self._pending_register = None
        self._pending_textobj_prefix = None
        # B(v2): 独立"等待寄存器名"状态
        self._waiting_for_register = False

    def set_enabled(self, enabled):
        """启用/禁用"""
        self.enabled = enabled
        if enabled:
            self.state = VimState.NORMAL
            self._on_state_enter()
            self._set_caret_block()
        else:
            self.state = VimState.INSERT
            self._set_caret_line()

    def _set_caret_block(self):
        """设置块状光标（Normal 模式）"""
        try:
            self.editor.SendScintilla(self.editor.SCI_SETCARETSTYLE, 2)
        except Exception:
            pass

    def _set_caret_line(self):
        """设置线状光标（Insert 模式）"""
        try:
            self.editor.SendScintilla(self.editor.SCI_SETCARETSTYLE, 1)
        except Exception:
            pass

    def _get_proxy(self):
        """取与当前编辑器关联的 EditorProxy（没有则 None）

        `VimMode` 只持有 QScintilla 控件，因此通过
        `EditorProxy.__init__` 挂上的反向引用找回代理。
        """
        try:
            return getattr(self.editor, '_qc_editor_proxy', None)
        except Exception:
            return None

    def _vim_undo(self):
        """Vim 的 `u`：撤销

        修复（审计用例 TestVimUndo 复现）：
            原先调用 `self.editor.undo()` —— QScintilla **内置**撤销栈。
            而 `EditorProxy` 在 `_connect_signals` 里执行了
            `SCI_SETUNDOCOLLECTION(0)` 禁用内置栈，因此 Vim 的撤销
            **静默无效**，同时 `handle_key` 返回 True 吞掉了按键，
            用户完全得不到反馈。

            现在改走 `EditorProxy.undo()` —— 它才是记录编辑的那一个，
            并且会把 `scintilla` 传给 `UndoManager`（否则命令只是被弹栈、
            **不会真正执行**：`UndoManager.undo()` 的 scintilla 参数为
            None 时只做栈操作）。
        """
        proxy = self._get_proxy()
        if proxy is not None and hasattr(proxy, 'undo'):
            try:
                proxy.undo()
                return
            except Exception:
                pass
        try:
            self.editor.undo()
        except Exception:
            pass

    def _vim_redo(self):
        """Vim 的 `Ctrl+R`：重做（同样走 EditorProxy，见 `_vim_undo`）"""
        proxy = self._get_proxy()
        if proxy is not None and hasattr(proxy, 'redo'):
            try:
                proxy.redo()
                return
            except Exception:
                pass
        try:
            self.editor.redo()
        except Exception:
            pass

    def handle_key(self, event) -> bool:
        """
        处理按键。

        返回:
            True 表示已处理（应该阻止默认行为）
        """
        if not self.enabled:
            return False

        from PyQt5.QtCore import Qt
        key = event.key()
        text = event.text()
        modifiers = event.modifiers()

        # 任何状态都允许 Ctrl 组合键（除非被 vim 拦截）
        if modifiers & Qt.ControlModifier:
            # Normal 模式拦截 Ctrl+R（重做，vim 中是重做）
            if self.state == VimState.NORMAL and key == Qt.Key_R:
                self._vim_redo()
                return True
            return False

        # 命令模式处理
        if self.state == VimState.COMMAND:
            return self._handle_command(key, text, modifiers)

        # Normal / Visual 模式
        if self.state in (VimState.NORMAL, VimState.VISUAL,
                          VimState.VISUAL_LINE):
            return self._handle_normal(key, text, modifiers)

        # Insert 模式：Esc 切换到 Normal
        if self.state == VimState.INSERT:
            if key == Qt.Key_Escape:
                self._switch_to(VimState.NORMAL)
                return True
            return False

        return False

    def _handle_normal(self, key, text, modifiers) -> bool:
        """处理 Normal 模式按键（v2: 支持操作符 + 文本对象 + 寄存器）"""
        from PyQt5.QtCore import Qt

        # ==== A3: v2 操作符 + 文本对象 ====
        if self._pending_textobj_prefix is not None:
            return self._handle_textobj(text)

        if self._pending_operator is not None:
            return self._handle_after_operator(key, text)

        # B(v2): 等待寄存器名输入
        if self._waiting_for_register:
            self._waiting_for_register = False
            if text and (text.isalnum() or
                          text in ('"', '+', '-', '*', '0', '_')):
                self._pending_register = text
                return True
            self._pending_register = None
            self.status_message.emit("")
            return True

        if (text and text.isdigit()
                and not (text == "0" and not self.count_buffer)):
            self.count_buffer += text
            self.status_message.emit("计数: " + self.count_buffer)
            return True

        count = int(self.count_buffer) if self.count_buffer else 1
        self.count_buffer = ""

        # 寄存器前缀
        if text == '"':
            self._waiting_for_register = True
            self.status_message.emit('"')
            return True

        # 操作符前缀
        if text in ('d', 'c', 'y', '>', '<'):
            self._pending_operator = text
            self._operator_count = count
            self.status_message.emit(text)
            return True

        # ===== 原有按键 =====
        if text == 'h' or key == Qt.Key_Left:
            self._move_cursor(-count, 0); return True
        if text == 'j' or key == Qt.Key_Down:
            self._move_cursor(0, count); return True
        if text == 'k' or key == Qt.Key_Up:
            self._move_cursor(0, -count); return True
        if text == 'l' or key == Qt.Key_Right:
            self._move_cursor(count, 0); return True

        if text == 'w':
            for _ in range(count): self._move_word_forward()
            return True
        if text == 'b':
            for _ in range(count): self._move_word_backward()
            return True
        if text == 'e':
            for _ in range(count): self._move_word_end()
            return True

        if text == '0':
            self._goto_line_start(); return True
        if text == '$':
            self._goto_line_end(); return True

        # 修复 B4：先检查 gg
        # 原实现 if text == 'g' 提前 return，command_buffer 判断
        # 永远走不到，gg 命令完全失效。
        if self.command_buffer == 'g' and text == 'g':
            self.command_buffer = ""
            self._goto_line(0); return True
        if text == 'g':
            self.command_buffer = 'g'
            self.status_message.emit("g...")
            return True
        if text == 'G':
            line_count = self.editor.SendScintilla(
                self.editor.SCI_GETLINECOUNT
            )
            self._goto_line(line_count - 1)
            return True

        if text == 'i':
            self._switch_to(VimState.INSERT); return True
        if text == 'a':
            self._move_cursor(1, 0)
            self._switch_to(VimState.INSERT); return True
        if text == 'I':
            self._goto_line_start()
            self._switch_to(VimState.INSERT); return True
        if text == 'A':
            self._goto_line_end()
            self._switch_to(VimState.INSERT); return True
        if text == 'o':
            self._open_line_below()
            self._switch_to(VimState.INSERT); return True
        if text == 'O':
            self._open_line_above()
            self._switch_to(VimState.INSERT); return True

        if text == 'x':
            for _ in range(count):
                self._delete_char_forward()
            return True
        if text == 'X':
            for _ in range(count):
                self._delete_char_backward()
            return True

        if text == 'p':
            self._paste_after(); return True
        if text == 'P':
            self._paste_before(); return True

        if text == 'u':
            for _ in range(count):
                self._vim_undo()
            return True

        if text == 'r':
            self._switch_to(VimState.REPLACE); return True

        if text == 'v':
            self._switch_to(VimState.VISUAL); return True
        if text == 'V':
            self._switch_to(VimState.VISUAL_LINE); return True

        if text == '/':
            self._switch_to(VimState.COMMAND)
            self.command_buffer = "/"
            self.status_message.emit("搜索...")
            return True
        if text == '?':
            self._switch_to(VimState.COMMAND)
            self.command_buffer = "?"
            self.status_message.emit("搜索...")
            return True

        if text == 'n':
            for _ in range(count):
                self._search_next()
            return True
        if text == 'N':
            for _ in range(count):
                self._search_prev()
            return True

        if text == ':':
            self._switch_to(VimState.COMMAND)
            self.command_buffer = ":"
            self.status_message.emit(":")
            return True

        if key == Qt.Key_Escape:
            self.command_buffer = ""
            self.count_buffer = ""
            self.status_message.emit("")
            return True

        return False

    # ============================================================
    # A3: v2 操作符 / 文本对象 / 寄存器
    # ============================================================
    def _handle_after_operator(self, key, text) -> bool:
        from PyQt5.QtCore import Qt
        op = self._pending_operator
        count = self._operator_count

        if text and text.isdigit():
            self.count_buffer += text
            self._operator_count = int(self.count_buffer)
            return True

        if text == op:
            if op in ('d', 'c', 'y'):
                for _ in range(count):
                    self._apply_line_operator(op)
            elif op in ('>', '<'):
                for _ in range(count):
                    self._indent_line(op == '>')
            self._clear_pending()
            return True

        if text in ('i', 'a'):
            self._pending_textobj_prefix = text
            self.status_message.emit(op + text)
            return True

        rng = self._resolve_motion(text, key, count)
        if rng is None:
            self._clear_pending()
            return True

        start, end = rng
        self._apply_operator(op, start, end)
        self._clear_pending()
        return True

    def _handle_textobj(self, text) -> bool:
        prefix = self._pending_textobj_prefix
        self._pending_textobj_prefix = None
        op = self._pending_operator

        if not text:
            self._clear_pending()
            return True

        rng = None
        if text in ('w', 'W'):
            rng = self._textobj_word(prefix == 'a')
        elif text in ('"', "'", '`'):
            rng = self._textobj_quote(text, prefix == 'a')
        elif text in ('(', ')', 'b'):
            rng = self._textobj_bracket('(', ')', prefix == 'a')
        elif text in ('[', ']'):
            rng = self._textobj_bracket('[', ']', prefix == 'a')
        elif text in ('{', '}', 'B'):
            rng = self._textobj_bracket('{', '}', prefix == 'a')
        elif text in ('<', '>'):
            rng = self._textobj_bracket('<', '>', prefix == 'a')

        if rng is None or rng[0] is None:
            self._clear_pending()
            return True

        if op:
            self._apply_operator(op, rng[0], rng[1])
        self._clear_pending()
        return True

    def _clear_pending(self):
        self._pending_operator = None
        self._operator_count = 1
        self._pending_register = None
        self._pending_textobj_prefix = None
        self._waiting_for_register = False
        self.count_buffer = ""
        self.status_message.emit("")

    def _resolve_motion(self, text, key, count):
        from PyQt5.QtCore import Qt
        pos = self._get_pos()
        length = self._get_length()

        if text == 'w':
            end = pos
            for _ in range(count):
                end = self._find_word_forward(end)
            return pos, end
        if text == 'b':
            start = pos
            for _ in range(count):
                start = self._find_word_backward(start)
            return start, pos
        if text == 'e':
            end = pos
            for _ in range(count):
                end = self._find_word_end(end)
            return pos, min(end + 1, length)
        if text == '$':
            line, _ = self.editor.getCursorPosition()
            end = self.editor.SendScintilla(
                self.editor.SCI_GETLINEENDPOSITION, line
            )
            return pos, end
        if text == '0':
            line, _ = self.editor.getCursorPosition()
            start = self.editor.SendScintilla(
                self.editor.SCI_POSITIONFROMLINE, line
            )
            return start, pos
        if text == 'G':
            return pos, length
        if text == 'g' and self.command_buffer == 'g':
            self.command_buffer = ""
            return 0, pos
        if text == 'g':
            self.command_buffer = 'g'
            return None
        return None

    def _textobj_word(self, include_space: bool):
        pos = self._get_pos()
        start = self.editor.SendScintilla(
            self.editor.SCI_WORDSTARTPOSITION, pos, True
        )
        end = self.editor.SendScintilla(
            self.editor.SCI_WORDENDPOSITION, pos, True
        )
        if include_space:
            length = self._get_length()
            while end < length:
                ch = self.editor.SendScintilla(
                    self.editor.SCI_GETCHARAT, end
                )
                if ch not in (0x20, 0x09, 0x0A, 0x0D):
                    break
                end += 1
        return start, end

    def _textobj_quote(self, quote: str, include_quote: bool):
        pos = self._get_pos()
        line, _ = self.editor.getCursorPosition()
        line_start = self.editor.SendScintilla(
            self.editor.SCI_POSITIONFROMLINE, line
        )
        line_text = self.editor.text(line)
        col_in_line = pos - line_start

        left_idx = -1
        for i in range(col_in_line - 1, -1, -1):
            if line_text[i] == quote:
                left_idx = i
                break

        right_idx = -1
        for i in range(col_in_line, len(line_text)):
            if line_text[i] == quote:
                right_idx = i
                break

        if left_idx < 0 or right_idx < 0:
            return None, None

        if include_quote:
            return (line_start + left_idx, line_start + right_idx + 1)
        return (line_start + left_idx + 1, line_start + right_idx)

    def _textobj_bracket(self, open_ch: str, close_ch: str,
                          include_bracket: bool):
        pos = self._get_pos()
        length = self._get_length()

        depth = 0
        open_pos = -1
        for i in range(pos, -1, -1):
            ch = chr(self.editor.SendScintilla(
                self.editor.SCI_GETCHARAT, i
            ))
            if ch == close_ch:
                depth += 1
            elif ch == open_ch:
                depth -= 1
                if depth < 0:
                    open_pos = i
                    break
        if open_pos < 0:
            return None, None

        depth = 0
        close_pos = -1
        for i in range(open_pos, length):
            ch = chr(self.editor.SendScintilla(
                self.editor.SCI_GETCHARAT, i
            ))
            if ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    close_pos = i
                    break
        if close_pos < 0:
            return None, None

        if include_bracket:
            return open_pos, close_pos + 1
        return open_pos + 1, close_pos

    def _apply_operator(self, op: str, start: int, end: int):
        if start is None or end is None or start >= end:
            return

        text = self.editor.text()[start:end]
        reg = self._pending_register or '"'
        if reg:
            self.registers[reg] = text
            self.registers['"'] = text
            self.register = text  # v3: 同步旧属性
            self.register_is_line = False

        if op == 'y':
            self.editor.SendScintilla(self.editor.SCI_GOTOPOS, start)
        elif op == 'd':
            self.editor.SendScintilla(
                self.editor.SCI_DELETERANGE, start, end - start
            )
        elif op == 'c':
            self.editor.SendScintilla(
                self.editor.SCI_DELETERANGE, start, end - start
            )
            self._switch_to(VimState.INSERT)

    def _apply_line_operator(self, op: str):
        line, _ = self.editor.getCursorPosition()
        start = self.editor.SendScintilla(
            self.editor.SCI_POSITIONFROMLINE, line
        )
        end = self.editor.SendScintilla(
            self.editor.SCI_GETLINEENDPOSITION, line
        )
        total = self._get_length()
        has_nl = end < total

        if op == 'y':
            end_with = end + 1 if has_nl else end
            text = self.editor.text()[start:end_with]
            reg = self._pending_register or '"'
            if reg:
                self.registers[reg] = text
                self.registers['"'] = text
                self.register = text  # v3: 同步旧属性
                self.register_is_line = True
            self.editor.SendScintilla(self.editor.SCI_GOTOPOS, start)
        elif op == 'd':
            del_len = end - start + (1 if has_nl else 0)
            self.editor.SendScintilla(
                self.editor.SCI_DELETERANGE, start, del_len
            )
        elif op == 'c':
            line_text = self.editor.text(line)
            stripped = line_text.lstrip()
            indent = len(line_text) - len(stripped)
            indent_bytes = len(line_text[:indent].encode('utf-8'))
            del_start = start + indent_bytes
            del_len = end - del_start
            if del_len > 0:
                self.editor.SendScintilla(
                    self.editor.SCI_DELETERANGE, del_start, del_len
                )
            self.editor.SendScintilla(
                self.editor.SCI_GOTOPOS, del_start
            )
            self._switch_to(VimState.INSERT)

    def _indent_line(self, increase: bool):
        if increase:
            self.editor.SendScintilla(self.editor.SCI_TAB)
        else:
            self.editor.SendScintilla(self.editor.SCI_BACKTAB)

    def _get_pos(self) -> int:
        return self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)

    def _get_length(self) -> int:
        return self.editor.SendScintilla(self.editor.SCI_GETLENGTH)

    def _find_word_forward(self, pos: int) -> int:
        length = self._get_length()
        try:
            new_pos = self.editor.SendScintilla(
                self.editor.SCI_WORDRIGHT, pos, True
            )
        except Exception:
            new_pos = self.editor.SendScintilla(
                self.editor.SCI_WORDRIGHTEND, pos, True
            )
        return min(max(new_pos, pos + 1), length)

    def _find_word_backward(self, pos: int) -> int:
        try:
            return self.editor.SendScintilla(
                self.editor.SCI_WORDLEFT, pos, True
            )
        except Exception:
            return self.editor.SendScintilla(
                self.editor.SCI_WORDSTARTPOSITION, pos, True
            )

    def _find_word_end(self, pos: int) -> int:
        return self.editor.SendScintilla(
            self.editor.SCI_WORDENDPOSITION, pos, True
        )

    def _search_prev(self):
        if not self.last_search:
            return
        pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
        target = self.last_search.encode('utf-8')
        self.editor.SendScintilla(self.editor.SCI_SETTARGETSTART, 0)
        self.editor.SendScintilla(self.editor.SCI_SETTARGETEND, pos)
        found = self.editor.SendScintilla(
            self.editor.SCI_SEARCHINTARGET, len(target), target
        )
        if found >= 0:
            last_found = found
            while found >= 0:
                last_found = found
                self.editor.SendScintilla(
                    self.editor.SCI_SETTARGETSTART, found + 1
                )
                self.editor.SendScintilla(
                    self.editor.SCI_SETTARGETEND, pos
                )
                found = self.editor.SendScintilla(
                    self.editor.SCI_SEARCHINTARGET,
                    len(target), target
                )
            self.editor.SendScintilla(
                self.editor.SCI_GOTOPOS, last_found
            )


    def _handle_command(self, key, text, modifiers) -> bool:
        """处理命令模式"""
        from PyQt5.QtCore import Qt

        # 回车执行
        if key in (Qt.Key_Return, Qt.Key_Enter):
            cmd = self.command_buffer
            self.command_buffer = ""
            self._execute_command(cmd)
            return True

        # Esc 取消
        if key == Qt.Key_Escape:
            self.command_buffer = ""
            self._switch_to(VimState.NORMAL)
            self.status_message.emit("")
            return True

        # 退格
        if key == Qt.Key_Backspace:
            if len(self.command_buffer) > 1:
                self.command_buffer = self.command_buffer[:-1]
                self.status_message.emit(self.command_buffer)
            else:
                self._switch_to(VimState.NORMAL)
                self.status_message.emit("")
            return True

        # 普通字符
        if text and text.isprintable():
            self.command_buffer += text
            self.status_message.emit(self.command_buffer)
            return True

        return False

    def _execute_command(self, cmd):
        """执行命令"""
        if cmd.startswith('/'):
            # 搜索
            pattern = cmd[1:]
            if pattern:
                self.last_search = pattern
                self.editor.highlight_all(pattern)
                # 跳转到第一个匹配
                self._search_next()
            self._switch_to(VimState.NORMAL)
            return

        if cmd == ':w':
            self.editor.window().save_file() \
                if hasattr(self.editor.window(), 'save_file') else None
            self._switch_to(VimState.NORMAL)
            return

        if cmd == ':q':
            self.editor.window()._close_current_tab() \
                if hasattr(self.editor.window(), '_close_current_tab') else None
            self._switch_to(VimState.NORMAL)
            return

        if cmd == ':wq':
            if hasattr(self.editor.window(), 'save_file'):
                self.editor.window().save_file()
            if hasattr(self.editor.window(), '_close_current_tab'):
                self.editor.window()._close_current_tab()
            self._switch_to(VimState.NORMAL)
            return

        # 数字跳转
        if cmd[1:].isdigit():
            line = int(cmd[1:]) - 1
            self._goto_line(line)
            self._switch_to(VimState.NORMAL)
            return

        self.status_message.emit("未知命令: " + cmd)
        self._switch_to(VimState.NORMAL)

    def _switch_to(self, state):
        """切换状态"""
        old_state = self.state
        self.state = state

        if state == VimState.INSERT:
            self._set_caret_line()
        else:
            self._set_caret_block()

        self.state_changed.emit(state.name)
        if state != old_state:
            self._on_state_enter()

    def _on_state_enter(self):
        """进入状态"""
        names = {
            VimState.NORMAL: "-- 普通 --",
            VimState.INSERT: "-- 插入 --",
            VimState.VISUAL: "-- 可视 --",
            VimState.VISUAL_LINE: "-- 可视行 --",
            VimState.COMMAND: "-- 命令 --",
        }
        self.status_message.emit(names.get(self.state, ""))

    # ========== 编辑操作 ==========
    def _delete_char_forward(self):
        pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
        self.editor.SendScintilla(self.editor.SCI_DELETERANGE, pos, 1)

    def _delete_char_backward(self):
        pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
        if pos > 0:
            self.editor.SendScintilla(self.editor.SCI_DELETERANGE, pos - 1, 1)

    def _delete_line(self):
        line, _ = self.editor.getCursorPosition()
        start = self.editor.SendScintilla(
            self.editor.SCI_POSITIONFROMLINE, line
        )
        end = self.editor.SendScintilla(
            self.editor.SCI_GETLINEENDPOSITION, line
        )
        # 包含换行符
        length = end - start
        total = self.editor.SendScintilla(self.editor.SCI_GETLENGTH)
        if end < total:
            length += 1
        self.editor.SendScintilla(self.editor.SCI_DELETERANGE, start, length)

    def _yank_line(self):
        line, _ = self.editor.getCursorPosition()
        start = self.editor.SendScintilla(
            self.editor.SCI_POSITIONFROMLINE, line
        )
        end = self.editor.SendScintilla(
            self.editor.SCI_GETLINEENDPOSITION, line
        )
        text = self.editor.text()[start:end]
        self.register = text
        self.register_is_line = True
        self.status_message.emit("已复制行")

    def _paste_after(self):
        # v3: 统一从 self.registers['"'] 读
        # 原实现读 self.register，但 v2 起 yank 写入 registers['"']，
        # 导致 yy 后 p 无效。
        text = self.registers.get('"') or self.register
        if not text:
            return
        if self.register_is_line or text.endswith('\n'):
            # 行粘贴：在下一行插入
            line, _ = self.editor.getCursorPosition()
            end = self.editor.SendScintilla(
                self.editor.SCI_GETLINEENDPOSITION, line
            )
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, end,
                ("\n" + text.rstrip('\n')).encode('utf-8')
            )
        else:
            pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, pos + 1,
                text.encode('utf-8')
            )

    def _paste_before(self):
        # v3: 统一从 self.registers['"'] 读
        text = self.registers.get('"') or self.register
        if not text:
            return
        if self.register_is_line or text.endswith('\n'):
            line, _ = self.editor.getCursorPosition()
            start = self.editor.SendScintilla(
                self.editor.SCI_POSITIONFROMLINE, line
            )
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, start,
                (text.rstrip('\n') + "\n").encode('utf-8')
            )
        else:
            pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, pos,
                text.encode('utf-8')
            )

    def _open_line_below(self):
        line, _ = self.editor.getCursorPosition()
        end = self.editor.SendScintilla(
            self.editor.SCI_GETLINEENDPOSITION, line
        )
        self.editor.SendScintilla(
            self.editor.SCI_INSERTTEXT, end, b"\n"
        )
        self.editor.SendScintilla(self.editor.SCI_GOTOLINE, line + 1)

    def _open_line_above(self):
        line, _ = self.editor.getCursorPosition()
        start = self.editor.SendScintilla(
            self.editor.SCI_POSITIONFROMLINE, line
        )
        self.editor.SendScintilla(
            self.editor.SCI_INSERTTEXT, start, b"\n"
        )

    # ========== 移动 ==========
    def _move_cursor(self, dx, dy):
        line, col = self.editor.getCursorPosition()
        self.editor.setCursorPosition(max(0, line + dy), max(0, col + dx))

    def _move_word_forward(self):
        # A2: 用 SCI_WORDRIGHT 替代不存在的 SCI_WORDRIGHTPOSITION
        # （Scintilla 没有 SCI_WORDRIGHTPOSITION，PyQt5 也不导出）
        pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
        # 优先用 SCI_WORDRIGHT 一步到位
        try:
            new_pos = self.editor.SendScintilla(
                self.editor.SCI_WORDRIGHT, pos, True
            )
        except Exception:
            # 回退：用 WORDRIGHTEND 再走一步
            new_pos = self.editor.SendScintilla(
                self.editor.SCI_WORDRIGHTEND, pos, True
            )
            if new_pos <= pos:
                new_pos = pos + 1
        if new_pos > pos:
            self.editor.SendScintilla(
                self.editor.SCI_GOTOPOS, new_pos
            )

    def _move_word_backward(self):
        pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
        self.editor.SendScintilla(
            self.editor.SCI_WORDSTARTPOSITION, pos, True
        )
        new_pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
        if new_pos == pos:
            self.editor.SendScintilla(
                self.editor.SCI_WORDLEFTPOSITION, pos, True
            )

    def _move_word_end(self):
        pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
        self.editor.SendScintilla(
            self.editor.SCI_WORDENDPOSITION, pos, True
        )

    def _goto_line(self, line):
        self.editor.setCursorPosition(line, 0)
        self.editor.ensureLineVisible(line)

    def _goto_line_start(self):
        line, _ = self.editor.getCursorPosition()
        self.editor.setCursorPosition(line, 0)

    def _goto_line_end(self):
        line, _ = self.editor.getCursorPosition()
        end = self.editor.SendScintilla(
            self.editor.SCI_GETLINEENDPOSITION, line
        )
        start = self.editor.SendScintilla(
            self.editor.SCI_POSITIONFROMLINE, line
        )
        self.editor.setCursorPosition(line, end - start)

    def _search_next(self):
        # A(v2): 从 pos+1 开始，避免命中当前匹配
        if self.last_search:
            pos = self.editor.SendScintilla(
                self.editor.SCI_GETCURRENTPOS
            )
            target = self.last_search.encode('utf-8')
            length = self.editor.SendScintilla(
                self.editor.SCI_GETLENGTH
            )
            start = pos + 1
            if start >= length:
                # 循环到开头
                start = 0
            self.editor.SendScintilla(
                self.editor.SCI_SETTARGETSTART, start
            )
            self.editor.SendScintilla(
                self.editor.SCI_SETTARGETEND, length
            )
            found = self.editor.SendScintilla(
                self.editor.SCI_SEARCHINTARGET, len(target), target
            )
            if found < 0 and start > 0:
                # 到末尾未找到 → 从头再搜一次
                self.editor.SendScintilla(
                    self.editor.SCI_SETTARGETSTART, 0
                )
                self.editor.SendScintilla(
                    self.editor.SCI_SETTARGETEND, start
                )
                found = self.editor.SendScintilla(
                    self.editor.SCI_SEARCHINTARGET,
                    len(target), target
                )
            if found >= 0:
                self.editor.SendScintilla(
                    self.editor.SCI_GOTOPOS, found
                )