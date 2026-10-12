# -*- coding: utf-8 -*-
"""代码度量面板"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.code_metrics import analyze_directory, analyze_file


class CodeMetricsDialog(QDialog):
    """代码度量对话框"""

    def __init__(self, filepath="", root_path="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("代码度量")
        self.resize(800, 600)

        self.filepath = filepath
        self.root_path = root_path

        self._build_ui()
        self._apply_style()
        self._analyze()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 标签页
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # 单文件页
        self.file_tab = QWidget()
        self._build_file_tab()
        self.tabs.addTab(self.file_tab, "当前文件")

        # 项目页
        self.project_tab = QWidget()
        self._build_project_tab()
        self.tabs.addTab(self.project_tab, "整个项目")

        # 底部
        bottom = QHBoxLayout()
        bottom.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)

        layout.addLayout(bottom)

    def _build_file_tab(self):
        layout = QVBoxLayout(self.file_tab)

        self.file_info = QTextBrowser()
        self.file_info.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; "
            "border: none; padding: 8px;"
        )
        layout.addWidget(self.file_info)

        # 函数列表
        layout.addWidget(QLabel("函数列表:"))
        self.func_table = QTableWidget()
        self.func_table.setColumnCount(4)
        self.func_table.setHorizontalHeaderLabels(
            ["函数名", "行号", "长度", "参数数"]
        )
        self.func_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.func_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.func_table)

    def _build_project_tab(self):
        layout = QVBoxLayout(self.project_tab)

        self.project_info = QTextBrowser()
        self.project_info.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; "
            "border: none; padding: 8px;"
        )
        layout.addWidget(self.project_info, 1)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; }
            QTabWidget::pane {
                border: 1px solid #3c3c3c;
                background-color: #252526;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #d4d4d4;
                padding: 6px 14px;
                border: none;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: #7ec850;
            }
            QTableWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                gridline-color: #3c3c3c;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #d4d4d4;
                border: none;
                padding: 4px;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #1177bb; }
        """)

    def _analyze(self):
        """执行分析"""
        # 单文件
        if self.filepath:
            m = analyze_file(self.filepath)
            if 'error' in m:
                self.file_info.setPlainText("分析失败: " + m['error'])
            else:
                html = self._format_file_metrics(m)
                self.file_info.setHtml(html)

                # 函数表
                details = m.get('functions_detail', [])
                self.func_table.setRowCount(len(details))
                for i, f in enumerate(details):
                    self.func_table.setItem(
                        i, 0, QTableWidgetItem(f['name'])
                    )
                    self.func_table.setItem(
                        i, 1, QTableWidgetItem(str(f['line']))
                    )
                    length_item = QTableWidgetItem(str(f['length']))
                    if f['length'] > 50:
                        length_item.setForeground(QColor("#f0ad4e"))
                    self.func_table.setItem(i, 2, length_item)
                    self.func_table.setItem(
                        i, 3, QTableWidgetItem(str(f['args']))
                    )

        # 项目
        if self.root_path:
            import os
            result = analyze_directory(self.root_path)
            self.project_info.setHtml(
                self._format_project_metrics(result)
            )

    def _format_file_metrics(self, m):
        """格式化单文件度量"""
        html = "<h2>文件度量</h2>"
        html += "<table style='color:#d4d4d4; font-size:13px;'>"
        items = [
            ("文件", m.get('filepath', '')),
            ("语言", m.get('language', '')),
            ("大小", "%.1f KB" % (m.get('size', 0) / 1024)),
            ("总行数", m.get('total_lines', 0)),
            ("代码行", "<span style='color:#7ec850;'>%d</span>"
                     % m.get('code_lines', 0)),
            ("注释行", "<span style='color:#4dabf7;'>%d</span>"
                     % m.get('comment_lines', 0)),
            ("空行", "<span style='color:#888;'>%d</span>"
                   % m.get('blank_lines', 0)),
        ]

        if 'classes' in m:
            items.extend([
                ("类数量", m.get('classes', 0)),
                ("函数数量", m.get('functions', 0)),
                ("方法数量", m.get('methods', 0)),
                ("导入数量", m.get('imports', 0)),
                ("圈复杂度", "<span style='color:#f0ad4e;'>%d</span>"
                          % m.get('complexity', 0)),
            ])
            longest = m.get('longest_function', (0, ''))
            if longest[0] > 0:
                items.append(
                    ("最长函数", "%s (%d 行)" % (longest[1], longest[0]))
                )

        for k, v in items:
            html += "<tr><td style='padding:4px 12px 4px 0; color:#888;'>%s</td>" % k
            html += "<td style='padding:4px 0;'>%s</td></tr>" % str(v)
        html += "</table>"

        return html

    def _format_project_metrics(self, result):
        """格式化项目度量"""
        t = result['totals']
        html = "<h2>项目度量</h2>"

        if t['files'] == 0:
            return html + "<p>未发现代码文件</p>"

        html += "<table style='color:#d4d4d4; font-size:13px;'>"
        items = [
            ("文件数", t['files']),
            ("总大小", "%.1f MB" % (t['size'] / 1024 / 1024)),
            ("总行数", "<b>%d</b>" % t['total_lines']),
            ("代码行", "<span style='color:#7ec850;'>%d</span>"
                     % t['code_lines']),
            ("注释行", "<span style='color:#4dabf7;'>%d</span>"
                     % t['comment_lines']),
            ("空行", "<span style='color:#888;'>%d</span>"
                   % t['blank_lines']),
        ]

        # 注释率
        if t['total_lines'] > 0:
            comment_ratio = t['comment_lines'] / t['total_lines'] * 100
            items.append(
                ("注释率", "%.1f%%" % comment_ratio)
            )

        for k, v in items:
            html += "<tr><td style='padding:4px 12px 4px 0; color:#888;'>%s</td>" % k
            html += "<td style='padding:4px 0;'>%s</td></tr>" % str(v)
        html += "</table>"

        # Top 10 大文件
        files = sorted(result['files'],
                       key=lambda f: f.get('total_lines', 0),
                       reverse=True)[:10]

        html += "<h3>Top 10 最大文件</h3>"
        html += "<table style='color:#d4d4d4; font-size:12px;'>"
        html += "<tr style='color:#7ec850;'><th>文件</th><th>行数</th><th>代码行</th></tr>"

        import os
        for f in files:
            html += "<tr>"
            html += "<td style='padding:2px 8px;'>%s</td>" % os.path.basename(
                f.get('filepath', '')
            )
            html += "<td style='padding:2px 8px; text-align:right;'>%d</td>" % f.get('total_lines', 0)
            html += "<td style='padding:2px 8px; text-align:right;'>%d</td>" % f.get('code_lines', 0)
            html += "</tr>"
        html += "</table>"

        return html