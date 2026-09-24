# -*- coding: utf-8 -*-
"""
青草编辑器 - 状态栏 Mixin
============================
从 ui/main_window.py 拆分出来的状态栏功能。

包含:
    - _build_status_bar     构建状态栏
    - _update_status_for_editor  更新状态栏（当前文件信息）
    - _refresh_status       定时刷新
    - _update_memory        内存占用显示
    - _update_git_branch    Git 分支显示
    - _on_encoding_changed  编码切换回调
    - _on_eol_changed       行尾符切换回调
    - _on_git_branch_clicked  Git 分支点击回调
"""

import os
import subprocess

from PyQt5.QtWidgets import (
    QStatusBar, QLabel, QWidget, QSizePolicy, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer


# 从 main_window.py 复制的常量
STATUS_REFRESH_INTERVAL = 3000
MEMORY_WARN_THRESHOLD = 800


class StatusBarMixin:
    """状态栏 Mixin —— 由 MainWindow 继承"""

    # 属性（由 MainWindow.__init__ 创建）:
    #   self._status_timer
    #   self.status_bar, self.cursor_label, self.encoding_label,
    #   self.eol_label, self.mode_label, self.selection_label,
    #   self.lsp_status_label, self.git_branch_label,
    #   self.rec_label, self.mem_label

    # ========================================================
    # 状态栏
    # ========================================================
    def _build_status_bar(self):
        """构建状态栏"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # 光标位置
        self.cursor_label = QLabel("行 1, 列 1")
        self.cursor_label.setMinimumWidth(120)
        self.status_bar.addWidget(self.cursor_label)

        # 编码（可点击切换）
        try:
            from ui.status_bar_widgets import EncodingLabel
            self.encoding_label = EncodingLabel(self)
            self.encoding_label.setMinimumWidth(80)
            self.encoding_label.encoding_changed.connect(
                self._on_encoding_changed
            )
        except ImportError:
            self.encoding_label = QLabel("UTF-8")
            self.encoding_label.setMinimumWidth(80)
        self.status_bar.addWidget(self.encoding_label)

        # 行尾符（可点击切换）
        try:
            from ui.status_bar_widgets import EolLabel
            self.eol_label = EolLabel(self)
            self.eol_label.setMinimumWidth(40)
            self.eol_label.eol_changed.connect(self._on_eol_changed)
        except ImportError:
            self.eol_label = QLabel("LF")
            self.eol_label.setMinimumWidth(40)
        self.status_bar.addWidget(self.eol_label)

        # 插入/改写模式
        self.mode_label = QLabel("插入")
        self.mode_label.setMinimumWidth(50)
        self.status_bar.addWidget(self.mode_label)

        # 选区信息
        self.selection_label = QLabel("")
        self.selection_label.setMinimumWidth(150)
        self.status_bar.addWidget(self.selection_label)

        # 弹性空间
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.status_bar.addWidget(spacer)

        # LSP 状态
        self.lsp_status_label = QLabel("●")
        self.lsp_status_label.setStyleSheet("color: gray; font-size: 14px;")
        self.lsp_status_label.setToolTip("LSP 未启用")
        self.lsp_status_label.setMinimumWidth(20)
        self.status_bar.addPermanentWidget(self.lsp_status_label)

        # Git 分支（可点击）
        try:
            from ui.status_bar_widgets import GitBranchLabel
            self.git_branch_label = GitBranchLabel(self)
            self.git_branch_label.setMinimumWidth(100)
            self.git_branch_label.git_clicked.connect(
                self._on_git_branch_clicked
            )
        except ImportError:
            self.git_branch_label = QLabel("")
            self.git_branch_label.setMinimumWidth(100)
        self.status_bar.addPermanentWidget(self.git_branch_label)

        # 宏录制
        self.rec_label = QLabel("")
        self.rec_label.setStyleSheet("color: #FF4444; font-weight: bold;")
        self.rec_label.hide()
        self.status_bar.addPermanentWidget(self.rec_label)

        # 内存占用
        self.mem_label = QLabel("内存: 0 MB")
        self.mem_label.setMinimumWidth(120)
        self.status_bar.addPermanentWidget(self.mem_label)

        # 初始消息
        self.status_bar.showMessage("就绪")


    def _update_status_for_editor(self):
        """更新状态栏为当前编辑器信息"""
        try:
            proxy = self.tabs.current_proxy()
            if not proxy:
                return

            # 编码（优先调用新组件的 set_encoding）
            try:
                enc = "utf-8"
                if proxy.document:
                    enc = proxy.document.encoding or "utf-8"
                if hasattr(self.encoding_label, 'set_encoding'):
                    self.encoding_label.set_encoding(enc)
                else:
                    self.encoding_label.setText(enc.upper())
            except Exception:
                pass

            # 行尾符（优先调用新组件的 set_eol）
            try:
                if proxy.document and hasattr(proxy.document, 'meta'):
                    eol = getattr(proxy.document.meta, 'eol', "\n")
                    if hasattr(self.eol_label, 'set_eol'):
                        self.eol_label.set_eol(eol)
                    else:
                        eol_display = {'\n': 'LF', '\r\n': 'CRLF',
                                        '\r': 'CR'}.get(eol, 'LF')
                        self.eol_label.setText(eol_display)
            except Exception:
                pass

            # 只读
            try:
                is_readonly = False
                if hasattr(proxy, 'is_readonly'):
                    is_readonly = proxy.is_readonly
                if is_readonly:
                    self.mode_label.setText("只读")
                    self.mode_label.setStyleSheet("color: #f0ad4e;")
                else:
                    self.mode_label.setText("插入")
                    self.mode_label.setStyleSheet("")
            except Exception:
                pass

        except Exception as e:
            print(f"[MainWindow] 更新状态栏失败: {e}")


    def _on_encoding_changed(self, encoding: str):
        """状态栏切换编码"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.document:
                proxy.document.change_encoding(encoding)
                self._update_status_for_editor()
                self.status_bar.showMessage(
                    f"编码已切换: {encoding}", 2000
                )
        except Exception as e:
            print(f"[MainWindow] 切换编码失败: {e}")


    def _on_eol_changed(self, eol: str):
        """状态栏切换行尾符"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy and proxy.document:
                if hasattr(proxy.document, 'set_eol'):
                    proxy.document.set_eol(eol)
                    self._update_status_for_editor()
                    display = {"\n": "LF", "\r\n": "CRLF",
                                "\r": "CR"}.get(eol, "LF")
                    self.status_bar.showMessage(
                        f"行尾符已切换: {display}", 2000
                    )
        except Exception as e:
            print(f"[MainWindow] 切换行尾符失败: {e}")


    def _on_git_branch_clicked(self):
        """状态栏点击 Git 分支"""
        try:
            # 优先尝试调用已加载的 git_deep 插件
            for plugin in getattr(self, 'plugins', []):
                if getattr(plugin, 'NAME', '') == 'git_deep':
                    if hasattr(plugin, 'show_status'):
                        plugin.show_status()
                        return
            # 回退：显示简单提示
            from PyQt5.QtWidgets import QMessageBox
            text = self.git_branch_label.text() or "(无)"
            QMessageBox.information(self, "Git 分支", text)
        except Exception as e:
            print(f"[MainWindow] Git 分支点击失败: {e}")


    def _refresh_status(self):
        """定时刷新状态栏"""
        self._update_memory()


    def _update_memory(self):
        """更新内存显示"""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem_mb = process.memory_info().rss / 1024 / 1024
            self.mem_label.setText(f"内存: {mem_mb:.1f} MB")

            if mem_mb > MEMORY_WARN_THRESHOLD:
                self.mem_label.setStyleSheet(
                    "color: #f14c4c; font-weight: bold;"
                )
            else:
                self.mem_label.setStyleSheet("")
        except ImportError:
            self.mem_label.setText("内存: 未安装 psutil")
        except Exception:
            pass


    def _update_git_branch(self):
        """更新 Git 分支"""
        try:
            proxy = self.tabs.current_proxy()
            if not proxy or not proxy.document:
                self.git_branch_label.setText("")
                return

            filepath = proxy.document.filepath
            if not filepath:
                self.git_branch_label.setText("")
                return

            dirpath = os.path.dirname(filepath)
            git_root = None
            check_path = dirpath
            while check_path != os.path.dirname(check_path):
                if os.path.isdir(os.path.join(check_path, '.git')):
                    git_root = check_path
                    break
                check_path = os.path.dirname(check_path)

            if not git_root:
                self.git_branch_label.setText("")
                return

            result = subprocess.run(
                ['git', '-C', git_root, 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True, text=True, timeout=2,
                encoding='utf-8', errors='replace'
            )

            if result.returncode == 0:
                branch = result.stdout.strip()
                self.git_branch_label.setText(f"🌿 {branch}")
            else:
                self.git_branch_label.setText("")

        except Exception:
            self.git_branch_label.setText("")
