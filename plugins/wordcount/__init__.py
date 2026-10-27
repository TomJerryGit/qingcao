# -*- coding: utf-8 -*-
"""字数统计插件"""
import re
import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QDockWidget, QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.plugins import PluginBase


class WordCountPanel(QDockWidget):
    """字数统计面板"""

    def __init__(self, api, main_window, parent=None):
        super().__init__("字数统计", parent or main_window)
        self.setObjectName("WordCountPanel")
        self.api = api
        self.main_window = main_window

        self._build_ui()
        self._apply_style()

        # 定时刷新
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 统计网格
        grid = QGridLayout()
        grid.setSpacing(8)

        self.stats = {}
        items = [
            ("chars", "字符数", "0"),
            ("chars_no_space", "不含空白", "0"),
            ("words", "词数", "0"),
            ("lines", "行数", "0"),
            ("paragraphs", "段落数", "0"),
            ("reading_time", "阅读时间", "0 分钟"),
        ]

        for i, (key, label, default) in enumerate(items):
            row = i // 2
            col = (i % 2) * 2

            lbl = QLabel(label + ":")
            lbl.setStyleSheet("color: #888;")
            grid.addWidget(lbl, row, col)

            val = QLabel(default)
            val.setStyleSheet(
                "color: #7ec850; font-weight: bold; "
                "font-size: 14px;"
            )
            grid.addWidget(val, row, col + 1)

            self.stats[key] = val

        layout.addLayout(grid)

        # 刷新按钮
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn)

        layout.addStretch()

        self.setWidget(container)

    def _apply_style(self):
        self.setStyleSheet("""
            QDockWidget {
                background-color: #252526;
                color: #d4d4d4;
            }
            QDockWidget::title {
                background-color: #2d2d2d;
                padding: 4px 8px;
            }
            QLabel { color: #d4d4d4; }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #1177bb; }
        """)

    def refresh(self):
        """刷新"""
        try:
            if self.api is None:
                return
            text = self.api.get_current_text()
            if text is None:
                return

            chars = len(text)
            chars_no_space = len(re.sub(r'\s', '', text))
            words = len(text.split())
            lines = text.count('\n') + 1 if text else 0
            paragraphs = len(
                [l for l in text.split('\n') if l.strip()]
            )
            # 阅读时间（按 300 字/分钟）
            minutes = max(1, chars // 300) if chars > 0 else 0

            self.stats['chars'].setText(str(chars))
            self.stats['chars_no_space'].setText(str(chars_no_space))
            self.stats['words'].setText(str(words))
            self.stats['lines'].setText(str(lines))
            self.stats['paragraphs'].setText(str(paragraphs))
            self.stats['reading_time'].setText(f"{minutes} 分钟")
        except Exception:
            pass


class Plugin(PluginBase):
    NAME = "wordcount"
    VERSION = "1.0.0"
    DESCRIPTION = "字数统计"
    AUTHOR = "TomJerry"

    def on_activate(self):
        self.api.log("字数统计插件已激活")
        # D3 修复：懒创建面板，避免反复启停堆叠 dock
        self._panel = None

        self.api.add_menu(
            "视图/字数统计",
            self.show_panel,
            shortcut="Ctrl+Alt+W"
        )

        # ---- v2.4 扩展点 ----
        self.api.register_settings_schema([
            {"key": "show_status", "label": "状态栏显示字数",
             "type": "bool", "default": True},
            {"key": "mode", "label": "统计口径", "type": "choice",
             "default": "chars",
             "choices": [("字符数", "chars"), ("单词数", "words")]},
        ])
        self._last_status_ts = 0.0
        self._status_item = None
        try:
            if bool(self.api.get_config("show_status", True)):
                self._status_item = self.api.add_status_item("字数: -")
        except Exception:
            self._status_item = None
        try:
            self.api.subscribe("editor_changed", self._on_editor_changed)
        except Exception:
            pass

    def _on_editor_changed(self, *args):
        """编辑器变化时刷新状态栏字数（0.5s 节流 + 大文件保护）"""
        if self._status_item is None:
            return
        now = time.time()
        if now - self._last_status_ts < 0.5:
            return
        self._last_status_ts = now
        try:
            editor = self.api.current_editor()
            length = 0
            try:
                length = editor.sc.length()
            except Exception:
                pass
            if length > 2 * 1024 * 1024:
                self._status_item.setText("字数: 大文件")
                return
            text = self.api.get_current_text() or ""
            if str(self.api.get_config("mode", "chars")) == "words":
                n = len(re.findall(r"\w+", text))
                self._status_item.setText("词数: %d" % n)
            else:
                self._status_item.setText("字数: %d" % len(text))
        except Exception:
            pass

    def on_deactivate(self):
        # D3: 显式销毁而非只 close
        if self._panel is not None:
            try:
                self._panel.timer.stop()
                self.api._host_window().removeDockWidget(self._panel)
            except Exception:
                pass
            self._panel.deleteLater()
            self._panel = None

    def _ensure_panel(self):
        """懒创建面板；首次显示时才实例化并加 dock"""
        if self._panel is None:
            self._panel = WordCountPanel(self.api, self.api._host_window())
            self.api._host_window().addDockWidget(
                Qt.RightDockWidgetArea, self._panel
            )

    def show_panel(self):
        self._ensure_panel()
        self._panel.setVisible(True)
        self._panel.raise_()
        self._panel.refresh()