# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""绘制/鼠标/调试标记职责（v2.24 拆出）。"""

from ui.editor_view_common import *  # noqa: F401,F403,F405


class EditorPaintMixin:
    def paintEvent(self, event):
        """
        重写绘制事件，绘制彩虹线。

        性能优化说明（P2-2）:
            - 缓存行高，避免每级缩进都查询 SCI_TEXTHEIGHT。
            - 只在缩进 > 0 的行上绘制，跳过空白行。
            - 使用局部变量减少属性查找。
            - 一次性读取可见行范围，避免在循环中重复计算。
        """
        super().paintEvent(event)

        if not self._rainbow_enabled:
            return

        try:
            painter = QPainter(self.viewport())

            # 获取可见行范围
            first_visible = self.SendScintilla(QsciScintilla.SCI_GETFIRSTVISIBLELINE)
            lines_on_screen = self.SendScintilla(QsciScintilla.SCI_LINESONSCREEN)

            tab_width = max(1, self.tabWidth())

            for i in range(lines_on_screen + 1):
                line = first_visible + i

                try:
                    line_text = self.text(line)
                except Exception:
                    continue

                if not line_text:
                    continue

                # 计算缩进级别
                stripped = line_text.lstrip()
                indent = len(line_text) - len(stripped)

                if indent == 0:
                    continue

                level = indent // tab_width
                if level <= 0:
                    continue

                # 缓存行高（每次循环只查一次）
                line_height = self.SendScintilla(QsciScintilla.SCI_TEXTHEIGHT, line)

                # 行起始字节位置
                line_start = self.SendScintilla(QsciScintilla.SCI_POSITIONFROMLINE, line)

                # 绘制每一层的彩虹线
                for lv in range(level):
                    color = RAINBOW_COLORS[lv % len(RAINBOW_COLORS)]
                    painter.setPen(QPen(color, 1))

                    # 计算 x 坐标
                    char_pos = lv * tab_width
                    if char_pos >= len(line_text):
                        continue

                    pos = line_start + char_pos

                    x = self.SendScintilla(QsciScintilla.SCI_POINTXFROMPOSITION, 0, pos)
                    y = self.SendScintilla(QsciScintilla.SCI_POINTYFROMPOSITION, 0, pos)

                    if x < 0 or y < 0:
                        continue

                    painter.drawLine(x, y, x, y + line_height)

            painter.end()

        except Exception:
            pass

    # ========================================================
    # 鼠标事件
    # ========================================================

    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下事件"""
        # Ctrl+点击：添加多光标
        if event.modifiers() == Qt.ControlModifier and event.button() == Qt.LeftButton:
            pos = self.SendScintilla(
                QsciScintilla.SCI_POSITIONFROMPOINT, event.pos().x(), event.pos().y()
            )
            if pos >= 0:
                self.proxy.add_cursor_at(pos)
                event.accept()
                return

        # Alt+点击：切换书签
        if event.modifiers() == Qt.AltModifier and event.button() == Qt.LeftButton:
            pos = self.SendScintilla(
                QsciScintilla.SCI_POSITIONFROMPOINT, event.pos().x(), event.pos().y()
            )
            if pos >= 0:
                line = self.SendScintilla(QsciScintilla.SCI_LINEFROMPOSITION, pos)
                self._toggle_bookmark_at_line(line)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """双击事件"""
        # 双击行号边距：切换书签
        if event.pos().x() < 50:
            line, _ = self.getCursorPosition()
            self._toggle_bookmark_at_line(line)
            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    def _toggle_bookmark_at_line(self, line: int):
        """在指定行切换书签"""
        try:
            if self.markersAtLine(line) & (1 << MARKER_BOOKMARK):
                self.markerDelete(line, MARKER_BOOKMARK)
                self.document.remove_bookmark(line)
            else:
                self.markerAdd(line, MARKER_BOOKMARK)
                self.document.add_bookmark(line)
        except Exception:
            pass

    # ========================================================
    # 断点（D3）
    # ========================================================

    def _on_margin_clicked(self, margin: int, line: int, modifiers):
        """装订线单击 → 切换断点。

        只有 margin 1（紧贴行号右侧的专用断点装订线）会切换断点。
        行号边距（margin 0）**刻意保持不可点**：那里已有"双击切换
        书签"的交互，而 Qt 在敏感边距上会吞掉 mousePressEvent，
        两者叠加会让"双击加书签"顺带留下一个断点。

        另外两个等价入口：F9（编辑器内，见 keyPressEvent）与右键菜单。
        """
        try:
            if margin == 1:
                self._toggle_breakpoint_at_line(line)
                return True
        except Exception as e:
            print(f"[EditorWidget] 切换断点失败: {e}")
        return False

    def _toggle_breakpoint_at_line(self, line: int):
        """在指定行切换断点标记（与 `_toggle_bookmark_at_line` 对称）。

        行号越界（空文件 / 行号超过文件末尾）时返回 **False 且不做任何
        修改**：QScintilla 的 `markerAdd()` 对越界行是**静默失败**的，
        若此处无条件 `return True`，调用方会以为断点设上了而实际没有
        —— 返回值必须与实际效果一致。
        """
        try:
            line = int(line)
            if line < 0 or line >= max(1, int(self.lines())):
                return False
            if self.markersAtLine(line) & (1 << MARKER_BREAKPOINT):
                self.markerDelete(line, MARKER_BREAKPOINT)
            else:
                self.markerAdd(line, MARKER_BREAKPOINT)
            # 通知代理（它会再广播 breakpoints_changed 给调试器）
            try:
                proxy = getattr(self, "proxy", None)
                if proxy is not None:
                    proxy._emit_breakpoints_changed()
            except Exception:
                pass
            return True
        except Exception as e:
            print(f"[EditorWidget] 切换断点失败: {e}")
            return False

    def get_breakpoints(self):
        """返回已设断点的行号列表（升序）。"""
        try:
            total = self.lines()
            return [
                line for line in range(total) if self.markersAtLine(line) & (1 << MARKER_BREAKPOINT)
            ]
        except Exception as e:
            print(f"[EditorWidget] 读取断点失败: {e}")
            return []

    def clear_breakpoints(self):
        """清除本编辑器的所有断点，返回清除数量。"""
        try:
            lines = self.get_breakpoints()
            self.markerDeleteAll(MARKER_BREAKPOINT)
            try:
                proxy = getattr(self, "proxy", None)
                if proxy is not None:
                    proxy._emit_breakpoints_changed()
            except Exception:
                pass
            return len(lines)
        except Exception as e:
            print(f"[EditorWidget] 清除断点失败: {e}")
            return 0

    def highlight_debug_line(self, line: int):
        """高亮调试器当前停住的行（D3）。"""
        try:
            self.markerDeleteAll(MARKER_DEBUG_LINE)
            handle = self.markerAdd(int(line), MARKER_DEBUG_LINE)
            self.ensureLineVisible(int(line))
            return handle >= 0
        except Exception as e:
            print(f"[EditorWidget] 高亮调试行失败: {e}")
            return False

    def clear_debug_line(self):
        """清除"当前执行行"高亮。"""
        try:
            self.markerDeleteAll(MARKER_DEBUG_LINE)
        except Exception:
            pass

    # ========================================================
    # 右键上下文菜单
    # ========================================================
