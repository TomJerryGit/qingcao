#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Vim 补全 + Ctrl+Z 修复 + Vim 菜单入口
==========================================
修复 3 件事：

  A. vim_mode.py:
     - __init__ 加寄存器/操作符状态（锚点宽松版）
     - _move_word_forward 修复 SCI_WORDRIGHTPOSITION 不存在
     - _handle_normal 整块替换（支持 dw/ciw/"a/n 等）

  B. editor_view.py:
     - 禁用 QScintilla 内置 Ctrl+Z/Ctrl+Y 快捷键，
       让主窗口菜单的撤销/重做能收到按键

  C. main_window.py:
     - 工具菜单加"Vim 模式"开关

特性:
    - 幂等
    - 每步独立处理
    - 修改前备份 *.bak.v2

用法:
    python fix_vim_and_ctrlz.py --dry-run
    python fix_vim_and_ctrlz.py
    python fix_vim_and_ctrlz.py --only A,B
"""

import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple, Optional, List

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.v2"


# ============================================================
# 输出
# ============================================================
def print_header(t): print(f"\n{'=' * 60}\n{t}\n{'=' * 60}")
def print_ok(m):   print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")


# ============================================================
# 工具
# ============================================================
def backup(path: Path) -> bool:
    bak = Path(str(path) + BACKUP_SUFFIX)
    if bak.exists():
        return True
    try:
        shutil.copy2(path, bak)
        print_info(f"已备份: {bak.name}")
        return True
    except Exception as e:
        print_fail(f"备份失败: {e}")
        return False


def write_back(path: Path, content: str, no_backup: bool) -> bool:
    if not no_backup and not backup(path):
        return False
    try:
        path.write_text(content, encoding='utf-8', newline='\n')
        return True
    except Exception as e:
        print_fail(f"写回失败: {e}")
        return False


def validate_python(content: str, filepath: str) -> Tuple[bool, str]:
    try:
        compile(content, filepath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"


def replace_once(path: Path, old: str, new: str,
                 marker: str, no_backup: bool) -> str:
    if not path.exists():
        print_fail(f"{path.relative_to(ROOT)}: 不存在")
        return 'failed'
    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"{path.relative_to(ROOT)}: 读取失败 ({e})")
        return 'failed'

    if marker and marker in content:
        print_skip(f"{path.relative_to(ROOT)}: 已修复")
        return 'skipped'

    cnt = content.count(old)
    if cnt == 0:
        print_fail(f"{path.relative_to(ROOT)}: 锚点未找到")
        for line in old.split('\n')[:3]:
            print(f"      | {line}")
        return 'failed'
    if cnt > 1:
        print_fail(f"{path.relative_to(ROOT)}: 锚点重复 {cnt} 次")
        return 'failed'

    new_content = content.replace(old, new, 1)

    if path.suffix == '.py':
        ok, err = validate_python(new_content, str(path))
        if not ok:
            print_fail(f"{path.relative_to(ROOT)}: 语法错误 ({err})")
            return 'failed'

    if not write_back(path, new_content, no_backup):
        return 'failed'
    print_ok(f"{path.relative_to(ROOT)}: 已修复")
    return 'applied'


# ============================================================
# A1: vim_mode.py __init__ 加状态（锚点含注释）
# ============================================================
A1_MARKER = "self.registers = {'\"': ''}"

A1_OLD = '''        self.state = VimState.NORMAL
        self.command_buffer = ""
        self.register = ""  # 剪贴板寄存器
        self.register_is_line = False
        self.last_search = ""
        self.count_buffer = ""  # 数字前缀
        self.enabled = False'''

A1_NEW = '''        self.state = VimState.NORMAL
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
        self._pending_textobj_prefix = None'''


# ============================================================
# A2: _move_word_forward 修复 SCI_WORDRIGHTPOSITION
# ============================================================
A2_MARKER = "# A2: 用 SCI_WORDRIGHT 替代不存在的 SCI_WORDRIGHTPOSITION"

A2_OLD = '''    def _move_word_forward(self):
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
            )'''

A2_NEW = '''    def _move_word_forward(self):
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
            )'''


# ============================================================
# A3: _handle_normal 整块替换
# ============================================================
A3_MARKER = "# ==== A3: v2 操作符 + 文本对象 ===="

A3_NEW_BLOCK = '''    def _handle_normal(self, key, text, modifiers) -> bool:
        """处理 Normal 模式按键（v2: 支持操作符 + 文本对象 + 寄存器）"""
        from PyQt5.QtCore import Qt

        # ==== A3: v2 操作符 + 文本对象 ====
        if self._pending_textobj_prefix is not None:
            return self._handle_textobj(text)

        if self._pending_operator is not None:
            return self._handle_after_operator(key, text)

        if self._pending_register is not None:
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
            self._pending_register = ""
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

        if text == 'g':
            self.command_buffer = 'g'
            self.status_message.emit("g...")
            return True
        if self.command_buffer == 'g' and text == 'g':
            self.command_buffer = ""
            self._goto_line(0); return True
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
                self.editor.undo()
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


'''


def _replace_normal_block(path: Path, no_backup: bool) -> str:
    """在 _handle_normal 与 _handle_command 之间替换"""
    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 'failed'

    if A3_MARKER in content:
        print_skip(f"{path.relative_to(ROOT)}: _handle_normal 已替换")
        return 'skipped'

    start_mark = "    def _handle_normal(self, key, text, modifiers) -> bool:"
    end_mark = "    def _handle_command(self, key, text, modifiers) -> bool:"

    start = content.find(start_mark)
    if start < 0:
        print_fail(f"未找到 _handle_normal 起点")
        return 'failed'
    end = content.find(end_mark, start + len(start_mark))
    if end < 0:
        print_fail(f"未找到 _handle_command 终点")
        return 'failed'

    new_content = content[:start] + A3_NEW_BLOCK + content[end:]

    ok, err = validate_python(new_content, str(path))
    if not ok:
        print_fail(f"语法错误: {err}")
        return 'failed'

    if not write_back(path, new_content, no_backup):
        return 'failed'
    print_ok(f"{path.relative_to(ROOT)}: _handle_normal 块已替换")
    return 'applied'


# ============================================================
# B: editor_view.py 禁用 QScintilla 内置 Ctrl+Z/Ctrl+Y
# ============================================================
B_MARKER = "# B: 禁用 QScintilla 内置 Ctrl+Z/Ctrl+Y 快捷键"

B_OLD = '''        # 自动补全
        self.setAutoCompletionSource(QsciScintilla.AcsAll)
        self.setAutoCompletionThreshold(2)
        self.setAutoCompletionCaseSensitivity(False)
        self.setAutoCompletionReplaceWord(False)'''

B_NEW = '''        # 自动补全
        self.setAutoCompletionSource(QsciScintilla.AcsAll)
        self.setAutoCompletionThreshold(2)
        self.setAutoCompletionCaseSensitivity(False)
        self.setAutoCompletionReplaceWord(False)

        # B: 禁用 QScintilla 内置 Ctrl+Z/Ctrl+Y 快捷键
        # 原因:
        #   EditorProxy 禁用了 Scintilla 内置 undo 栈，改用自己的
        #   undo_manager。但 QScintilla 默认仍响应 Ctrl+Z/Ctrl+Y
        #   按键，执行"内置 undo"（空操作），并吃掉按键 —— 导致
        #   主窗口菜单的撤销/重做快捷键收不到。
        # 解决:
        #   把 Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z 的内置绑定清除。
        try:
            from PyQt5.QtCore import Qt as _Qt
            for _key, _mod in [
                (_Qt.Key_Z, _Qt.ControlModifier),
                (_Qt.Key_Y, _Qt.ControlModifier),
                (_Qt.Key_Z, _Qt.ControlModifier | _Qt.ShiftModifier),
            ]:
                try:
                    self.SendScintilla(
                        QsciScintilla.SCI_CLEARCMDKEY,
                        _key + (_mod << 16),
                    )
                except Exception:
                    pass
        except Exception:
            pass'''

# ============================================================
# C: main_window.py 加 Vim 模式菜单
# ============================================================
C_MARKER = "# C: Vim 模式菜单开关"

C_OLD_ANCHOR = '''        self._add_action(self.tools_menu, "⌨ 快捷键编辑器", None,
                          self._show_keymap_editor)
        self.tools_menu.addSeparator()
        self._add_action(self.tools_menu, "📊 性能监控", None,
                          self._show_perf_monitor)'''

C_NEW_ANCHOR = '''        self._add_action(self.tools_menu, "⌨ 快捷键编辑器", None,
                          self._show_keymap_editor)
        self.tools_menu.addSeparator()
        self._add_action(self.tools_menu, "📊 性能监控", None,
                          self._show_perf_monitor)
        # C: Vim 模式菜单开关
        self.vim_mode_action = QAction("Vim 模式", self)
        self.vim_mode_action.setCheckable(True)
        self.vim_mode_action.setShortcut(QKeySequence("Ctrl+Alt+V"))
        self.vim_mode_action.toggled.connect(self._toggle_vim_mode)
        self.tools_menu.addAction(self.vim_mode_action)'''

# 加 _toggle_vim_mode 方法（插在 _show_perf_monitor 后面）
C_METHOD_MARKER = "# C: Vim 模式切换方法"

C_METHOD_OLD = '''    def _export_config(self):
        """导出配置"""
        try:
            from app.config_manager import ConfigManager'''

C_METHOD_NEW = '''    # C: Vim 模式切换方法
    def _toggle_vim_mode(self, checked: bool):
        """切换 Vim 模式

        为当前编辑器附加/移除 VimMode 实例。
        """
        try:
            from core.vim_mode import VimMode

            proxy = self.tabs.current_proxy()
            if not proxy or not proxy.sc:
                self.status_bar.showMessage("没有活动的编辑器", 2000)
                self.vim_mode_action.setChecked(False)
                return

            editor = proxy.sc

            if checked:
                # 创建 VimMode 实例并附加到 editor
                vim = getattr(editor, '_vim_mode', None)
                if vim is None:
                    vim = VimMode(editor)
                    editor._vim_mode = vim
                vim.set_enabled(True)
                self.status_bar.showMessage(
                    "Vim 模式已启用（Esc 回到 Normal）", 3000
                )
            else:
                vim = getattr(editor, '_vim_mode', None)
                if vim is not None:
                    vim.set_enabled(False)
                self.status_bar.showMessage("Vim 模式已禁用", 2000)
        except Exception as e:
            print(f"[MainWindow] Vim 切换失败: {e}")
            self.status_bar.showMessage(f"Vim 切换失败: {e}", 3000)

    def _export_config(self):
        """导出配置"""
        try:
            from app.config_manager import ConfigManager'''


# ============================================================
# 主流程
# ============================================================
def fix_A(no_backup: bool) -> str:
    """vim_mode.py 三处修改"""
    path = ROOT / "core" / "vim_mode.py"
    if not path.exists():
        print_fail("core/vim_mode.py 不存在")
        return 'failed'

    results = []

    # A1
    print_info("A1: __init__ 加状态")
    r1 = replace_once(path, A1_OLD, A1_NEW, A1_MARKER, no_backup)
    results.append(r1)

    # A2
    print_info("A2: _move_word_forward 修复")
    r2 = replace_once(path, A2_OLD, A2_NEW, A2_MARKER, no_backup)
    results.append(r2)

    # A3
    print_info("A3: _handle_normal 块替换")
    r3 = _replace_normal_block(path, no_backup)
    results.append(r3)

    if 'failed' in results:
        return 'failed'
    if 'applied' in results:
        return 'applied'
    return 'skipped'


def fix_B(no_backup: bool) -> str:
    """editor_view.py 禁用 QScintilla 内置 Ctrl+Z/Y"""
    path = ROOT / "ui" / "editor_view.py"
    return replace_once(path, B_OLD, B_NEW, B_MARKER, no_backup)


def fix_C(no_backup: bool) -> str:
    """main_window.py 加 Vim 菜单"""
    path = ROOT / "ui" / "main_window.py"
    if not path.exists():
        print_fail("ui/main_window.py 不存在")
        return 'failed'

    results = []

    print_info("C1: 工具菜单加 Vim 开关")
    r1 = replace_once(path, C_OLD_ANCHOR, C_NEW_ANCHOR,
                       C_MARKER, no_backup)
    results.append(r1)

    print_info("C2: 加 _toggle_vim_mode 方法")
    r2 = replace_once(path, C_METHOD_OLD, C_METHOD_NEW,
                       C_METHOD_MARKER, no_backup)
    results.append(r2)

    if 'failed' in results:
        return 'failed'
    if 'applied' in results:
        return 'applied'
    return 'skipped'


FIXES = [
    ("A", "vim_mode.py: 状态 + SCI_WORDRIGHT + 操作符", fix_A),
    ("B", "editor_view.py: 禁用 Scintilla 内置 Ctrl+Z", fix_B),
    ("C", "main_window.py: Vim 模式菜单", fix_C),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Vim 补全 + Ctrl+Z 修复")
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--only', type=str, default='')
    args = parser.parse_args()

    print_header("Vim 补全 + Ctrl+Z 修复")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")

    fixes = FIXES
    if args.only:
        only = {x.strip().upper() for x in args.only.split(',')}
        fixes = [f for f in fixes if f[0] in only]

    if args.dry_run:
        print()
        print_info(f"[DRY-RUN] 将处理 {len(fixes)} 项：")
        for pid, name, _ in fixes:
            print_info(f"  {pid}: {name}")
        print()
        print("  去掉 --dry-run 即可应用。")
        return 0

    results = []
    for pid, name, fn in fixes:
        print_header(f"{pid}: {name}")
        r = fn(args.no_backup)
        results.append((pid, name, r))

    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)

    applied = skipped = failed = 0
    for pid, name, r in results:
        marker = {'applied': '✓', 'skipped': '-', 'failed': '✗'}[r]
        print(f"  {marker} {pid}: {name} [{r}]")
        if r == 'applied':
            applied += 1
        elif r == 'skipped':
            skipped += 1
        else:
            failed += 1

    print()
    if failed > 0:
        print("=" * 60)
        print(f"✗ 有 {failed} 项失败")
        print("=" * 60)
        return 1

    print("=" * 60)
    print(f"✓ 完成（应用 {applied} 项，跳过 {skipped} 项）")
    print("=" * 60)
    print()
    print("验证:")
    print("  python tests/run_all.py")
    print("  python main.py")
    print()
    print("进入 Vim 模式: 工具菜单 → Vim 模式（Ctrl+Alt+V）")
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n脚本异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)