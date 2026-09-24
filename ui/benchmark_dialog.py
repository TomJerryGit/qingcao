# -*- coding: utf-8 -*-
"""基准测试对话框"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QPushButton, QLabel, QProgressBar, QApplication
)
from PyQt5.QtGui import QFont

from core.benchmark import Benchmark


class BenchmarkDialog(QDialog):
    """基准测试对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("性能基准测试")
        self.resize(700, 500)

        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "点击\"开始测试\"运行所有基准项目。\n"
            "测试期间界面可能短暂无响应，请稍候。"
        ))

        self.progress = QProgressBar()
        self.progress.setRange(0, 5)
        layout.addWidget(self.progress)

        self.result_view = QPlainTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setFont(QFont("Consolas", 10))
        layout.addWidget(self.result_view, 1)

        # 按钮
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("▶ 开始测试")
        self.start_btn.clicked.connect(self._on_start)
        btn_layout.addWidget(self.start_btn)

        copy_btn = QPushButton("📋 复制报告")
        copy_btn.clicked.connect(self._on_copy)
        btn_layout.addWidget(copy_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; }
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
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #1177bb; }
            QProgressBar {
                background-color: #2d2d2d;
                border: 1px solid #3c3c3c;
                border-radius: 3px;
                height: 20px;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #0e639c;
                border-radius: 3px;
            }
        """)

    def _on_start(self):
        self.start_btn.setEnabled(False)
        self.result_view.clear()
        self.progress.setValue(0)

        bench = Benchmark()

        # 异步执行避免界面卡死
        import threading
        def worker():
            try:
                results = {}
                tests = [
                    ('open_file', bench._bench_open_file),
                    ('search', bench._bench_search),
                    ('commands', bench._bench_commands),
                    ('undo_redo', bench._bench_undo_redo),
                    ('event_bus', bench._bench_event_bus),
                ]

                for i, (name, fn) in enumerate(tests):
                    results[name] = fn()
                    bench.results = results
                    # 更新 UI（通过 signal 或 processEvents）
                    QApplication.processEvents()

                bench.results = results

                # 显示结果
                self._show_result(bench.get_report())
            except Exception as e:
                self._show_result("测试失败: " + str(e))
            finally:
                self.start_btn.setEnabled(True)

        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self, text):
        self.result_view.setPlainText(text)
        self.progress.setValue(5)

    def _on_copy(self):
        QApplication.clipboard().setText(
            self.result_view.toPlainText()
        )