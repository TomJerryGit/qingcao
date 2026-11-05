# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""从 core/editor.py 拆出的 editops 职责（v2.23 D1）。"""

from core.editor_common import *  # noqa: F401,F403
from core.editor_common import (  # noqa: F401
    _EOL_SPLIT_RE,
    _normalize_bytes,
    _trim_trailing_ws_keep_eol,
)


class EditorEditOpsMixin:
    # ========================================================
    # 行操作
    # ========================================================
    def move_line_up(self):
        """上移当前行（或多行选区）"""
        self._move_line(True)

    def move_line_down(self):
        """下移当前行（或多行选区）"""
        self._move_line(False)

    def _move_line(self, up: bool):
        """
        移动行（内部实现）。

        修复说明:
            - PyQt5 的 QsciScintilla 未导出 SCI_GETRANGE，改用
              self.sc.text(start, end) 获取文本
            - SCI_INSERTTEXT 需要 bytes 参数
        """
        try:
            sel_start = self.sc.SendScintilla(QsciScintilla.SCI_GETSELECTIONSTART)
            sel_end = self.sc.SendScintilla(QsciScintilla.SCI_GETSELECTIONEND)

            start_line = self.sc.SendScintilla(QsciScintilla.SCI_LINEFROMPOSITION, sel_start)
            end_line = self.sc.SendScintilla(QsciScintilla.SCI_LINEFROMPOSITION, sel_end)

            # 无选区则操作当前行
            if sel_start == sel_end:
                start_line = end_line = self.sc.SendScintilla(
                    QsciScintilla.SCI_LINEFROMPOSITION, self.get_current_pos()
                )

            line_count = self.sc.SendScintilla(QsciScintilla.SCI_GETLINECOUNT)

            if up and start_line == 0:
                return
            if not up and end_line >= line_count - 1:
                return

            self.sc.SendScintilla(QsciScintilla.SCI_BEGINUNDOACTION)

            # 提取行文本
            start_pos = self.sc.SendScintilla(QsciScintilla.SCI_POSITIONFROMLINE, start_line)
            end_pos = self.sc.SendScintilla(QsciScintilla.SCI_GETLINEENDPOSITION, end_line)

            # 修复：使用 Python API 获取文本
            text = self.sc.text(start_pos, end_pos)
            text_bytes = _normalize_bytes(text)

            # 删除原行
            self.sc.SendScintilla(QsciScintilla.SCI_DELETERANGE, start_pos, end_pos - start_pos)

            # 插入到目标位置
            if up:
                target_line = start_line - 1
                insert_pos = self.sc.SendScintilla(QsciScintilla.SCI_POSITIONFROMLINE, target_line)
            else:
                target_line = end_line
                insert_pos = self.sc.SendScintilla(
                    QsciScintilla.SCI_GETLINEENDPOSITION, target_line
                )

            if text_bytes:
                self.sc.SendScintilla(QsciScintilla.SCI_INSERTTEXT, insert_pos, text_bytes)

            # 恢复选区（按字节长度计算新位置）
            new_start = insert_pos
            new_end = insert_pos + len(text_bytes)
            self.sc.SendScintilla(QsciScintilla.SCI_SETSELECTIONSTART, new_start)
            self.sc.SendScintilla(QsciScintilla.SCI_SETSELECTIONEND, new_end)

            self.sc.SendScintilla(QsciScintilla.SCI_ENDUNDOACTION)

        except Exception as e:
            print(f"[EditorProxy] 移动行失败: {e}")
            import traceback

            traceback.print_exc()

    def duplicate_line(self):
        """
        复制当前行（或多行选区）到下方。

        修复说明:
            - 使用 self.sc.text() 替代 SCI_GETRANGE
            - SCI_INSERTTEXT 需要 bytes
        """
        try:
            sel_start = self.sc.SendScintilla(QsciScintilla.SCI_GETSELECTIONSTART)
            sel_end = self.sc.SendScintilla(QsciScintilla.SCI_GETSELECTIONEND)

            start_line = self.sc.SendScintilla(QsciScintilla.SCI_LINEFROMPOSITION, sel_start)
            end_line = self.sc.SendScintilla(QsciScintilla.SCI_LINEFROMPOSITION, sel_end)

            # 无选区则操作当前行
            if sel_start == sel_end:
                start_line = end_line = self.sc.SendScintilla(
                    QsciScintilla.SCI_LINEFROMPOSITION, self.get_current_pos()
                )

            start_pos = self.sc.SendScintilla(QsciScintilla.SCI_POSITIONFROMLINE, start_line)
            end_pos = self.sc.SendScintilla(QsciScintilla.SCI_GETLINEENDPOSITION, end_line)

            # 修复：使用 Python API 获取文本
            text = self.sc.text(start_pos, end_pos)
            text_bytes = _normalize_bytes(text)

            # 插入到下一行
            insert_pos = self.sc.SendScintilla(QsciScintilla.SCI_GETLINEENDPOSITION, end_line)
            if text_bytes:
                self.sc.SendScintilla(QsciScintilla.SCI_INSERTTEXT, insert_pos, text_bytes)

            # 光标移动到复制的内容
            self.sc.SendScintilla(QsciScintilla.SCI_GOTOPOS, insert_pos)

        except Exception as e:
            print(f"[EditorProxy] 复制行失败: {e}")
            import traceback

            traceback.print_exc()

    def delete_line(self):
        """删除当前行"""
        try:
            line, _ = self.sc.getCursorPosition()
            start_pos = self.sc.SendScintilla(QsciScintilla.SCI_POSITIONFROMLINE, line)
            end_pos = self.sc.SendScintilla(QsciScintilla.SCI_GETLINEENDPOSITION, line)
            # 包含换行符
            length = end_pos - start_pos
            if end_pos < self.sc.SendScintilla(QsciScintilla.SCI_GETLENGTH):
                length += 1
            self.sc.SendScintilla(QsciScintilla.SCI_DELETERANGE, start_pos, length)
        except Exception as e:
            print(f"[EditorProxy] 删除行失败: {e}")

    def toggle_line_comment(self):
        """切换行注释"""
        try:
            line, _ = self.sc.getCursorPosition()
            text = self.sc.text(line)

            # 判断注释符
            comment_char = "#"
            lexer = self.sc.lexer()
            if isinstance(lexer, QsciLexerCPP):
                comment_char = "//"

            stripped = text.lstrip()

            if stripped.startswith(comment_char):
                # 取消注释
                start_pos = self.sc.SendScintilla(QsciScintilla.SCI_POSITIONFROMLINE, line)
                pos = text.index(comment_char)
                del_len = len(comment_char)
                # 同时删除后面的空格
                if pos + del_len < len(text) and text[pos + del_len] == " ":
                    del_len += 1
                self.sc.SendScintilla(QsciScintilla.SCI_DELETERANGE, start_pos + pos, del_len)
            else:
                # 添加注释
                indent = len(text) - len(stripped)
                start_pos = self.sc.SendScintilla(QsciScintilla.SCI_POSITIONFROMLINE, line) + indent
                insert_text = (comment_char + " ").encode("utf-8")
                self.sc.SendScintilla(QsciScintilla.SCI_INSERTTEXT, start_pos, insert_text)

        except Exception as e:
            print(f"[EditorProxy] 切换注释失败: {e}")

    def indent_selection(self):
        """增加选区缩进"""
        try:
            self.sc.SendScintilla(QsciScintilla.SCI_TAB)
        except Exception:
            pass

    def unindent_selection(self):
        """减少选区缩进"""
        try:
            self.sc.SendScintilla(QsciScintilla.SCI_BACKTAB)
        except Exception:
            pass
