#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Vim 模式补全
============================
为 core/vim_mode.py 增加：

  1. 操作符 + 动作组合:  dw / de / db / d$ / d0 / dG / dgg
                        cw / ce / cb / c$ / cc
                        yw / ye / yb / yy
  2. 文本对象:           iw / aw / i" / a" / i' / a'
                        i( / a( / i[ / a[ / i{ / a{
  3. 命名寄存器:         "a 前缀（a-z, 0-9, ", +, *, -, _）
  4. 查找重复:           n / N

改动方式:
    - __init__: 增加 pending 状态字段 + registers
    - _handle_normal: 整块替换（含新增辅助方法）
    - 保留 __init__ / set_enabled / 其它辅助方法不变

特性:
    - 幂等
    - 修改前备份 *.bak.vim
    - 修改后 compile() 验证

用法:
    python fix_vim_enhance.py --dry-run
    python fix_vim_enhance.py
    python fix_vim_enhance.py --no-backup
"""

import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple, List, Optional

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.vim"


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


# ============================================================
# 段 1: __init__ 增加状态字段
# ============================================================
M1 = "self.registers"

OLD1 = '''        self.state = VimState.NORMAL
        self.command_buffer = ""
        self.register = ""
        self.register_is_line = False
        self.last_search = ""
        self.count_buffer = ""
        self.enabled = False'''

NEW1 = '''        self.state = VimState.NORMAL
        self.command_buffer = ""
        self.register = ""
        self.register_is_line = False
        self.last_search = ""
        self.count_buffer = ""
        self.enabled = False

        # v2 补全: 多寄存器 + 操作符/文本对象状态
        self.registers = {'"': ''}              # 命名寄存器
        self._pending_operator = None           # d / c / y / > / <
        self._operator_count = 1                # 操作符后跟随的计数
        self._pending_register = None           # 等待寄存器名的状态
        self._pending_textobj_prefix = None     # i / a
        self._last_search_forward = True        # n / N 方向记忆'''

# ============================================================
# 段 2: _handle_normal 整块替换（含新增辅助方法）
# ============================================================
M2 = "# ==== v2 操作符 + 文本对象 ==="

NEW_HANDLE_NORMAL = '''    def _handle_normal(self, key, text, modifiers) -> bool:
        """处理 Normal 模式按键（v2: 支持操作符 + 文本对象 + 寄存器）"""
        from PyQt5.QtCore import Qt

        # ==== v2 操作符 + 文本对象 ====
        # 1. 待处理：文本对象
        if self._pending_textobj_prefix is not None:
            return self._handle_textobj(text)

        # 2. 待处理：操作符
        if self._pending_operator is not None:
            return self._handle_after_operator(key, text)

        # 3. 待处理：寄存器名
        if self._pending_register is not None:
            if text and (text.isalnum() or
                          text in ('"', '+', '-', '*', '0', '_')):
                self._pending_register = text
                return True
            # 非法字符，清空
            self._pending_register = None
            self.status_message.emit("")
            return True

        # 4. 数字前缀
        if (text and text.isdigit()
                and not (text == "0" and not self.count_buffer)):
            self.count_buffer += text
            self.status_message.emit("计数: " + self.count_buffer)
            return True

        count = int(self.count_buffer) if self.count_buffer else 1
        self.count_buffer = ""

        # 5. 寄存器前缀 "
        if text == '"':
            self._pending_register = ""
            self.status_message.emit('"')
            return True

        # 6. 操作符前缀
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
    # v2 新增：操作符处理
    # ============================================================
    def _handle_after_operator(self, key, text) -> bool:
        """已按 d/c/y/>/<，等待动作键"""
        from PyQt5.QtCore import Qt
        op = self._pending_operator
        count = self._operator_count

        # 数字继续累积
        if text and text.isdigit():
            self.count_buffer += text
            self._operator_count = int(self.count_buffer)
            return True

        # 相同操作符 → 行操作（dd/yy/cc/>>/<<）
        if text == op:
            if op in ('d', 'c', 'y'):
                for _ in range(count):
                    self._apply_line_operator(op)
            elif op in ('>', '<'):
                for _ in range(count):
                    self._indent_line(op == '>')
            self._clear_pending()
            return True

        # i/a → 文本对象
        if text in ('i', 'a'):
            self._pending_textobj_prefix = text
            self.status_message.emit(op + text)
            return True

        # 动作键 → 计算范围
        rng = self._resolve_motion(text, key, count)
        if rng is None:
            self._clear_pending()
            return True  # 未知动作，静默放弃

        start, end = rng
        self._apply_operator(op, start, end)
        self._clear_pending()
        return True

    def _handle_textobj(self, text) -> bool:
        """已按 i/a，等待对象字符"""
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
        """清除所有待处理状态"""
        self._pending_operator = None
        self._operator_count = 1
        self._pending_register = None
        self._pending_textobj_prefix = None
        self.count_buffer = ""
        self.status_message.emit("")

    # ============================================================
    # v2 新增：动作解析
    # ============================================================
    def _resolve_motion(self, text, key, count):
        """返回 (start, end) 字节偏移，或 None"""
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

    # ============================================================
    # v2 新增：文本对象
    # ============================================================
    def _textobj_word(self, include_space: bool):
        """iw / aw"""
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
        """i" / a" 等"""
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
        """i( / a( 等"""
        pos = self._get_pos()
        length = self._get_length()

        # 向左找最近的 open_ch（深度匹配）
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

        # 向右找匹配的 close_ch
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

    # ============================================================
    # v2 新增：应用操作符
    # ============================================================
    def _apply_operator(self, op: str, start: int, end: int):
        """应用 d/c/y 操作到 [start, end)"""
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
        """dd / yy / cc 行操作"""
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
            # cc: 保留行首缩进，清空内容
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
        """增加/减少缩进"""
        if increase:
            self.editor.SendScintilla(self.editor.SCI_TAB)
        else:
            self.editor.SendScintilla(self.editor.SCI_BACKTAB)

    # ============================================================
    # v2 新增：辅助
    # ============================================================
    def _get_pos(self) -> int:
        return self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)

    def _get_length(self) -> int:
        return self.editor.SendScintilla(self.editor.SCI_GETLENGTH)

    def _find_word_forward(self, pos: int) -> int:
        length = self._get_length()
        return min(
            self.editor.SendScintilla(
                self.editor.SCI_WORDRIGHTEND, pos, True
            ),
            length,
        )

    def _find_word_backward(self, pos: int) -> int:
        return self.editor.SendScintilla(
            self.editor.SCI_WORDSTARTPOSITION, pos, True
        )

    def _find_word_end(self, pos: int) -> int:
        return self.editor.SendScintilla(
            self.editor.SCI_WORDENDPOSITION, pos, True
        )

    def _search_prev(self):
        """N: 反向查找"""
        if not self.last_search:
            return
        pos = self.editor.SendScintilla(
            self.editor.SCI_GETCURRENTPOS
        )
        target = self.last_search.encode('utf-8')
        self.editor.SendScintilla(self.editor.SCI_SETTARGETSTART, 0)
        self.editor.SendScintilla(
            self.editor.SCI_SETTARGETEND, pos
        )
        found = self.editor.SendScintilla(
            self.editor.SCI_SEARCHINTARGET, len(target), target
        )
        if found >= 0:
            # 反向搜最后一次出现
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


# ============================================================
# 主流程
# ============================================================
def apply_block_replace(content: str, start_mark: str, end_mark: str,
                         new_block: str) -> Optional[str]:
    """在 start_mark 和 end_mark 之间替换为 new_block"""
    start = content.find(start_mark)
    if start < 0:
        return None
    end = content.find(end_mark, start + len(start_mark))
    if end < 0:
        return None
    return content[:start] + new_block + content[end:]


def main() -> int:
    parser = argparse.ArgumentParser(description="Vim 模式补全")
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("Vim 模式补全")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")

    path = ROOT / "core" / "vim_mode.py"
    if not path.exists():
        print_fail(f"未找到 {path}")
        return 1

    content = path.read_text(encoding='utf-8')

    # 幂等检查
    if M2 in content:
        print_skip("Vim 模式已补全（v2）")
        return 0

    # 段 1: __init__ 状态字段
    if M1 in content:
        print_skip("段 1（__init__）已应用")
    else:
        if OLD1 not in content:
            print_fail("段 1: __init__ 锚点未找到")
            return 1
        content = content.replace(OLD1, NEW1, 1)
        print_ok("段 1: __init__ 状态字段已添加")

    # 段 2: _handle_normal 块替换
    START_NORMAL = "    def _handle_normal(self, key, text, modifiers) -> bool:"
    END_NORMAL = "    def _handle_command(self, key, text, modifiers) -> bool:"

    new_content = apply_block_replace(
        content, START_NORMAL, END_NORMAL,
        NEW_HANDLE_NORMAL + "\n",
    )
    if new_content is None:
        print_fail("段 2: _handle_normal 块边界未找到")
        print_info("请检查 vim_mode.py 是否有 "
                   "'def _handle_normal' 和 'def _handle_command'")
        return 1
    content = new_content
    print_ok("段 2: _handle_normal 及新增方法已替换")

    # 语法验证
    ok, err = validate_python(content, str(path))
    if not ok:
        print_fail(f"语法错误: {err}")
        return 1

    if args.dry_run:
        print()
        print_info("[DRY-RUN] 内容已生成，不写回")
        return 0

    if not write_back(path, content, args.no_backup):
        return 1

    print()
    print("=" * 60)
    print("✓ Vim 模式补全完成")
    print("=" * 60)
    print()
    print("新增支持:")
    print("  操作符+动作:  dw / de / db / d$ / d0 / dG / dgg")
    print("               cw / ce / cb / c$ / cc")
    print("               yw / ye / yb / yy")
    print("  文本对象:     iw / aw / i\" / a\" / i( / a( / i[ / a[ / i{ / a{")
    print("  命名寄存器:   \"a 前缀（a-z, 0-9, \", +, *, -, _）")
    print("  查找重复:     n / N")
    print()
    print("验证:")
    print("  python tests/run_all.py")
    print("  python main.py")
    print("  # 在编辑器中启用 Vim 模式后测试")
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