# -*- coding: utf-8 -*-
"""日志实时监视插件"""

import os

from PyQt5.QtCore import QFileSystemWatcher, Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.plugins import PluginBase


def filter_lines(text, pattern):
    """按正则/子串过滤日志行；空模式返回原文。"""
    if not pattern:
        return text or ""
    try:
        import re as _re

        rx = _re.compile(pattern)
        matcher = rx.search
    except Exception:
        matcher = lambda s: pattern in s  # noqa: E731
    return "\n".join(line for line in (text or "").splitlines() if matcher(line))


class LogTailPanel(QDockWidget):
    """日志监视面板"""

    def __init__(self, parent=None):
        super().__init__("日志监视", parent)
        self.setObjectName("LogTailPanel")

        self.current_file = None
        self.last_size = 0

        self._build_ui()
        self._apply_style()

        # 文件监听
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._on_file_changed)

        # 定时轮询（防止 watcher 失效）
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._poll)
        self.timer.start()
        self._files = []
        self._paused = False

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)

        # 工具栏
        toolbar = QHBoxLayout()

        from PyQt5.QtWidgets import QComboBox, QLineEdit

        self.file_combo = QComboBox()
        self.file_combo.setMinimumWidth(180)
        self.file_combo.activated.connect(self._on_combo_activated)
        toolbar.addWidget(self.file_combo, 1)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("过滤（正则/子串）")
        self.filter_edit.setMaximumWidth(180)
        self.filter_edit.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self.filter_edit)

        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self._set_paused)
        toolbar.addWidget(self.pause_btn)

        self.file_label = QLabel("(未选择)")
        self.file_label.setStyleSheet("color: #888;")
        toolbar.addWidget(self.file_label)

        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(lambda: self.view.clear())
        toolbar.addWidget(clear_btn)

        layout.addLayout(toolbar)

        # 输出
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setFont(QFont("Consolas", 10))
        self.view.setMaximumBlockCount(5000)
        layout.addWidget(self.view)

        self.setWidget(container)

    def _apply_style(self):
        self._base_qss = """
            QDockWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
            QDockWidget::title {
                background-color: #2d2d2d;
                padding: 4px 8px;
            }
            QPlainTextEdit {
                background-color: #0d0d0d;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                font-family: Consolas, monospace;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 8px;
            }
"""
        self.setStyleSheet(self._base_qss)

    def refresh_theme(self, theme):
        """主题切换：按当前主题适配面板 QSS（v2.14 插件 UI 统一）"""
        try:
            from infrastructure.theme_loader import adapt_qss_colors

            base = getattr(self, "_base_qss", "")
            if base:
                self.setStyleSheet(adapt_qss_colors(base, theme))
        except Exception:
            pass

    def watch(self, filepath):
        """监视文件；filepath=None 表示停止监视"""
        # 停止监视（修复：原实现直接 basename(None) 会崩）
        if not filepath:
            if self.current_file and self.current_file in self.watcher.files():
                self.watcher.removePath(self.current_file)
            self.current_file = None
            self.last_size = 0
            self.file_label.setText("(未选择)")
            return

        if self.current_file == filepath:
            return

        if self.current_file and self.current_file in self.watcher.files():
            self.watcher.removePath(self.current_file)

        self.current_file = filepath
        if filepath not in self._files:
            self._files.append(filepath)
        if self.file_combo.findText(filepath) < 0:
            self.file_combo.addItem(filepath)
            self.file_combo.setCurrentText(filepath)
        self.file_label.setText(os.path.basename(filepath))

        if filepath and os.path.exists(filepath):
            self.watcher.addPath(filepath)
            self.last_size = 0
            self.view.clear()
            # 读取全部
            self._read_all()

    def _on_combo_activated(self, _index):
        path = self.file_combo.currentText().strip()
        if path and path != self.current_file:
            self.watch(path)

    def _set_paused(self, paused):
        self._paused = bool(paused)
        self.pause_btn.setText("继续" if self._paused else "暂停")

    def _apply_filter(self, _text=""):
        if not self.current_file:
            return
        try:
            with open(self.current_file, encoding="utf-8", errors="replace") as f:
                content = f.read()
            self.view.setPlainText(filter_lines(content, self.filter_edit.text()))
        except Exception:
            pass

    def _read_all(self):
        """读取全部内容"""
        if not self.current_file or not os.path.exists(self.current_file):
            return
        try:
            with open(self.current_file, encoding="utf-8", errors="replace") as f:
                content = f.read()
            self.view.setPlainText(content)
            self.last_size = os.path.getsize(self.current_file)
            # 滚动到底
            sb = self.view.verticalScrollBar()
            sb.setValue(sb.maximum())
        except Exception as e:
            self.view.appendPlainText(f"读取失败: {e}")

    def _on_file_changed(self, path):
        """文件变化"""
        # 重新添加监听（某些系统上会失效）
        if path not in self.watcher.files() and os.path.exists(path):
            self.watcher.addPath(path)
        self._read_tail()

    def _poll(self):
        """轮询"""
        if self._paused:
            return
        if not self.current_file or not os.path.exists(self.current_file):
            return
        try:
            size = os.path.getsize(self.current_file)
            if size != self.last_size:
                self._read_tail()
        except Exception:
            pass

    def _read_tail(self):
        """读取新增内容"""
        try:
            size = os.path.getsize(self.current_file)
            if size < self.last_size:
                # 文件被截断，重读
                self.last_size = 0
                self.view.clear()

            with open(self.current_file, encoding="utf-8", errors="replace") as f:
                f.seek(self.last_size)
                new_content = f.read()
                self.last_size = size

            if new_content:
                if self.filter_edit.text().strip():
                    self._apply_filter()
                    return
                self.view.appendPlainText(new_content.rstrip("\n"))
                sb = self.view.verticalScrollBar()
                sb.setValue(sb.maximum())
        except Exception as e:
            print(f"[LogTail] 读取失败: {e}")


