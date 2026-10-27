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

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)

        # 工具栏
        toolbar = QHBoxLayout()

        self.file_label = QLabel("(未选择)")
        self.file_label.setStyleSheet("color: #888;")
        toolbar.addWidget(self.file_label, 1)

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
        self.setStyleSheet("""
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
        """)

    def watch(self, filepath):
        """监视文件；filepath=None 表示停止监视"""
        # 停止监视（修复：原实现直接 basename(None) 会崩）
        if not filepath:
            if (self.current_file and
                    self.current_file in self.watcher.files()):
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
        self.file_label.setText(os.path.basename(filepath))

        if filepath and os.path.exists(filepath):
            self.watcher.addPath(filepath)
            self.last_size = 0
            self.view.clear()
            # 读取全部
            self._read_all()

    def _read_all(self):
        """读取全部内容"""
        if not self.current_file or not os.path.exists(self.current_file):
            return
        try:
            with open(self.current_file,
                      encoding='utf-8', errors='replace') as f:
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

            with open(self.current_file,
                      encoding='utf-8', errors='replace') as f:
                f.seek(self.last_size)
                new_content = f.read()
                self.last_size = size

            if new_content:
                self.view.appendPlainText(
                    new_content.rstrip('\n')
                )
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

        self.api.add_menu(
            "工具/日志监视/监视当前文件",
            self.watch_current,
            shortcut="Ctrl+Alt+L"
        )
        self.api.add_menu(
            "工具/日志监视/停止监视",
            self.stop_watching
        )
        self.api.add_menu(
            "工具/日志监视/打开面板",
            self.show_panel
        )
        # v2.4 扩展点
        self.on_activate_extension_points()

    def on_activate_extension_points(self):
        """v2.4 扩展点（由 on_activate 末尾调用）"""
        self.api.register_settings_schema([
            {"key": "max_lines", "label": "面板最多保留行数",
             "type": "int", "default": 5000, "min": 100, "max": 200000},
        ])
        self._status = self.api.add_status_item("监视: 未启动")

    def on_deactivate(self):
        if self._panel:
            self._panel.close()

    def show_panel(self):
        """显示面板"""
        if not self._panel:
            self._panel = LogTailPanel(self.api._host_window())
            # 修复: 使用 Qt 枚举而非裸 int
            self.api._host_window().addDockWidget(
                Qt.BottomDockWidgetArea, self._panel
            )
        self._panel.show()
        self._panel.raise_()

    def watch_current(self):
        """监视当前文件"""
        filepath = self.api.get_current_filepath()
        if not filepath:
            self.api.show_status("没有打开的文件", 2000)
            return

        self.show_panel()
        self._panel.watch(filepath)
        self.api.show_status(
            f"监视: {os.path.basename(filepath)}", 2000, "success"
        )

    def stop_watching(self):
        """停止监视"""
        if self._panel:
            self._panel.watch(None)
            self.api.show_status("已停止监视", 2000)