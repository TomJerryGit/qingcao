# -*- coding: utf-8 -*-
"""性能监控面板"""
import os
import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDockWidget,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class PerfMonitor(QDockWidget):
    """性能监控面板"""

    def __init__(self, main_window=None, parent=None):
        super().__init__("性能监控", parent or main_window)
        self.main_window = main_window
        self.setObjectName("PerfMonitor")
        self.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.RightDockWidgetArea)

        self._build_ui()
        self._apply_style()

        # 定时刷新
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(2000)

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 内存/CPU
        sys_group = QGroupBox("系统资源")
        sys_layout = QGridLayout(sys_group)

        sys_layout.addWidget(QLabel("进程内存:"), 0, 0)
        self.mem_label = QLabel("-")
        self.mem_label.setStyleSheet("color: #7ec850; font-weight: bold;")
        sys_layout.addWidget(self.mem_label, 0, 1)

        sys_layout.addWidget(QLabel("CPU:"), 1, 0)
        self.cpu_label = QLabel("-")
        self.cpu_label.setStyleSheet("color: #7ec850; font-weight: bold;")
        sys_layout.addWidget(self.cpu_label, 1, 1)

        sys_layout.addWidget(QLabel("线程数:"), 2, 0)
        self.thread_label = QLabel("-")
        sys_layout.addWidget(self.thread_label, 2, 1)

        layout.addWidget(sys_group)

        # 编辑器状态
        editor_group = QGroupBox("编辑器")
        editor_layout = QGridLayout(editor_group)

        editor_layout.addWidget(QLabel("标签数:"), 0, 0)
        self.tab_label = QLabel("-")
        self.tab_label.setStyleSheet("color: #4dabf7; font-weight: bold;")
        editor_layout.addWidget(self.tab_label, 0, 1)

        editor_layout.addWidget(QLabel("总字符:"), 1, 0)
        self.chars_label = QLabel("-")
        editor_layout.addWidget(self.chars_label, 1, 1)

        editor_layout.addWidget(QLabel("撤销栈:"), 2, 0)
        self.undo_label = QLabel("-")
        editor_layout.addWidget(self.undo_label, 2, 1)

        layout.addWidget(editor_group)

        # 事件总线
        event_group = QGroupBox("事件总线")
        event_layout = QGridLayout(event_group)

        event_layout.addWidget(QLabel("总事件:"), 0, 0)
        self.event_count_label = QLabel("-")
        self.event_count_label.setStyleSheet("color: #ce9178; font-weight: bold;")
        event_layout.addWidget(self.event_count_label, 0, 1)

        event_layout.addWidget(QLabel("待处理:"), 1, 0)
        self.pending_label = QLabel("-")
        event_layout.addWidget(self.pending_label, 1, 1)

        layout.addWidget(event_group)

        # 操作按钮
        btn_layout = QHBoxLayout()

        gc_btn = QPushButton("♻ 强制 GC")
        gc_btn.clicked.connect(self._force_gc)
        btn_layout.addWidget(gc_btn)

        clear_btn = QPushButton("🗑 清空事件历史")
        clear_btn.clicked.connect(self._clear_events)
        btn_layout.addWidget(clear_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

        self.setWidget(container)


    def refresh_theme(self, theme):
        """主题变更时刷新样式（v3.0）"""
        try:
            from infrastructure.theme_loader import adapt_qss_colors
            # 保存原始 QSS（只保存一次）
            if not hasattr(self, '_original_qss') or not self._original_qss:
                self._original_qss = self.styleSheet()
            if self._original_qss:
                qss = adapt_qss_colors(self._original_qss, theme)
                self.setStyleSheet(qss)
        except Exception as e:
            print(f"[{self.__class__.__name__}] refresh_theme 失败: {e}")

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
            QGroupBox {
                color: #7ec850;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 8px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLabel {
                color: #d4d4d4;
                padding: 2px;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)

    @staticmethod
    def _count_chars(sc):
        """返回 (真实字符数, 字节数)

        缺陷背景（P0-8，已核实）:
            Scintilla 的 `length()` / `SCI_GETLENGTH` 返回的是文档的
            **UTF-8 字节数**，本面板却把它标成"总字符"。纯 ASCII 下两者
            相等，含中文时每个汉字 3 字节 → 数字差 3 倍。
            `sc.text()` 是 QScintilla 解码后的 str，`len()` 才是真实字符数。

        性能: `text()` 需要整篇解码；本面板每 2 秒刷新一次，大文件上
            重复解码代价明显。因此把结果按"字节长度"缓存在控件上：
            内容没变（字节长度相同）就直接复用，不做第二次解码。
        """
        nbytes = int(sc.length())

        cached = getattr(sc, '_qc_char_count_cache', None)
        if (isinstance(cached, tuple) and len(cached) == 2
                and cached[0] == nbytes):
            return int(cached[1]), nbytes

        chars = len(sc.text())
        try:
            # 私有缓存挂在控件上：控件销毁即回收，不会造成额外内存驻留
            sc._qc_char_count_cache = (nbytes, chars)
        except Exception:
            pass
        return chars, nbytes

    @staticmethod
    def _format_count(total: int) -> str:
        """把字符数格式化为可读文本（与修复前的显示习惯保持一致）"""
        if total > 1000000:
            return "%.1f M" % (total / 1000000)
        if total > 1000:
            return "%.1f K" % (total / 1000)
        return str(total)

    def _refresh(self):
        """刷新显示"""
        try:
            # 系统资源
            try:
                import psutil
                proc = psutil.Process(os.getpid())
                mem_mb = proc.memory_info().rss / 1024 / 1024
                self.mem_label.setText("%.1f MB" % mem_mb)

                cpu = proc.cpu_percent(interval=0.05)
                self.cpu_label.setText("%.1f%%" % cpu)

                self.thread_label.setText(str(proc.num_threads()))
            except ImportError:
                self.mem_label.setText("(未安装 psutil)")

            # 编辑器状态
            if self.main_window and hasattr(self.main_window, 'tabs'):
                tabs = self.main_window.tabs
                self.tab_label.setText(str(tabs.count()))

                # 总字符 / 总字节
                #
                # P0-8 修复：`sc.length()`（= SCI_GETLENGTH）返回的是
                # **字节数**，不是字符数 —— 纯 ASCII 下两者相同，所以这个
                # 错标一直没被发现；含中文时（UTF-8 每字 3 字节）
                # "总字符"会被高估约 3 倍。现在显示真实字符数，
                # 字节数放进 tooltip（两个口径都保留，便于判断内存压力）。
                total_chars = 0
                total_bytes = 0
                for i in range(tabs.count()):
                    w = tabs.widget(i)
                    if hasattr(w, 'proxy') and w.proxy and w.proxy.sc:
                        try:
                            chars, nbytes = self._count_chars(w.proxy.sc)
                            total_chars += chars
                            total_bytes += nbytes
                        except Exception:
                            pass
                self.chars_label.setText(self._format_count(total_chars))
                self.chars_label.setToolTip(
                    "字符 %d / 字节 %d" % (total_chars, total_bytes)
                )

                # 撤销栈
                proxy = tabs.current_proxy()
                if proxy and hasattr(proxy, 'undo_manager'):
                    try:
                        self.undo_label.setText(
                            str(len(proxy.undo_manager.undo_stack))
                        )
                    except Exception:
                        pass

            # 事件总线
            try:
                from app.event_bus import bus
                stats = bus.get_stats()
                self.event_count_label.setText(
                    str(stats.get('total_events', 0))
                )
                self.pending_label.setText(
                    str(stats.get('pending_count', 0))
                )
            except Exception:
                pass

        except Exception as e:
            print("[PerfMonitor] 刷新失败: %s" % e)

    def _force_gc(self):
        """强制垃圾回收"""
        import gc
        count = gc.collect()
        print("[PerfMonitor] GC 回收 %d 个对象" % count)
        self._refresh()

    def _clear_events(self):
        """清空事件历史"""
        try:
            from app.event_bus import bus
            bus.clear_history()
            self._refresh()
        except Exception:
            pass