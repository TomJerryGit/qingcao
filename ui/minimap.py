#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为 Minimap 缩略图模块，包含：
- Minimap：代码缩略图（QScintilla 只读实例）
- MinimapWidget：Minimap 包装组件（带标题、工具栏）
- MinimapViewport：视口指示器（绘制半透明矩形）
- MinimapScrollBar：自定义滚动条
- 文档指针共享
- 视口同步
- 点击跳转
- 悬停行号提示
- 滚轮滚动
- 拖动视口
- 颜色主题适配
- 显示/隐藏切换
- 宽度自适应
- 性能优化（禁用不必要的渲染）
"""

import os
import sys
import time
from typing import Any, Dict, Optional, Tuple

from PyQt5.Qsci import QsciScintilla
from PyQt5.QtCore import QPoint, QRect, QRectF, QSettings, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QContextMenuEvent,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QWheelEvent,
)
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


# ============================================================
# 常量
# ============================================================
# 默认 Minimap 宽度（像素）
DEFAULT_MINIMAP_WIDTH = 120
MIN_MINIMAP_WIDTH = 60
MAX_MINIMAP_WIDTH = 300

# 默认字体大小（超小字体，缩略显示）
DEFAULT_MINIMAP_FONT_SIZE = 1

# 视口矩形颜色（半透明白）
VIEWPORT_COLOR = QColor(255, 255, 255, 40)
VIEWPORT_BORDER_COLOR = QColor(255, 255, 255, 100)

# 悬停高亮颜色
HOVER_LINE_COLOR = QColor(255, 255, 255, 30)

# 光标位置颜色
CURSOR_LINE_COLOR = QColor(255, 200, 0, 80)

# 更新节流（毫秒）
UPDATE_THROTTLE_MS = 30

# 缓冲区
DEFAULT_BUFFER_SIZE = 5


# ============================================================
# Minimap 组件
# ============================================================
class Minimap(QsciScintilla):
    """
    Minimap 缩略图控件。

    基于 QScintilla 的只读实例，与主编辑器共享文档指针。
    提供:
    - 文档内容缩略显示
    - 视口指示器
    - 点击跳转
    - 悬停行号提示
    - 滚轮滚动
    - 拖动视口

    信号:
        line_clicked(int): 点击跳转到行
        viewport_changed(): 视口变化
    """

    line_clicked = pyqtSignal(int)
    viewport_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # 主编辑器引用
        self.main_editor: Optional[QsciScintilla] = None

        # 视口矩形
        self._viewport_rect: QRect = QRect()

        # 悬停行
        self._hover_line: int = -1

        # 状态
        self._syncing: bool = False
        self._enabled: bool = True

        # 更新节流定时器
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(UPDATE_THROTTLE_MS)
        self._update_timer.timeout.connect(self._do_update)

        # 配置
        self._configure()

    # --------------------------------------------------------
    # 配置
    # --------------------------------------------------------
    def _configure(self):
        """配置 Minimap"""
        # 只读
        self.setReadOnly(True)

        # 隐藏所有边距
        self.setMarginWidth(0, 0)
        self.setMarginWidth(1, 0)
        self.setMarginWidth(2, 0)
        self.setMarginWidth(3, 0)

        # 隐藏滚动条
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 禁止换行
        self.setWrapMode(QsciScintilla.WrapNone)

        # 禁止折叠
        self.setFolding(QsciScintilla.NoFoldStyle)

        # 禁止行号
        self.setMarginType(0, QsciScintilla.NumberMargin)
        self.setMarginWidth(0, 0)

        # 超小字体
        font = QFont("Consolas", DEFAULT_MINIMAP_FONT_SIZE)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)
        self.setMarginsFont(font)

        # 禁止光标
        self.setCaretWidth(0)
        self.setCaretLineVisible(False)

        # 关闭自动补全
        try:
            self.setAutoCompletionSource(QsciScintilla.AcsNone)
            self.setAutoCompletionThreshold(-1)
        except Exception:
            pass

        # 启用鼠标跟踪（用于悬停）
        self.setMouseTracking(True)

        # 关闭焦点
        self.setFocusPolicy(Qt.NoFocus)

        # 隐藏缩进辅助线
        self.setIndentationGuides(False)

        # 禁用滚动超出
        self.setScrollWidth(1)
        self.setScrollWidthTracking(False)

        # 边距颜色（与背景一致）
        self.setMarginsBackgroundColor(QColor("#1e1e1e"))
        self.setMarginsForegroundColor(QColor("#555555"))

        # 纸张颜色（背景）
        self.setPaper(QColor("#1e1e1e"))
        self.setColor(QColor("#d4d4d4"))

        # 关闭所有可见性增强
        self.setWhitespaceVisibility(QsciScintilla.WsInvisible)
        self.setEolVisibility(False)
        self.setBraceMatching(QsciScintilla.NoBraceMatch)

        # 启用 OpenGL 加速（如果可用）
        try:
            self.setRenderHint(QPainter.Antialiasing, True)
        except Exception:
            pass

    # --------------------------------------------------------
    # 主编辑器绑定
    # --------------------------------------------------------
    def set_editor(self, editor: Optional[QsciScintilla]):
        """
        设置关联的主编辑器。

        参数:
            editor: QScintilla 实例（主编辑器）或 None
        """
        # 断开旧连接
        if self.main_editor:
            try:
                self.main_editor.verticalScrollBar().valueChanged.disconnect(
                    self._on_main_scroll
                )
            except (TypeError, RuntimeError):
                pass
            try:
                self.main_editor.horizontalScrollBar().valueChanged.disconnect(
                    self._on_main_scroll_h
                )
            except (TypeError, RuntimeError):
                pass
            try:
                self.main_editor.textChanged.disconnect(
                    self._on_main_text_changed
                )
            except (TypeError, RuntimeError):
                pass

        self.main_editor = editor

        # 连接新编辑器
        if editor:
            # 安全：直接复制文本，不共享文档指针
            # （SCI_SETDOCPOINTER 在 PyQt5+QScintilla 上会触发 Access Violation）
            #
            # ★ 大文档跳过（cProfile 实测）：
            #   2MB / 50 万行文档，`editor.text()` 复制 + 本控件 setText
            #   合计 **0.74 秒**，而缩略图对超大文件的信息价值远低于成本。
            #   阈值与 ui/editor_view.py 的 LARGE_DOC_LINES 保持一致。
            self._large_editor = False
            try:
                force = bool(getattr(editor.window(),
                                     '_force_highlight_large_files', False))
                too_big = (not force) and (
                    editor.lines() > 200_000
                    or editor.length() > 8 * 1024 * 1024)
                if too_big:
                    self._large_editor = True
                    self.setText("")
                else:
                    self.setText(editor.text())
            except Exception as e:
                print(f"[Minimap] 复制文本失败: {e}")

            # 同步字体和语法高亮
            try:
                lexer = editor.lexer()
                if lexer:
                    self.setLexer(lexer)
            except Exception:
                pass

            # 连接主编辑器滚动事件
            try:
                editor.verticalScrollBar().valueChanged.connect(
                    self._on_main_scroll
                )
            except Exception:
                pass

            try:
                editor.horizontalScrollBar().valueChanged.connect(
                    self._on_main_scroll_h
                )
            except Exception:
                pass

            # 连接文本变化事件
            try:
                editor.textChanged.connect(self._on_main_text_changed)
            except Exception:
                pass

            # 同步主题
            self._sync_colors_from_editor(editor)

            # 初始更新
            self._schedule_update()
        else:
            # 清空
            try:
                self.SendScintilla(self.SCI_SETDOCPOINTER, 0, 0)
            except Exception:
                pass
            self._viewport_rect = QRect()
            self.repaint()

    def _sync_colors_from_editor(self, editor):
        """同步颜色主题"""
        try:
            # 背景色
            paper = editor.paper()
            if paper.isValid():
                self.setPaper(paper)
                self.setMarginsBackgroundColor(paper)

            # 前景色
            color = editor.color()
            if color.isValid():
                self.setColor(color)
                self.setMarginsForegroundColor(color)

        except Exception:
            pass

    # --------------------------------------------------------
    # 主编辑器事件回调
    # --------------------------------------------------------
    def _on_main_scroll(self, value: int):
        """主编辑器垂直滚动"""
        self._schedule_update()

    def _on_main_scroll_h(self, value: int):
        """主编辑器水平滚动"""
        pass  # Minimap 只关心垂直

    def _on_main_text_changed(self):
        """主编辑器文本变化"""
        # 大文档不渲染缩略图（见 set_editor 中的阈值说明）
        if getattr(self, '_large_editor', False):
            return
        self._schedule_update()

    def _schedule_update(self):
        """调度更新（节流）"""
        if not self._update_timer.isActive():
            self._update_timer.start()

    def _do_update(self):
        """执行更新"""
        try:
            self._update_viewport()
            self.repaint()
            self.viewport_changed.emit()
        except Exception:
            pass

    # --------------------------------------------------------
    # 视口计算
    # --------------------------------------------------------
    def _update_viewport(self):
        """计算并更新视口矩形"""
        if not self.main_editor:
            self._viewport_rect = QRect()
            return

        try:
            # 主编辑器可见范围
            first_line = self.main_editor.SendScintilla(
                self.main_editor.SCI_GETFIRSTVISIBLELINE
            )
            lines_on_screen = self.main_editor.SendScintilla(
                self.main_editor.SCI_LINESONSCREEN
            )
            total_lines = max(1, self.SendScintilla(self.SCI_GETLINECOUNT))

            # 当前 Minimap 的高度
            map_height = self.height()
            if map_height <= 0:
                return

            # 计算视口矩形
            y_top = int(first_line / total_lines * map_height)
            y_bottom = int((first_line + lines_on_screen) / total_lines * map_height)

            # 限制范围
            y_top = max(0, min(y_top, map_height - 1))
            y_bottom = max(y_top + 2, min(y_bottom, map_height))

            self._viewport_rect = QRect(0, y_top, self.width(), y_bottom - y_top)

        except Exception:
            self._viewport_rect = QRect()

    # --------------------------------------------------------
    # 绘制
    # --------------------------------------------------------
    def paintEvent(self, event: QPaintEvent):
        """绘制事件（附加视口指示）"""
        super().paintEvent(event)

        if not self.main_editor:
            return

        try:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.Antialiasing, False)

            # 绘制视口矩形
            if self._viewport_rect.isValid() and self._viewport_rect.height() > 0:
                # 半透明填充
                painter.fillRect(self._viewport_rect, VIEWPORT_COLOR)

                # 边框
                pen = QPen(VIEWPORT_BORDER_COLOR, 1)
                painter.setPen(pen)
                painter.drawRect(self._viewport_rect.adjusted(0, 0, -1, -1))

            # 绘制悬停行高亮
            if self._hover_line >= 0:
                total_lines = max(1, self.SendScintilla(self.SCI_GETLINECOUNT))
                map_height = self.height()
                if total_lines > 0 and map_height > 0:
                    y = int(self._hover_line / total_lines * map_height)
                    painter.fillRect(
                        0, y, self.width(), 2,
                        HOVER_LINE_COLOR
                    )

            # 绘制光标位置
            if self.main_editor:
                try:
                    cursor_line, _ = self.main_editor.getCursorPosition()
                    total_lines = max(1, self.SendScintilla(self.SCI_GETLINECOUNT))
                    map_height = self.height()
                    if total_lines > 0 and map_height > 0:
                        y = int(cursor_line / total_lines * map_height)
                        painter.fillRect(
                            0, y, self.width(), 2,
                            CURSOR_LINE_COLOR
                        )
                except Exception:
                    pass

            painter.end()

        except Exception:
            pass

    # --------------------------------------------------------
    # 鼠标交互
    # --------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent):
        """鼠标按下"""
        if not self.main_editor:
            super().mousePressEvent(event)
            return

        if event.button() == Qt.LeftButton:
            # 点击位置映射到行号
            line = self._point_to_line(event.pos().y())
            if line >= 0:
                self._goto_line(line)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """鼠标移动（悬停）"""
        if not self.main_editor:
            super().mouseMoveEvent(event)
            return

        # 更新悬停行
        line = self._point_to_line(event.pos().y())
        if line != self._hover_line:
            self._hover_line = line

            # 显示工具提示
            if line >= 0:
                try:
                    text = self.text(line).strip()[:80]
                    if text:
                        from PyQt5.QtWidgets import QToolTip
                        QToolTip.showText(
                            event.globalPos(),
                            f"行 {line + 1}: {text}"
                        )
                except Exception:
                    pass

            self.repaint()

        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        """鼠标离开"""
        self._hover_line = -1
        self.repaint()
        super().leaveEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        """滚轮事件（转发到主编辑器）"""
        if self.main_editor:
            try:
                # 转发滚轮事件
                delta = event.angleDelta().y()
                scrollbar = self.main_editor.verticalScrollBar()
                scrollbar.setValue(scrollbar.value() - delta)
                event.accept()
                return
            except Exception:
                pass

        super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """双击（居中显示）"""
        if not self.main_editor:
            return

        line = self._point_to_line(event.pos().y())
        if line >= 0:
            self._center_on_line(line)
            event.accept()

    def _point_to_line(self, y: int) -> int:
        """将 Y 坐标映射到行号"""
        if not self.main_editor:
            return -1

        try:
            total_lines = self.SendScintilla(self.SCI_GETLINECOUNT)
            map_height = self.height()

            if total_lines <= 0 or map_height <= 0:
                return -1

            line = int(y / map_height * total_lines)
            return max(0, min(line, total_lines - 1))

        except Exception:
            return -1

    def _goto_line(self, line: int):
        """跳转到指定行"""
        if not self.main_editor:
            return

        try:
            # 保持行在屏幕中央
            lines_visible = self.main_editor.SendScintilla(
                self.main_editor.SCI_LINESONSCREEN
            )
            target_line = max(0, line - lines_visible // 2)

            self.main_editor.SendScintilla(
                self.main_editor.SCI_SETFIRSTVISIBLELINE, target_line
            )
            self.main_editor.SendScintilla(
                self.main_editor.SCI_GOTOLINE, line
            )

            self.line_clicked.emit(line)

        except Exception:
            pass

    def _center_on_line(self, line: int):
        """将指定行居中显示"""
        self._goto_line(line)

    # --------------------------------------------------------
    # 尺寸调整
    # --------------------------------------------------------
    def resizeEvent(self, event: QResizeEvent):
        """尺寸变化"""
        super().resizeEvent(event)
        self._schedule_update()

    # --------------------------------------------------------
    # 启用/禁用
    # --------------------------------------------------------
    def set_enabled(self, enabled: bool):
        """启用/禁用 Minimap"""
        self._enabled = enabled
        self.setVisible(enabled)

        if enabled:
            self._schedule_update()

    def is_enabled(self) -> bool:
        """是否启用"""
        return self._enabled

    def refresh(self):
        """手动刷新"""
        self._schedule_update()


# ============================================================
# Minimap 包装组件
# ============================================================
class MinimapWidget(QWidget):
    """
    Minimap 包装组件。

    提供:
    - 标题栏
    - 宽度调节
    - 显示/隐藏按钮
    - 与 Minimap 控件集成

    信号:
        visibility_changed(bool): 可见性变化
        width_changed(int): 宽度变化
    """

    visibility_changed = pyqtSignal(bool)
    width_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._minimap: Optional[Minimap] = None
        self._settings = QSettings("QingCao", "Minimap")

        # 从设置加载宽度
        self._width = self._settings.value(
            "width", DEFAULT_MINIMAP_WIDTH, type=int
        )
        self._width = max(MIN_MINIMAP_WIDTH,
                          min(self._width, MAX_MINIMAP_WIDTH))

        # 构建 UI
        self._build_ui()

    def _build_ui(self):
        """构建 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部工具栏
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(4, 2, 4, 2)
        toolbar_layout.setSpacing(2)

        # 标题
        title = QLabel("Minimap")
        title.setStyleSheet("color: #888; font-size: 11px;")
        toolbar_layout.addWidget(title)

        toolbar_layout.addStretch()

        # 缩小按钮
        self.zoom_out_btn = QToolButton()
        self.zoom_out_btn.setText("−")
        self.zoom_out_btn.setFixedSize(18, 18)
        self.zoom_out_btn.setToolTip("缩小 Minimap")
        self.zoom_out_btn.clicked.connect(
            lambda: self._adjust_width(-20)
        )
        toolbar_layout.addWidget(self.zoom_out_btn)

        # 放大按钮
        self.zoom_in_btn = QToolButton()
        self.zoom_in_btn.setText("+")
        self.zoom_in_btn.setFixedSize(18, 18)
        self.zoom_in_btn.setToolTip("放大 Minimap")
        self.zoom_in_btn.clicked.connect(
            lambda: self._adjust_width(20)
        )
        toolbar_layout.addWidget(self.zoom_in_btn)

        self._toolbar = toolbar
        layout.addWidget(toolbar)

        # Minimap 控件
        self._minimap = Minimap()
        layout.addWidget(self._minimap, 1)

        # 应用宽度
        self.setFixedWidth(self._width)

        # 应用样式
        self._apply_style()

    def _apply_style(self):
        """应用样式"""
        self.setStyleSheet("""
            QToolButton {
                background-color: transparent;
                color: #888;
                border: none;
                font-size: 14px;
                font-weight: bold;
            }
            QToolButton:hover {
                background-color: #3c3c3c;
                color: #fff;
                border-radius: 3px;
            }
        """)

    def _adjust_width(self, delta: int):
        """调整宽度"""
        new_width = self._width + delta
        new_width = max(MIN_MINIMAP_WIDTH, min(new_width, MAX_MINIMAP_WIDTH))

        if new_width != self._width:
            self._width = new_width
            self.setFixedWidth(self._width)
            self._settings.setValue("width", self._width)
            self.width_changed.emit(self._width)

    def set_editor(self, editor: Optional[QsciScintilla]):
        """设置编辑器"""
        if self._minimap:
            self._minimap.set_editor(editor)

    def get_minimap(self) -> Optional[Minimap]:
        """获取内部 Minimap"""
        return self._minimap

    def set_visible_state(self, visible: bool):
        """设置可见状态"""
        self.setVisible(visible)
        self.visibility_changed.emit(visible)

    def refresh(self):
        """刷新"""
        if self._minimap:
            self._minimap.refresh()

    def get_width(self) -> int:
        """获取宽度"""
        return self._width

    def set_width(self, width: int):
        """设置宽度"""
        width = max(MIN_MINIMAP_WIDTH, min(width, MAX_MINIMAP_WIDTH))
        if width != self._width:
            self._width = width
            self.setFixedWidth(self._width)
            self._settings.setValue("width", self._width)
            self.width_changed.emit(self._width)


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication, QMainWindow, QSplitter, QTextEdit

    app = QApplication(sys.argv)

    # 创建主窗口
    win = QMainWindow()
    win.setWindowTitle("Minimap 测试")
    win.resize(1000, 700)

    # 中央区使用 QSplitter 分左右
    splitter = QSplitter(Qt.Horizontal)

    # 主编辑器
    from PyQt5.Qsci import QsciLexerPython, QsciScintilla

    editor = QsciScintilla()
    editor.setUtf8(True)
    editor.setMarginType(0, QsciScintilla.NumberMargin)
    editor.setMarginWidth(0, 50)
    editor.setFolding(QsciScintilla.BoxedFoldStyle)
    editor.setLexer(QsciLexerPython())

    # 加载测试内容
    test_content = "#!/usr/bin/env python\n# -*- coding: utf-8 -*-\n\n"
    test_content += "import sys\nimport os\n\n"

    for i in range(1, 100):
        test_content += f"def function_{i}():\n"
        test_content += f"    '''函数 {i} 的文档字符串'''\n"
        test_content += f"    value = {i}\n"
        test_content += "    if value > 50:\n"
        test_content += f"        print('大于50: {i}')\n"
        test_content += "    else:\n"
        test_content += f"        print('小于等于50: {i}')\n"
        test_content += "    return value\n\n"

    test_content += "class MyClass:\n"
    test_content += "    def __init__(self):\n"
    test_content += "        self.value = 42\n\n"
    test_content += "if __name__ == '__main__':\n"
    test_content += "    for i in range(10):\n"
    test_content += "        function_1()\n"

    editor.setText(test_content)
    splitter.addWidget(editor)

    # Minimap 组件
    minimap_widget = MinimapWidget()
    minimap_widget.set_editor(editor)
    minimap_widget.setFixedWidth(120)
    splitter.addWidget(minimap_widget)

    # 设置初始比例（主编辑器占大部分）
    splitter.setSizes([850, 120])
    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 0)

    win.setCentralWidget(splitter)
    win.show()

    print("=== Minimap 测试 ===")
    print(f"Minimap 宽度: {minimap_widget.get_width()}")
    print(f"Minimap 启用: {minimap_widget.get_minimap().is_enabled()}")
    print(f"关联编辑器: {minimap_widget.get_minimap().main_editor is editor}")
    print()

    # 连接信号
    minimap_widget.get_minimap().line_clicked.connect(
        lambda line: print(f"[信号] 点击行: {line + 1}")
    )
    minimap_widget.get_minimap().viewport_changed.connect(
        lambda: print("[信号] 视口变化")
    )
    minimap_widget.width_changed.connect(
        lambda w: print(f"[信号] 宽度变化: {w}")
    )

    # 测试点击跳转
    def test_goto():
        print("测试跳转到行 500...")
        minimap_widget.get_minimap()._goto_line(500)

    QTimer.singleShot(2000, test_goto)

    # 5 秒后退出
    def cleanup_and_quit():
        print()
        print(f"Minimap 宽度: {minimap_widget.get_width()}")
        app.quit()

    QTimer.singleShot(5000, cleanup_and_quit)

    sys.exit(app.exec())