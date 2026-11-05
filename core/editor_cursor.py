# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""从 core/editor.py 拆出的 cursor 职责（v2.23 D1）。"""

from core.editor_common import *  # noqa: F401,F403
from core.editor_common import (  # noqa: F401
    _EOL_SPLIT_RE,
    _normalize_bytes,
    _trim_trailing_ws_keep_eol,
)


class EditorCursorMixin:
    # ========================================================
    # 光标与选区
    # ========================================================
    def get_current_pos(self) -> int:
        """获取当前光标位置（字符偏移）"""
        try:
            return self.sc.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)
        except Exception:
            return 0

    def get_cursor_position(self) -> Tuple[int, int]:
        """获取光标 (行, 列)"""
        try:
            return self.sc.getCursorPosition()
        except Exception:
            return (0, 0)

    def set_selection(self, start: int, end: int):
        """设置选区"""
        try:
            self.sc.SendScintilla(QsciScintilla.SCI_SETSELECTIONSTART, start)
            self.sc.SendScintilla(QsciScintilla.SCI_SETSELECTIONEND, end)
        except Exception as e:
            print(f"[EditorProxy] 设置选区失败: {e}")

    def get_selected_text(self) -> str:
        """获取选中的文本"""
        try:
            return self.sc.selectedText()
        except Exception:
            return ""

    def select_all(self):
        """全选"""
        try:
            self.sc.selectAll()
        except Exception:
            pass

    def goto_position(self, pos: int):
        """跳转到字符位置"""
        try:
            max_pos = self.sc.SendScintilla(QsciScintilla.SCI_GETLENGTH)
            pos = max(0, min(pos, max_pos))
            self.sc.SendScintilla(QsciScintilla.SCI_GOTOPOS, pos)
            self.sc.ensureCursorVisible()
        except Exception:
            pass

    def goto_line(self, line: int):
        """跳转到指定行（0 开始）"""
        try:
            self.sc.setCursorPosition(line, 0)
            self.sc.ensureLineVisible(line)
        except Exception:
            pass

    # ========================================================
    # 文本操作
    # ========================================================
    def read_buffer_range(self, start: int, length: int) -> bytes:
        """读取缓冲区的字节区间（用于撤销栈记录被删除的内容）

        修复（DeleteCmd 无法撤销，审计用例 TestVimUndo 复现）：
            SCN_MODIFIED 对**删除**通知**不提供文本**（`text` 为 None），
            而原先直接用这个空值构造 `DeleteCmd`：

                cmd = CommandPool.acquire_delete(position, length,
                                                 text_bytes)   # text_bytes = b''

            于是 `DeleteCmd.deleted_text` 永远是空 bytes，而
            `DeleteCmd.undo()` 开头就是 `if not self.deleted_text: return`
            —— **任何删除都无法撤销**（Ctrl+Z 后文本原样不动，内容永久丢失）。

            正确做法是在收到 `SC_MOD_BEFOREDELETE`（删除**之前**触发，
            此时缓冲区里还有原文）时读取待删区间并暂存，随后构造
            `DeleteCmd` 时使用它。
        """
        try:
            if start < 0 or length <= 0:
                return b""
            buf = self.sc.text().encode("utf-8")
            end = min(start + length, len(buf))
            if end <= start:
                return b""
            return buf[start:end]
        except Exception as e:
            logger.debug("读取缓冲区区间失败: %s", e)
            return b""

    def get_text(self) -> str:
        """获取全部文本"""
        try:
            return self.sc.text()
        except Exception:
            return ""

    def set_text(self, text: str):
        """设置全部文本"""
        try:
            self.sc.setText(text)
            self._modified = True
            self.modified_changed.emit(True)
        except Exception as e:
            print(f"[EditorProxy] 设置文本失败: {e}")

    def abort_loading(self):
        """中止大文件的延迟分块加载（关标签 / 关窗口时必须调用）

        ★ 为什么必须有（真实 UI 压测复现的段错误）：

            大文件（>10MB）采用"先加载一部分、其余分片延迟加载"的策略，
            靠 `QTimer.singleShot(0, self._load_chunk_slice)` 续跑。

            用户在这期间关闭标签或窗口时，Qt 会销毁 `self.sc`
            （QScintilla 控件），但**已排队的定时器回调仍会执行**，
            于是 `self.sc.append(...)` 作用在已销毁的 C++ 对象上
            → 进程直接 **段错误（0xC0000005）**，没有任何 Python 异常
            可捕获，用户看到的是"关窗口时程序闪退"。

            置位 `_load_aborted` 后，`_load_chunk_slice` 每次进入都会检查
            并立即返回；`_load_content` 也会在重新打开文件时复位它。
        """
        self._load_aborted = True

    def insert_text(self, text: str, pos: Optional[int] = None):
        """在指定位置插入文本"""
        try:
            if pos is None:
                pos = self.get_current_pos()
            data = _normalize_bytes(text)
            self.sc.SendScintilla(QsciScintilla.SCI_INSERTTEXT, pos, data)
        except Exception as e:
            print(f"[EditorProxy] 插入文本失败: {e}")

    def replace_selected_text(self, text: str):
        """替换选中的文本"""
        try:
            self.sc.replaceSelectedText(text)
        except Exception as e:
            print(f"[EditorProxy] 替换文本失败: {e}")

    # ========================================================
    # 列模式与多光标
    # ========================================================
    def set_column_mode(self, enabled: bool):
        """切换列模式"""
        try:
            mode = QsciScintilla.SC_SEL_RECTANGLE if enabled else QsciScintilla.SC_SEL_STREAM
            self.sc.SendScintilla(QsciScintilla.SCI_SETSELECTIONMODE, mode)
        except Exception as e:
            print(f"[EditorProxy] 切换列模式失败: {e}")

    def is_column_mode(self) -> bool:
        """是否处于列模式"""
        try:
            mode = self.sc.SendScintilla(QsciScintilla.SCI_GETSELECTIONMODE)
            return mode == QsciScintilla.SC_SEL_RECTANGLE
        except Exception:
            return False

    def add_cursor_at(self, pos: int):
        """在指定位置添加额外光标"""
        try:
            self.sc.SendScintilla(QsciScintilla.SCI_ADDSELECTION, pos, pos)
        except Exception as e:
            print(f"[EditorProxy] 添加光标失败: {e}")

    def add_cursors_at_line_ends(self):
        """为选中范围每行末尾添加光标"""
        try:
            sel_start = self.sc.SendScintilla(QsciScintilla.SCI_GETSELECTIONSTART)
            sel_end = self.sc.SendScintilla(QsciScintilla.SCI_GETSELECTIONEND)

            start_line = self.sc.SendScintilla(QsciScintilla.SCI_LINEFROMPOSITION, sel_start)
            end_line = self.sc.SendScintilla(QsciScintilla.SCI_LINEFROMPOSITION, sel_end)

            for line in range(start_line, end_line + 1):
                pos = self.sc.SendScintilla(QsciScintilla.SCI_GETLINEENDPOSITION, line)
                self.sc.SendScintilla(QsciScintilla.SCI_ADDSELECTION, pos, pos)

        except Exception as e:
            print(f"[EditorProxy] 添加行尾光标失败: {e}")

    def clear_multi_cursors(self):
        """清除所有额外光标"""
        try:
            self.sc.SendScintilla(QsciScintilla.SCI_CLEARSELECTIONS)
        except Exception:
            pass

    def get_selection_count(self) -> int:
        """获取当前选区/光标数量"""
        try:
            return self.sc.SendScintilla(QsciScintilla.SCI_GETSELECTIONS)
        except Exception:
            return 1

    def select_next_occurrence(self):
        """选中当前单词的下一次出现"""
        try:
            sel_text = self.sc.selectedText()

            if not sel_text:
                # 无选区，先选中当前单词
                pos = self.get_current_pos()
                start = self.sc.SendScintilla(QsciScintilla.SCI_WORDSTARTPOSITION, pos, True)
                end = self.sc.SendScintilla(QsciScintilla.SCI_WORDENDPOSITION, pos, True)
                if start < end:
                    self.sc.SendScintilla(QsciScintilla.SCI_SETSELECTION, start, end)
                    sel_text = self.sc.text()[start:end]
                if not sel_text:
                    return

            # 查找下一次出现
            target = sel_text.encode("utf-8", errors="replace")
            main_end = self.sc.SendScintilla(QsciScintilla.SCI_GETSELECTIONNEND, 0)
            length = self.sc.SendScintilla(QsciScintilla.SCI_GETLENGTH)

            self.sc.SendScintilla(QsciScintilla.SCI_SETTARGETSTART, main_end)
            self.sc.SendScintilla(QsciScintilla.SCI_SETTARGETEND, length)
            self.sc.SendScintilla(
                QsciScintilla.SCI_SETSEARCHFLAGS,
                QsciScintilla.SCFIND_MATCHCASE | QsciScintilla.SCFIND_WHOLEWORD,
            )

            pos = self.sc.SendScintilla(QsciScintilla.SCI_SEARCHINTARGET, len(target), target)

            if pos >= 0:
                self.sc.SendScintilla(QsciScintilla.SCI_ADDSELECTION, pos, pos + len(target))
            else:
                # 从头搜索
                self.sc.SendScintilla(QsciScintilla.SCI_SETTARGETSTART, 0)
                self.sc.SendScintilla(QsciScintilla.SCI_SETTARGETEND, length)
                pos = self.sc.SendScintilla(QsciScintilla.SCI_SEARCHINTARGET, len(target), target)
                if pos >= 0:
                    self.sc.SendScintilla(QsciScintilla.SCI_ADDSELECTION, pos, pos + len(target))

        except Exception as e:
            print(f"[EditorProxy] 选择下一个出现失败: {e}")
