# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""从 core/editor.py 拆出的 bookmarks 职责（v2.23 D1）。"""

from core.editor_common import *  # noqa: F401,F403
from core.editor_common import (  # noqa: F401
    _EOL_SPLIT_RE,
    _normalize_bytes,
    _trim_trailing_ws_keep_eol,
)


class EditorBookmarksMixin:
    # ========================================================
    # 书签
    # ========================================================
    def toggle_bookmark(self):
        """切换当前行书签"""
        try:
            line, _ = self.sc.getCursorPosition()

            if self.sc.markersAtLine(line) & (1 << MARKER_BOOKMARK):
                self.sc.markerDelete(line, MARKER_BOOKMARK)
                self.document.remove_bookmark(line)
            else:
                self.sc.markerAdd(line, MARKER_BOOKMARK)
                self.document.add_bookmark(line)
        except Exception as e:
            print(f"[EditorProxy] 切换书签失败: {e}")

    def next_bookmark(self):
        """跳转到下一个书签"""
        try:
            line, _ = self.sc.getCursorPosition()
            next_line = self.document.next_bookmark(line)
            if next_line is not None:
                self.sc.setCursorPosition(next_line, 0)
                self.sc.ensureLineVisible(next_line)
        except Exception as e:
            print(f"[EditorProxy] 跳转下一书签失败: {e}")

    def prev_bookmark(self):
        """跳转到上一个书签"""
        try:
            line, _ = self.sc.getCursorPosition()
            prev_line = self.document.prev_bookmark(line)
            if prev_line is not None:
                self.sc.setCursorPosition(prev_line, 0)
                self.sc.ensureLineVisible(prev_line)
        except Exception as e:
            print(f"[EditorProxy] 跳转上一书签失败: {e}")

    def clear_bookmarks(self):
        """清除所有书签"""
        try:
            self.sc.markerDeleteAll(MARKER_BOOKMARK)
            self.document.clear_bookmarks()
        except Exception:
            pass

    # ========================================================
    # 断点与调试执行行（D3）
    # ========================================================
    def _ensure_debug_markers(self):
        """按需定义调试相关标记（幂等）。

        D3 背景：`MARKER_BREAKPOINT` 此前**只被 markerDefine 定义过图例**，
        全仓没有任何 markerAdd / markerDelete —— 也就是说"断点"这个功能
        根本不存在。这里补齐标记定义，真正的读写见下面的方法。
        """
        if getattr(self, "_debug_markers_ready", False):
            return
        try:
            self.sc.markerDefine(QsciScintilla.Circle, MARKER_BREAKPOINT)
            self.sc.setMarkerBackgroundColor(QColor("#ff0000"), MARKER_BREAKPOINT)
        except Exception:
            pass
        # 当前执行行：Background 标记（不受任何边距是否可见影响）
        try:
            self.sc.markerDefine(QsciScintilla.Background, MARKER_DEBUG_LINE)
            self.sc.setMarkerBackgroundColor(QColor("#ffcc00"), MARKER_DEBUG_LINE)
        except Exception:
            pass
        self._debug_markers_ready = True

    def get_breakpoints(self) -> List[int]:
        """返回本文件已设断点的行号列表（升序，0 基行号）。

        优先用控件自身的 `get_breakpoints()`（ui/editor_view.py 的权威
        实现）；控件未实现时（裸 QsciScintilla / 单测）自行遍历。
        """
        try:
            getter = getattr(self.sc, "get_breakpoints", None)
            if callable(getter):
                return sorted(int(x) for x in getter())
            total = int(self.sc.lines())
            return [
                line
                for line in range(total)
                if self.sc.markersAtLine(line) & (1 << MARKER_BREAKPOINT)
            ]
        except Exception as e:
            print(f"[EditorProxy] 读取断点失败: {e}")
            return []

    def _is_valid_break_line(self, line: int) -> bool:
        """行号是否落在当前文档范围内（0 基）。

        QScintilla 的 `markerAdd()` 对越界行是**静默失败**的，因此调用前
        必须自己校验，否则会出现"返回 True 但断点没设上"的假成功。
        """
        try:
            line = int(line)
        except (TypeError, ValueError):
            return False
        if line < 0:
            return False
        try:
            total = max(1, int(self.sc.lines()))
        except Exception:
            return True
        return line < total

    def add_breakpoint(self, line: int) -> bool:
        """在指定行设置断点（幂等）。行号越界时返回 False。"""
        try:
            if not self._is_valid_break_line(line):
                return False
            line = int(line)
            self._ensure_debug_markers()
            if not (self.sc.markersAtLine(line) & (1 << MARKER_BREAKPOINT)):
                self.sc.markerAdd(line, MARKER_BREAKPOINT)
            self._emit_breakpoints_changed()
            return True
        except Exception as e:
            print(f"[EditorProxy] 设置断点失败: {e}")
            return False

    def toggle_breakpoint(self, line: Optional[int] = None) -> bool:
        """切换断点（默认当前行）。

        与书签（`toggle_bookmark`）对称。优先委托给控件自身的
        `_toggle_breakpoint_at_line()`（ui/editor_view.py 的权威实现）；
        控件未实现时直接操作 marker。

        行号越界（空文件 / 超出文件末尾）时返回 **False** 且不做修改 ——
        返回值必须与实际效果一致。
        """
        try:
            if line is None:
                line, _ = self.sc.getCursorPosition()
            if not self._is_valid_break_line(line):
                return False
            line = int(line)

            toggler = getattr(self.sc, "_toggle_breakpoint_at_line", None)
            if callable(toggler):
                if not toggler(line):
                    return False
            else:
                self._ensure_debug_markers()
                if self.sc.markersAtLine(line) & (1 << MARKER_BREAKPOINT):
                    self.sc.markerDelete(line, MARKER_BREAKPOINT)
                else:
                    self.sc.markerAdd(line, MARKER_BREAKPOINT)

            self._emit_breakpoints_changed()
            return True
        except Exception as e:
            print(f"[EditorProxy] 切换断点失败: {e}")
            return False

    def clear_breakpoints(self) -> int:
        """清除所有断点，返回被清除的断点数量。"""
        try:
            count = len(self.get_breakpoints())
            self.sc.markerDeleteAll(MARKER_BREAKPOINT)
            self._emit_breakpoints_changed()
            return count
        except Exception as e:
            print(f"[EditorProxy] 清除断点失败: {e}")
            return 0

    def _emit_breakpoints_changed(self):
        """把最新断点集合广播出去（调试器用它同步到被调试进程）。"""
        try:
            self.breakpoints_changed.emit(self.get_breakpoints())
        except Exception:
            pass

    def highlight_debug_line(self, line: int) -> bool:
        """高亮调试器**当前停住的行**（D3 用户路径 1）。"""
        try:
            self._ensure_debug_markers()
            self.sc.markerDeleteAll(MARKER_DEBUG_LINE)
            handle = self.sc.markerAdd(int(line), MARKER_DEBUG_LINE)
            self.sc.ensureLineVisible(int(line))
            return handle >= 0
        except Exception as e:
            print(f"[EditorProxy] 高亮调试行失败: {e}")
            return False

    def clear_debug_line(self):
        """清除"当前执行行"高亮。"""
        try:
            self.sc.markerDeleteAll(MARKER_DEBUG_LINE)
        except Exception:
            pass
