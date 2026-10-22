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

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QLabel, QMessageBox, QSizePolicy, QStatusBar, QWidget


# 从 main_window.py 复制的常量
STATUS_REFRESH_INTERVAL = 3000
MEMORY_WARN_THRESHOLD = 800


class _ClickableLabel(QLabel):
    """可点击的 QLabel（NPP 状态栏交互等价：点击 Ln/Col 跳转）"""

    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.LeftButton:
                self.clicked.emit()
        except Exception:
            pass
        super().mousePressEvent(event)


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
        self.cursor_label = _ClickableLabel("行 1, 列 1")
        self.cursor_label.setToolTip("点击跳转到行（NPP 同款：点击 Ln/Col）")
        self.cursor_label.setCursor(Qt.PointingHandCursor)
        self.cursor_label.clicked.connect(self._on_cursor_label_clicked)
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
        self.encoding_label.setToolTip("当前文件编码")
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
        self.eol_label.setToolTip("换行符格式（LF/CRLF/CR）")
        self.status_bar.addWidget(self.eol_label)

        # 插入/改写模式
        self.mode_label = QLabel("插入")
        self.mode_label.setToolTip("插入/覆盖模式")
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


    def _on_cursor_label_clicked(self):
        """点击"行/列"：跳转到行（NPP 状态栏惯例）"""
        try:
            proxy = self.tabs.current_proxy()
            editor = getattr(proxy, 'sc', None) if proxy else None
            fn = getattr(editor, '_trigger_goto_line', None)
            if callable(fn):
                fn()
                return
            self.status_bar.showMessage("当前没有可跳转的编辑器", 2500)
        except Exception as e:
            self.status_bar.showMessage("跳转失败: %s" % e, 3000)

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
        """状态栏切换编码

        修复（实测过的**静默数据损坏**）：
            状态栏这一项的语义是"**改解释**"（用另一种编码重新读同一份
            字节），而不是"转码"。原实现直接 `change_encoding(encoding)`，
            于是：

                UTF-8 文件「中文内容测试」→ 切 GBK 看一眼（显示乱码）
                → 顺手 Ctrl+S → **磁盘被改写**，原字节永久丢失
                  （读回变成 '�?文内容测�?'）

            不保存则无损，所以危险恰恰藏在"看一眼 + 保存"这个自然动作里。

        修复策略（fail-closed）：
            先判断新编码能否**无损解码**现有字节：
              * 能   → 正常切换（常见情形，无打扰）；
              * 不能 → 弹确认框，明确告知"保存会改写文件"，
                       用户取消则**不切换**。
        """
        try:
            proxy = self.tabs.current_proxy()
            if not (proxy and proxy.document):
                return
            doc = proxy.document

            lossy = False
            try:
                lossy = doc.would_lose_text(encoding)
            except Exception:
                lossy = False

            if lossy:
                reply = QMessageBox.warning(
                    self,
                    "切换编码会改变文件内容",
                    "用「%s」重新解释当前文件会产生乱码"
                    "（这份内容原本不是用该编码保存的）。\n\n"
                    "· 只是看看：选「是」后**不要保存**，"
                    "关闭文件即可恢复；\n"
                    "· 要让文件真正变成该编码：请用「另存为」"
                    "并指定编码，避免原地损坏。\n\n"
                    "是否仍然切换？" % encoding,
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    self._update_status_for_editor()
                    self.status_bar.showMessage(
                        f"已取消切换编码（会损坏内容）: {encoding}", 4000
                    )
                    return

            doc.change_encoding(encoding)
            self._update_status_for_editor()
            if lossy:
                self.status_bar.showMessage(
                    f"编码已改为按 {encoding} 解释（⚠ 保存会改写文件）",
                    8000,
                )
            else:
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
