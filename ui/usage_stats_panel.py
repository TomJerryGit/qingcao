# -*- coding: utf-8 -*-
"""使用数据分析面板"""
import os
import json
import time
import datetime
from collections import Counter, defaultdict
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QTextBrowser
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


class UsageStatsDialog(QDialog):
    """使用数据分析"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("使用数据分析")
        self.resize(800, 600)

        self.stats = self._load_stats()

        self._build_ui()
        self._apply_style()
        self._populate()

    def _load_stats(self):
        """加载统计数据。

        P2-C2: 复用 core.usage_stats

        原实现自己读 telemetry / session / local_completer，
        字段名和口径与 core.usage_stats 不一致，两处显示可能
        不同。统一走 core.usage_stats.get_snapshot()。
        """
        empty = {
            'basic': {}, 'file_types': {},
            'hourly': {}, 'daily': {}, 'features': {},
        }

        try:
            from core.usage_stats import get_usage_stats
            snap = get_usage_stats().get_snapshot(force=True)

            return {
                'basic': {
                    'first_run': snap.first_run,
                    'last_run': snap.last_run,
                    'run_count': snap.run_count,
                    'files_opened': snap.files_opened,
                    'files_saved': snap.files_saved,
                    'searches_run': snap.searches_run,
                    'plugins_loaded': snap.plugins_loaded,
                    'features_used': snap.features_used,
                },
                'file_types': dict(snap.files_by_ext),
                'hourly': dict(snap.hourly_activity),
                'daily': dict(snap.daily_activity),
                'features': {
                    '最近使用的词数': snap.recent_words_count,
                    '词频库大小': snap.word_freq_size,
                },
            }
        except ImportError as e:
            print(f"[UsageStatsDialog] core.usage_stats 不可用: {e}")
            return empty
        except Exception as e:
            print(f"[UsageStatsDialog] 加载统计失败: {e}")
            return empty

    def _build_ui(self):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        # 概览
        overview = QWidget()
        ov_layout = QVBoxLayout(overview)
        self.overview_view = QTextBrowser()
        ov_layout.addWidget(self.overview_view)
        tabs.addTab(overview, "概览")

        # 文件类型
        types = QWidget()
        t_layout = QVBoxLayout(types)
        self.types_table = QTableWidget()
        self.types_table.setColumnCount(3)
        self.types_table.setHorizontalHeaderLabels(
            ["扩展名", "数量", "占比"]
        )
        self.types_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.types_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        t_layout.addWidget(self.types_table)
        tabs.addTab(types, "文件类型")

        # 功能使用
        features = QWidget()
        f_layout = QVBoxLayout(features)
        self.features_table = QTableWidget()
        self.features_table.setColumnCount(2)
        self.features_table.setHorizontalHeaderLabels(
            ["指标", "数值"]
        )
        self.features_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.features_table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        f_layout.addWidget(self.features_table)
        tabs.addTab(features, "功能使用")

        layout.addWidget(tabs)

        # 底部
        bottom = QHBoxLayout()
        bottom.addStretch()

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self._on_refresh)
        bottom.addWidget(refresh_btn)

        clear_btn = QPushButton("🗑 清空数据")
        clear_btn.clicked.connect(self._on_clear)
        bottom.addWidget(clear_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)

        layout.addLayout(bottom)

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
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: #7ec850;
            }
            QTextBrowser, QTableWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:selected {
                background-color: #094771;
            }
            QHeaderView::section {
                background-color: #2d2d2d;
                color: #d4d4d4;
                border: none;
                padding: 6px;
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

    def _populate(self):
        """填充数据"""
        basic = self.stats.get('basic', {})

        # 概览
        html = "<h2>使用概览</h2><table style='font-size:13px;'>"
        items = [
            ("首次使用", self._format_time(basic.get('first_run', 0))),
            ("最近使用", self._format_time(basic.get('last_run', 0))),
            ("启动次数", basic.get('run_count', 0)),
            ("打开文件", basic.get('files_opened', 0)),
            ("保存文件", basic.get('files_saved', 0)),
            ("执行搜索", basic.get('searches_run', 0)),
            ("加载插件", basic.get('plugins_loaded', 0)),
            ("使用功能", len(basic.get('features_used', []))),
        ]
        for k, v in items:
            html += (
                "<tr><td style='padding:4px 12px 4px 0; "
                "color:#888;'>%s</td>"
                "<td style='padding:4px 0; color:#7ec850;'>%s</td></tr>"
                % (k, v)
            )
        html += "</table>"
        self.overview_view.setHtml(html)

        # 文件类型
        file_types = self.stats.get('file_types', {})
        total = sum(file_types.values()) or 1

        self.types_table.setRowCount(len(file_types))
        for i, (ext, count) in enumerate(
            sorted(file_types.items(), key=lambda x: -x[1])
        ):
            self.types_table.setItem(i, 0, QTableWidgetItem(ext))
            self.types_table.setItem(i, 1, QTableWidgetItem(str(count)))
            pct = count / total * 100
            item = QTableWidgetItem("%.1f%%" % pct)
            if pct > 50:
                item.setForeground(QColor("#7ec850"))
            self.types_table.setItem(i, 2, item)

        # 功能
        features = self.stats.get('features', {})
        self.features_table.setRowCount(len(features))
        for i, (k, v) in enumerate(features.items()):
            self.features_table.setItem(i, 0, QTableWidgetItem(k))
            self.features_table.setItem(i, 1, QTableWidgetItem(str(v)))

    def _format_time(self, ts):
        """格式化时间戳"""
        if not ts:
            return "从未"
        try:
            dt = datetime.datetime.fromtimestamp(ts)
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "?"

    def _on_refresh(self):
        self.stats = self._load_stats()
        self._populate()

    def _on_clear(self):
        from PyQt5.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "确认", "清空所有统计数据？"
        )
        if reply != QMessageBox.Yes:
            return

        try:
            from core.telemetry import get_telemetry
            get_telemetry().clear()
        except Exception:
            pass

        # 清空词频
        try:
            from core.local_completer import get_local_completer
            completer = get_local_completer()
            if completer:
                completer.word_freq.clear()
                completer.file_words.clear()
                completer.recent_words.clear()
        except Exception:
            pass

        self._populate()