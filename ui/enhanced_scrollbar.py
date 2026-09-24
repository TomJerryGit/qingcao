# -*- coding: utf-8 -*-
"""增强滚动条（带标记）"""
from PyQt5.QtWidgets import QScrollBar, QWidget
from PyQt5.QtCore import Qt, QRect, QSize
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush


class EnhancedScrollBar(QScrollBar):
    """带标记的滚动条"""

    def __init__(self, orientation=Qt.Vertical, parent=None):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)

        # 标记：{line: (color, tooltip)}
        self.markers = {}

        # 搜索高亮
        self.search_markers = []

        # 当前视口
        self.viewport_start = 0
        self.viewport_end = 0
        self.total_lines = 1

    def set_markers(self, markers):
        """设置标记

        markers: [(line, color_hex, tooltip), ...]
        """
        self.markers = {}
        for line, color, tooltip in markers:
            self.markers.setdefault(line, []).append((color, tooltip))
        self.update()

    def add_marker(self, line, color="#f14c4c", tooltip=""):
        """添加单个标记"""
        self.markers.setdefault(line, []).append((color, tooltip))
        self.update()

    def clear_markers(self):
        """清空标记"""
        self.markers.clear()
        self.update()

    def set_search_markers(self, lines):
        """设置搜索标记"""
        self.search_markers = list(lines)
        self.update()

    def set_viewport(self, start_line, end_line, total_lines):
        """设置视口范围"""
        self.viewport_start = start_line
        self.viewport_end = end_line
        self.total_lines = max(1, total_lines)
        self.update()

    def paintEvent(self, event):
        """重写绘制"""
        super().paintEvent(event)

        if self.total_lines <= 0:
            return

        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, False)

            width = self.width()
            height = self.height()

            # 绘制搜索标记（先画，会被覆盖）
            pen = QPen(QColor(255, 255, 0, 150))
            pen.setWidth(2)
            painter.setPen(pen)
            for line in self.search_markers:
                y = int(line / self.total_lines * height)
                painter.drawPoint(width - 3, y)

            # 绘制错误/警告标记
            for line, marks in self.markers.items():
                y = int(line / self.total_lines * height)
                # 取最严重的
                color = "#f14c4c"
                for c, _ in marks:
                    if c == "#f14c4c":
                        color = c
                        break
                    color = c

                painter.fillRect(
                    0, y - 1, 3, 3, QColor(color)
                )

            # 绘制视口高亮（半透明）
            if self.viewport_end > self.viewport_start:
                vp_start_y = int(
                    self.viewport_start / self.total_lines * height
                )
                vp_end_y = int(
                    self.viewport_end / self.total_lines * height
                )
                painter.fillRect(
                    0, vp_start_y, width,
                    max(3, vp_end_y - vp_start_y),
                    QColor(255, 255, 255, 30)
                )

            painter.end()
        except Exception:
            pass

    def mousePressEvent(self, event):
        """点击跳转"""
        if event.button() == Qt.LeftButton:
            # 计算点击位置对应的行
            y = event.pos().y()
            line = int(y / self.height() * self.total_lines)
            # 发射自定义信号
            if hasattr(self, '_on_click'):
                self._on_click(line)
        super().mousePressEvent(event)