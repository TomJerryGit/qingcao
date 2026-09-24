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
                self.editor.redo()
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
        """处理 Normal 模式按键"""
        from PyQt5.QtCore import Qt

        # 数字前缀
        if text and text.isdigit() and not (text == "0" and not self.count_buffer):
            self.count_buffer += text
            self.status_message.emit("计数: " + self.count_buffer)
            return True

        # 获取计数
        count = int(self.count_buffer) if self.count_buffer else 1
        self.count_buffer = ""

        # 数字 0：行首
        if text == "0":
            self._goto_line_start()
            return True

        # ========== 移动 ==========
        if text == 'h' or key == Qt.Key_Left:
            self._move_cursor(-count, 0)
            return True
        if text == 'j' or key == Qt.Key_Down:
            self._move_cursor(0, count)
            return True
        if text == 'k' or key == Qt.Key_Up:
            self._move_cursor(0, -count)
            return True
        if text == 'l' or key == Qt.Key_Right:
            self._move_cursor(count, 0)
            return True

        if text == 'w':
            for _ in range(count):
                self._move_word_forward()
            return True
        if text == 'b':
            for _ in range(count):
                self._move_word_backward()
            return True
        if text == 'e':
            for _ in range(count):
                self._move_word_end()
            return True

        if text == '0':
            self._goto_line_start()
            return True
        if text == '$':
            self._goto_line_end()
            return True

        if text == 'g':
            # 等待 gg
            self.command_buffer = 'g'
            self.status_message.emit("g...")
            return True
        if text == 'G':
            line_count = self.editor.SendScintilla(
                self.editor.SCI_GETLINECOUNT
            )
            self._goto_line(line_count - 1)
            return True

        # gg 组合
        if self.command_buffer == 'g' and text == 'g':
            self.command_buffer = ""
            self._goto_line(0)
            return True

        # ========== 编辑 ==========
        if text == 'i':
            self._switch_to(VimState.INSERT)
            return True
        if text == 'a':
            self._move_cursor(1, 0)
            self._switch_to(VimState.INSERT)
            return True
        if text == 'I':
            self._goto_line_start()
            self._switch_to(VimState.INSERT)
            return True
        if text == 'A':
            self._goto_line_end()
            self._switch_to(VimState.INSERT)
            return True
        if text == 'o':
            self._open_line_below()
            self._switch_to(VimState.INSERT)
            return True
        if text == 'O':
            self._open_line_above()
            self._switch_to(VimState.INSERT)
            return True

        if text == 'x':
            for _ in range(count):
                self._delete_char_forward()
            return True
        if text == 'X':
            for _ in range(count):
                self._delete_char_backward()
            return True

        if text == 'd':
            # 等待 dd
            self.command_buffer = 'd'
            self.status_message.emit("d...")
            return True

        if self.command_buffer == 'd':
            self.command_buffer = ""
            if text == 'd':
                for _ in range(count):
                    self._delete_line()
                return True

        if text == 'y':
            self.command_buffer = 'y'
            self.status_message.emit("y...")
            return True

        if self.command_buffer == 'y':
            self.command_buffer = ""
            if text == 'y':
                self._yank_line()
                return True

        if text == 'p':
            self._paste_after()
            return True
        if text == 'P':
            self._paste_before()
            return True

        if text == 'u':
            for _ in range(count):
                self.editor.undo()
            return True

        if text == 'r':
            self._switch_to(VimState.REPLACE)
            return True

        # ========== 视觉模式 ==========
        if text == 'v':
            self._switch_to(VimState.VISUAL)
            return True
        if text == 'V':
            self._switch_to(VimState.VISUAL_LINE)
            return True

        # ========== 搜索 ==========
        if text == '/' or text == '?':
            self._switch_to(VimState.COMMAND)
            self.command_buffer = "/"
            self.status_message.emit("搜索...")
            return True

        # ========== 命令模式 ==========
        if text == ':':
            self._switch_to(VimState.COMMAND)
            self.command_buffer = ":"
            self.status_message.emit(":")
            return True

        # Esc 清除命令缓冲
        if key == Qt.Key_Escape:
            self.command_buffer = ""
            self.count_buffer = ""
            self.status_message.emit("")
            return True

        return False

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
        if not self.register:
            return
        if self.register_is_line:
            line, _ = self.editor.getCursorPosition()
            end = self.editor.SendScintilla(
                self.editor.SCI_GETLINEENDPOSITION, line
            )
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, end,
                ("\n" + self.register).encode('utf-8')
            )
        else:
            pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, pos + 1,
                self.register.encode('utf-8')
            )

    def _paste_before(self):
        if not self.register:
            return
        if self.register_is_line:
            line, _ = self.editor.getCursorPosition()
            start = self.editor.SendScintilla(
                self.editor.SCI_POSITIONFROMLINE, line
            )
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, start,
                (self.register + "\n").encode('utf-8')
            )
        else:
            pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, pos,
                self.register.encode('utf-8')
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
        pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
        new_pos = self.editor.SendScintilla(
            self.editor.SCI_WORDENDPOSITION, pos, True
        )
        if new_pos <= pos:
            self.editor.SendScintilla(
                self.editor.SCI_WORDRIGHTPOSITION, pos, True
            )
        else:
            self.editor.SendScintilla(
                self.editor.SCI_WORDRIGHTPOSITION, new_pos, True
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
        if self.last_search:
            pos = self.editor.SendScintilla(
                self.editor.SCI_GETCURRENTPOS
            )
            target = self.last_search.encode('utf-8')
            length = self.editor.SendScintilla(
                self.editor.SCI_GETLENGTH
            )
            self.editor.SendScintilla(
                self.editor.SCI_SETTARGETSTART, pos
            )
            self.editor.SendScintilla(
                self.editor.SCI_SETTARGETEND, length
            )
            found = self.editor.SendScintilla(
                self.editor.SCI_SEARCHINTARGET, len(target), target
            )
            if found >= 0:
                self.editor.SendScintilla(
                    self.editor.SCI_GOTOPOS, found
                )