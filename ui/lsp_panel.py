# -*- coding: utf-8 -*-
"""
青草编辑器 - LSP 状态面板
============================
- 显示所有 LSP 服务器状态
- 显示当前文件 LSP 客户端状态
- 一键安装
- 一键重启

作者: hedongwei
"""
import os

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDockWidget,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.lsp_installer import get_lsp_installer


class LspPanel(QDockWidget):
    """LSP 状态面板"""

    def __init__(self, main_window=None, parent=None):
        super().__init__("语言服务器", parent or main_window)
        self.main_window = main_window
        self.setObjectName("LspPanel")
        self.setAllowedAreas(
            Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea
        )

        self.installer = get_lsp_installer()

        self._build_ui()
        self._apply_style()

        # 定时刷新
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5000)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start()

        QTimer.singleShot(100, self.refresh)

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 工具栏
        toolbar = QHBoxLayout()

        refresh_btn = QPushButton("🔄")
        refresh_btn.setFixedWidth(32)
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(refresh_btn)

        toolbar.addStretch()

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(
            "color: #888; font-size: 11px;"
        )
        toolbar.addWidget(self.status_label)

        layout.addLayout(toolbar)

        # 服务器树
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["", "语言", "状态", "版本"])
        self.tree.setColumnWidth(0, 30)
        self.tree.setColumnWidth(1, 100)
        self.tree.setColumnWidth(2, 80)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.tree)

        # 当前文件 LSP
        layout.addWidget(QLabel("当前文件:"))
        self.current_label = QLabel("")
        self.current_label.setStyleSheet(
            "background-color: #2d2d2d; color: #d4d4d4; "
            "padding: 6px; border-radius: 3px;"
        )
        layout.addWidget(self.current_label)

        self.setWidget(container)

    def refresh_theme(self, theme):
        """主题变更时刷新样式（v3.0）"""
        try:
            from infrastructure.theme_loader import adapt_qss_colors
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
                border-bottom: 1px solid #3c3c3c;
            }
            QTreeWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                font-size: 12px;
            }
            QTreeWidget::item {
                padding: 4px;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
            }
            QHeaderView::section {
                background-color: #252526;
                color: #888;
                border: none;
                padding: 4px;
                font-size: 11px;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)

    def refresh(self):
        """刷新状态"""
        self.tree.clear()

        # 获取所有语言
        languages = self.installer.list_languages()

        active_count = 0
        for lang in languages:
            info = self.installer.get_server_info(lang)

            item = QTreeWidgetItem(self.tree)
            item.setText(0, "✓" if info['installed'] else "✗")
            item.setForeground(0, QColor(
                "#7ec850" if info['installed'] else "#f14c4c"
            ))

            item.setText(1, lang)
            item.setText(2, "已安装" if info['installed'] else "未安装")
            item.setText(3, info['version'] or "-")

            item.setData(0, Qt.UserRole, info)
            item.setData(0, Qt.UserRole + 1, lang)

            if info['installed']:
                active_count += 1

        self.status_label.setText(
            f"{active_count}/{len(languages)} 已安装"
        )

        # 当前文件
        self._update_current()

    def _update_current(self):
        """更新当前文件状态"""
        if not self.main_window:
            self.current_label.setText("(未连接)")
            return

        try:
            proxy = self.main_window.tabs.current_proxy()
            if not proxy or not proxy.document:
                self.current_label.setText("(无活动文件)")
                return

            filepath = proxy.document.filepath or ""
            if not filepath:
                self.current_label.setText("(未保存)")
                return

            # 检测语言
            ext = os.path.splitext(filepath)[1].lower()
            lang = None
            for l, config in self._get_language_map().items():
                if ext in config:
                    lang = l
                    break

            if lang:
                installed = self.installer.is_installed(lang)
                # P6: 区分"装了服务器"与"当前文件真的连上了 LSP"
                active = bool(getattr(proxy, 'lsp_active', False))
                if active:
                    status = "已连接"
                    color = "#7ec850"
                elif installed:
                    status = "已安装（未启用）"
                    color = "#4ec9b0"
                else:
                    status = "未安装"
                    color = "#f0ad4e"
                self.current_label.setText(
                    f'<span style="color:{color};">'
                    f'{os.path.basename(filepath)} · {lang} · {status}'
                    f'</span>'
                )
            else:
                self.current_label.setText(
                    f"{os.path.basename(filepath)} · (无 LSP)"
                )
        except Exception as e:
            self.current_label.setText(f"(错误: {e})")

    def _get_language_map(self):
        """获取语言-扩展名映射"""
        result = {}
        for lang in self.installer.list_languages():
            info = self.installer.get_server_info(lang)
            result[lang] = info['extensions']
        return result

    def _on_item_double_clicked(self, item, column):
        """双击"""
        lang = item.data(0, Qt.UserRole + 1)
        info = item.data(0, Qt.UserRole)
        if not lang or not info:
            return

        if info['installed']:
            # 已安装：询问是否重装/更新
            reply = QMessageBox.question(
                self, "LSP 已安装",
                f"{info['name']} 已安装。\n\n"
                f"版本: {info['version']}\n\n"
                f"是否重新安装/更新？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self._install(lang)
        else:
            # 未安装：询问安装
            reply = QMessageBox.question(
                self, "安装 LSP",
                f"{info['name']} 未安装。\n\n"
                f"是否自动安装？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self._install(lang)

    def _install(self, language):
        """安装"""
        info = self.installer.get_server_info(language)

        # 检查是否有安装方法
        if not info['install_method']:
            QMessageBox.information(
                self, "手动安装",
                self.installer.get_manual_install_hint(language)
            )
            return

        # 创建进度对话框
        progress = QProgressDialog(
            f"正在安装 {info['name']}...", "取消",
            0, 0, self
        )
        progress.setWindowTitle("安装语言服务器")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        # 连接信号
        def on_started(lang):
            progress.setLabelText(f"正在安装 {info['name']}...")

        def on_progress(lang, msg):
            progress.setLabelText(msg)

        def on_finished(lang, success, msg):
            progress.close()
            if success:
                QMessageBox.information(
                    self, "安装成功",
                    f"{info['name']} 安装成功！\n\n"
                    f"重启编辑器后生效。"
                )
            else:
                QMessageBox.critical(
                    self, "安装失败", msg
                )
            self.refresh()

        # 修复说明（P2-4）: 原实现 disconnect() 不带参数会断开
        # 所有订阅者。现改为一次性连接，成功/失败后自动清理。
        def _one_shot_finished(lang, success, msg):
            for signal, slot in (
                (self.installer.install_started, on_started),
                (self.installer.install_progress, on_progress),
                (self.installer.install_finished, _one_shot_finished),
            ):
                try:
                    signal.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
            on_finished(lang, success, msg)

        self.installer.install_started.connect(on_started)
        self.installer.install_progress.connect(on_progress)
        self.installer.install_finished.connect(_one_shot_finished)

        self.installer.install_async(language)


class LspInstallerDialog(QDialog):
    """LSP 安装器对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("语言服务器管理")
        self.resize(700, 500)

        self.installer = get_lsp_installer()

        self._build_ui()
        self._apply_style()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "青草编辑器通过 LSP 为各种语言提供智能提示。\n"
            "双击行安装或更新。"
        ))

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "状态", "语言", "服务器", "版本", "操作"
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeToContents
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)

        # 底部按钮
        btn_layout = QHBoxLayout()

        install_all_btn = QPushButton("⬇ 全部安装")
        install_all_btn.clicked.connect(self._install_all)
        btn_layout.addWidget(install_all_btn)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self.refresh)
        btn_layout.addWidget(refresh_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #d4d4d4; }
            QLabel { color: #d4d4d4; }
            QTableWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                gridline-color: #3c3c3c;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QTableWidget::item:selected {
                background-color: #094771;
            }
            QHeaderView::section {
                background-color: #252526;
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
            QPushButton:hover {
                background-color: #1177bb;
            }
        """)

    def refresh(self):
        """刷新表格"""
        languages = self.installer.list_languages()
        self.table.setRowCount(len(languages))

        for i, lang in enumerate(languages):
            info = self.installer.get_server_info(lang)

            # 状态
            status_item = QTableWidgetItem(
                "✓" if info['installed'] else "✗"
            )
            status_item.setForeground(QColor(
                "#7ec850" if info['installed'] else "#f14c4c"
            ))
            self.table.setItem(i, 0, status_item)

            self.table.setItem(i, 1, QTableWidgetItem(lang))
            self.table.setItem(i, 2, QTableWidgetItem(info['name']))
            self.table.setItem(
                i, 3,
                QTableWidgetItem(info['version'] or "-")
            )

            # 操作按钮
            btn = QPushButton(
                "更新" if info['installed'] else "安装"
            )
            btn.setProperty("lang", lang)
            btn.clicked.connect(
                lambda checked=False, l=lang: self._install(l)
            )
            self.table.setCellWidget(i, 4, btn)

    def _install(self, language):
        """安装"""
        info = self.installer.get_server_info(language)

        if not info['install_method']:
            QMessageBox.information(
                self, "手动安装",
                self.installer.get_manual_install_hint(language)
            )
            return

        progress = QProgressDialog(
            f"正在安装 {info['name']}...", "取消",
            0, 0, self
        )
        progress.setWindowTitle("安装")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        def on_finished(lang, success, msg):
            progress.close()
            if success:
                QMessageBox.information(
                    self, "成功",
                    f"{info['name']} 安装成功！"
                )
            else:
                QMessageBox.critical(self, "失败", msg)
            self.refresh()

        try:
            self.installer.install_finished.disconnect()
        except Exception:
            pass

        self.installer.install_finished.connect(on_finished)
        self.installer.install_async(language)

    def _install_all(self):
        """全部安装"""
        languages = [
            l for l in self.installer.list_languages()
            if not self.installer.is_installed(l)
            and self.installer.get_server_info(l)['install_method']
        ]

        if not languages:
            QMessageBox.information(
                self, "提示", "没有需要安装的 LSP 服务器"
            )
            return

        reply = QMessageBox.question(
            self, "批量安装",
            f"将安装以下 {len(languages)} 个服务器:\n\n"
            + "\n".join(f"  • {l}" for l in languages)
            + "\n\n是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if reply != QMessageBox.Yes:
            return

        # 依次安装（简化，实际应串行）
        for lang in languages:
            self._install(lang)
            # 简单等待
            QApplication.processEvents()