class Plugin(PluginBase):
    NAME = "logtail"
    VERSION = "1.0.0"
    DESCRIPTION = "日志实时监视"
    AUTHOR = "TomJerry"

    def on_activate(self):
        self.api.log("日志监视插件已激活")
        self._panel = None

        self.api.add_menu("工具/日志监视/监视当前文件", self.watch_current, shortcut="Ctrl+Alt+L")
        self.api.add_menu("工具/日志监视/停止监视", self.stop_watching)
        self.api.add_menu("工具/日志监视/打开面板", self.show_panel)
        self._remote_panel = None
        self._watching = False
        if getattr(self.api, "is_isolated", False):
            try:
                self._remote_panel = self.api.register_remote_panel(
                    "日志监视", [], self._remote_refresh, kind="text"
                )
            except Exception as e:
                self.api.log("远程面板注册失败: %s" % e, "warning")
        # v2.4 扩展点
        self.on_activate_extension_points()

    def on_activate_extension_points(self):
        """v2.4 扩展点（由 on_activate 末尾调用）"""
        self.api.register_settings_schema(
            [
                {
                    "key": "max_lines",
                    "label": "面板最多保留行数",
                    "type": "int",
                    "default": 5000,
                    "min": 100,
                    "max": 200000,
                },
            ]
        )
        self._status = self.api.add_status_item("监视: 未启动")

    def on_deactivate(self):
        if getattr(self.api, "is_isolated", False):
            return
        if self._panel:
            self._panel.close()

    def _remote_refresh(self, text):
        text = text or ""
        try:
            max_lines = int(self.api.get_config("max_lines", 5000) or 5000)
        except Exception:
            max_lines = 5000
        lines = text.splitlines()[-max(100, min(max_lines, 200000)) :]
        if not self._watching:
            return "(未监视：使用「工具 → 日志监视 → 监视当前文件」)"
        return "\n".join(lines) or "(当前文件为空)"

    def show_panel(self):
        """显示面板"""
        if getattr(self.api, "is_isolated", False):
            if self._remote_panel is None:
                self._remote_panel = self.api.register_remote_panel(
                    "日志监视", [], self._remote_refresh, kind="text"
                )
            self.api.show_remote_panel(self._remote_panel)
            return
        if not self._panel:
            self._panel = LogTailPanel(self.api._host_window())
            # 修复: 使用 Qt 枚举而非裸 int
            self.api._host_window().addDockWidget(Qt.BottomDockWidgetArea, self._panel)
        self._panel.show()
        self._panel.raise_()

    def watch_file_dialog(self):
        filepath, _ok = self.api.open_file_dialog("选择日志文件", "")
        if filepath:
            self._watching = True
            self.show_panel()
            self._panel.watch(filepath)
            self.api.show_status("监视: %s" % os.path.basename(filepath), 2000)

    def watch_current(self):
        """监视当前文件"""
        if getattr(self.api, "is_isolated", False):
            self._watching = True
            self.show_panel()
            self.api.show_status("监视: 当前文件（隔离模式）", 2000, "success")
            return
        filepath = self.api.get_current_filepath()
        if not filepath:
            self.api.show_status("没有打开的文件", 2000)
            return

        self.show_panel()
        self._panel.watch(filepath)
        self.api.show_status(f"监视: {os.path.basename(filepath)}", 2000, "success")

    def stop_watching(self):
        """停止监视"""
        if getattr(self.api, "is_isolated", False):
            self._watching = False
            self.api.show_status("已停止监视", 2000)
            return
        if self._panel:
            self._panel.watch(None)
            self.api.show_status("已停止监视", 2000)
