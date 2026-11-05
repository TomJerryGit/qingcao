# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""MainWindow remote 职责（v2.23 D2 拆分）。"""

from ui.main_window_common import *  # noqa: F401,F403
from ui.main_window_common import _TopLevelThemeFilter  # noqa: F401


class WindowRemoteMixin:
    def apply_theme_to_widget(self, widget):
        """把一个控件（及其子控件）套用当前主题（若已确定）

        主题是否已知取决于 `apply_startup_theme()` 是否已执行 ——
        惰性面板/插件面板都可能在它之后创建，因此统一走这里。
        """
        theme = getattr(self, "_startup_theme", None)
        if theme is None or widget is None:
            return
        for target in [widget]:
            try:
                children = widget.findChildren(QWidget)
            except Exception:
                children = []
            for w in [target] + list(children):
                fn = getattr(w, "refresh_theme", None)
                if callable(fn):
                    try:
                        fn(theme)
                    except Exception:
                        pass
        # 子控件内联深色 QSS 也要适配（dock 级 refresh_theme 覆盖不到）
        try:
            adapt_widget_styles(widget, theme)
        except Exception:
            pass

    # ========================================================
    # 快捷键
    # ========================================================
    def _build_shortcuts(self):
        """绑定快捷键（QShortcut 在 PyQt5 中位于 QtWidgets）"""
        # 注意：以下快捷键中，与菜单 QAction 重复的已移除，
        #       避免 Qt 报 "Ambiguous shortcut overload"。
        #       QAction 的快捷键在 _build_menus 中定义。
        #
        # 这里只保留菜单里没有的快捷键。
        shortcuts = [
            ("Ctrl+Space", self._auto_complete),
            ("Ctrl+Tab", self._next_tab),
            ("Ctrl+Shift+Tab", self._prev_tab),
        ]

        self._shortcuts = []
        for shortcut, slot in shortcuts:
            try:
                sc = QShortcut(QKeySequence(shortcut), self)
                sc.activated.connect(slot)
                self._shortcuts.append(sc)
            except Exception as e:
                print(f"[MainWindow] 快捷键 {shortcut} 绑定失败: {e}")

    # ========================================================
    # 事件总线
    # ========================================================
    def _connect_event_bus(self):
        """连接事件总线"""
        try:
            from app.event_bus import bus

            bus.status_message.connect(self._on_status_message)
            bus.cursor_moved.connect(self._on_cursor_moved)
            bus.file_opened.connect(self._on_file_opened)
            bus.file_saved.connect(self._on_file_saved)
        except Exception as e:
            print(f"[MainWindow] 事件总线连接失败: {e}")

    def _open_language_packs_dir(self):
        """设置 → 打开语言包目录（data/language_packs）"""
        try:
            import os

            from PyQt5.QtCore import QUrl
            from PyQt5.QtGui import QDesktopServices

            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(root, "data", "language_packs")
            os.makedirs(path, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception as e:
            self.status_bar.showMessage("打开语言包目录失败: %s" % e, 3000)

    def _local_open_paths(self):
        paths = set()
        try:
            for i in range(self.tabs.count()):
                ed = self.tabs.widget(i)
                fp = getattr(getattr(ed, "document", None), "filepath", "") or ""
                if fp:
                    paths.add(fp)
        except Exception:
            pass
        return paths

    def _on_local_tab_opened(self, index):
        """打开文件：同一路径只广播一次（v2.12.0 重复事件抑制）"""
        try:
            ed = self.tabs.widget(index)
            fp = getattr(getattr(ed, "document", None), "filepath", "") or ""
            self._hook_sandbox_live_tab(index)
            if not fp:
                return
            known = set(getattr(self, "_known_open_paths", set()))
            already = fp in known
            known.add(fp)
            self._known_open_paths = known
            if already:
                return
            from infrastructure.instance_broadcast import notify_file_event

            notify_file_event("file_opened", fp)
        except Exception:
            pass

    def _on_local_tab_closed(self, index):
        try:
            from infrastructure.instance_broadcast import notify_file_event

            current = self._local_open_paths()
            known = getattr(self, "_known_open_paths", set())
            for fp in known - current:
                notify_file_event("file_closed", fp)
            self._known_open_paths = current
        except Exception:
            pass

    def _on_remote_file_opened(self, path, mtime, pid):
        """其它实例打开了文件：状态栏提示（不自动打开）"""
        import os

        if pid == os.getpid():
            return
        try:
            self.status_bar.showMessage("其它实例已打开: %s" % os.path.basename(path), 2000)
        except Exception:
            pass

    def _on_remote_file_closed(self, path, mtime, pid):
        import os

        if pid == os.getpid():
            return
        try:
            self.status_bar.showMessage("其它实例已关闭: %s" % os.path.basename(path), 2000)
        except Exception:
            pass

    def _follow_system_high_contrast(self) -> bool:
        try:
            from PyQt5.QtCore import QSettings

            return bool(
                QSettings("QingCao", "Editor").value("follow_system_high_contrast", True, type=bool)
            )
        except Exception:
            return True

    def apply_high_contrast_if_needed(self) -> bool:
        """系统高对比度开启时应用系统调色板 QSS（v2.13.0 P0）"""
        try:
            from infrastructure.theme_loader import build_high_contrast_qss, system_high_contrast

            hc = system_high_contrast()
            self._system_high_contrast = bool(hc)
            if hc and self._follow_system_high_contrast():
                self._suppress_panel_qss()
                qss = build_high_contrast_qss()
                self._current_theme_qss = qss
                self.setStyleSheet(qss)
                self._apply_theme_to_top_levels(qss)
                self.status_bar.showMessage("已启用高对比度适配（跟随系统）", 3000)
                return True
            self._restore_panel_qss()
        except Exception:
            pass
        return False

    def _set_follow_system_high_contrast(self, enabled):
        try:
            from PyQt5.QtCore import QSettings

            s = QSettings("QingCao", "Editor")
            s.setValue("follow_system_high_contrast", bool(enabled))
            s.sync()
        except Exception:
            pass
        if enabled:
            self.apply_high_contrast_if_needed()
        else:
            self._system_high_contrast = False
            self._restore_panel_qss()
            try:
                self._apply_theme_by_name(self._current_theme_name or "")
            except Exception:
                pass
        self.status_bar.showMessage("跟随系统高对比度: %s" % ("开启" if enabled else "关闭"), 2500)

    def _on_remote_config_changed(self, plugin_name):
        """其它实例修改了插件配置：重新读取并下发（配置变更广播）"""
        try:
            from infrastructure.plugin_sandbox_manager import load_plugin_config

            plugins = self._get_sandboxed_plugins() or {}
            sp = plugins.get(plugin_name)
            if sp is None:
                return
            schema = sp.config_schema()
            if not schema:
                return
            values = load_plugin_config(plugin_name, schema)
            ok = bool(sp.config_apply(values))
            self._last_synced_config = (plugin_name, values)
            try:
                self.run_sandboxed_diagnostics()
            except Exception:
                pass
            try:
                self.refresh_sandbox_plugin_menus(quiet=True)
            except Exception:
                pass
            self._refresh_sandbox_status()
            self.status_bar.showMessage(
                "配置已同步（来自其它实例）: %s · %s%s"
                % (plugin_name, "成功" if ok else "失败", " · 已刷新菜单/诊断" if ok else ""),
                5000,
            )
        except Exception:
            pass

    def apply_accessibility_settings(self):
        """应用无障碍设置：字体缩放 + 可访问名称（v2.17）"""
        try:
            from PyQt5.QtCore import QSettings

            from ui.accessibility import apply_accessible_names, apply_font_scale

            factor = QSettings("QingCao", "Editor").value("ui_scale", 1.0, type=float)
            apply_font_scale(self, factor or 1.0)
            apply_accessible_names(self)
        except Exception:
            pass

    def _live_diag_limit(self) -> int:
        """实时沙箱诊断大文件阈值（可配置，v2.17）"""
        try:
            from core.large_file import live_diagnostics_limit_bytes

            return live_diagnostics_limit_bytes()
        except Exception:
            return self.MAX_LIVE_DIAGNOSTICS_BYTES

    def _on_peer_versions_changed(self, versions):
        """多实例协议版本协商结果（v2.15.x）"""
        try:
            from infrastructure.instance_broadcast import PROTOCOL_VERSION

            bad = {
                int(p): int(v) for p, v in (versions or {}).items() if int(v) != PROTOCOL_VERSION
            }
        except Exception:
            return
        if bad and not getattr(self, "_compat_warned", False):
            self._compat_warned = True
            try:
                self.status_bar.showMessage(
                    "检测到不同协议版本的实例（%s），已按兼容模式处理" % bad, 5000
                )
            except Exception:
                pass

    def _on_focus_requested(self):
        """其它实例请求聚焦：还原并激活当前窗口（单实例行为）"""
        try:
            if self.isMinimized():
                self.showNormal()
            self.raise_()
            self.activateWindow()
            self.status_bar.showMessage("已切换到运行中的实例", 2000)
        except Exception:
            pass

    def _start_instance_broadcast(self):
        """多实例：启动保存广播并处理远端保存事件（P0）"""
        try:
            from infrastructure.instance_broadcast import start_broadcast

            self._broadcast = start_broadcast()
            self._broadcast.file_saved.connect(self._on_remote_file_saved)
            self._broadcast.file_opened.connect(self._on_remote_file_opened)
            self._broadcast.file_closed.connect(self._on_remote_file_closed)
            self._broadcast.focus_requested.connect(self._on_focus_requested)
            self._broadcast.config_changed.connect(self._on_remote_config_changed)
            try:
                from PyQt5.QtCore import QTimer as _QTimer

                self._broadcast.peer_versions_changed.connect(self._on_peer_versions_changed)
                _QTimer.singleShot(1500, self._broadcast.announce_hello)
            except Exception:
                pass
            try:
                from PyQt5.QtCore import QTimer

                def _deferred_sandbox_ui():
                    try:
                        self._apply_sandbox_configs()
                    except Exception:
                        pass
                    self.refresh_sandbox_plugin_menus(quiet=True)

                QTimer.singleShot(1500, _deferred_sandbox_ui)
            except Exception:
                pass
            if hasattr(self.tabs, "tab_opened"):
                self._known_open_paths = self._local_open_paths()
                self.tabs.tab_opened.connect(self._on_local_tab_opened)
                self.tabs.tab_closed.connect(self._on_local_tab_closed)
                for _i in range(self.tabs.count()):
                    self._hook_sandbox_live_tab(_i)
        except Exception as e:
            print(f"[MainWindow] 启动多实例广播失败: {e}")

    def _on_remote_file_saved(self, path, mtime, pid):
        """其它实例保存了同一文件：冲突检测 + 自动重载/询问（v2.12.0 P0）"""
        import os

        if not path or pid == os.getpid():
            return
        try:
            count = self.tabs.count()
        except Exception:
            return
        for idx in range(count):
            try:
                editor = self.tabs.widget(idx)
                fp = getattr(getattr(editor, "document", None), "filepath", "") or ""
                if not fp or os.path.normcase(fp) != os.path.normcase(path):
                    continue
                doc = getattr(editor, "document", None)
                if doc is None:
                    modified = False
                else:
                    try:
                        modified = bool(doc.is_modified)
                    except TypeError:
                        modified = bool(doc.is_modified())
                if modified:
                    self._last_remote_conflict = {"path": path, "mtime": mtime, "pid": pid}
                    from PyQt5.QtWidgets import QMessageBox

                    ret = QMessageBox.question(
                        self,
                        "保存冲突",
                        "该文件已被其它实例保存，而本地还有未保存修改。\n"
                        "继续保留本地修改可能与对方互相覆盖。\n\n"
                        "是否重新加载磁盘上的最新内容？\n%s" % path,
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No,
                    )
                    if ret != QMessageBox.Yes:
                        try:
                            self.status_bar.showMessage(
                                "保留本地修改（冲突未解决）: %s" % os.path.basename(path), 4000
                            )
                        except Exception:
                            pass
                        return
                reload_fn = getattr(self.tabs, "_reload_file", None)
                if reload_fn is not None:
                    reload_fn(path, editor)
                    self._last_remote_conflict = None
                    self.status_bar.showMessage("已从磁盘重载: %s" % os.path.basename(path), 3000)
                return
            except Exception:
                continue

    def _apply_theme_to_top_levels(self, qss=None):
        """把当前主题 QSS 套到所有独立顶层窗口（C-2）"""
        qss = qss or getattr(self, "_current_theme_qss", "")
        if not qss:
            return 0
        try:
            from PyQt5.QtWidgets import QApplication, QMenu, QToolTip
        except Exception:
            return 0
        theme = getattr(self, "_startup_theme", None)
        count = 0
        for w in QApplication.topLevelWidgets():
            try:
                if w is self or not w.isWindow():
                    continue
                if isinstance(w, (QMenu, QToolTip)):
                    continue
                if w.styleSheet() != qss:
                    w.setStyleSheet(qss)
                    count += 1
                if theme is not None:
                    adapt_widget_styles(w, theme)
            except Exception:
                continue
        return count

    def _ensure_toplevel_theme_filter(self):
        """确保安装了"新窗口显示时套主题"的应用级事件过滤器"""
        try:
            from PyQt5.QtWidgets import QApplication

            if getattr(self, "_toplevel_theme_filter", None) is not None:
                return
            self._toplevel_theme_filter = _TopLevelThemeFilter(self)
            QApplication.instance().installEventFilter(self._toplevel_theme_filter)
        except Exception as e:
            print(f"[MainWindow] 安装顶层主题过滤器失败: {e}")

    def _open_dropped_paths(self, paths):
        """打开拖入的文件/目录（供 dropEvent 与测试复用）"""
        import os as _os

        opened = 0
        for path in paths or []:
            try:
                if not path:
                    continue
                if _os.path.isdir(path):
                    if hasattr(self, "_open_folder"):
                        self._open_folder(path)
                    continue
                if hasattr(self, "tabs") and self.tabs is not None:
                    self.tabs.open_file(path)
                    opened += 1
            except Exception as e:
                print(f"[MainWindow] 拖放打开失败({path}): {e}")
        if opened:
            try:
                self.status_bar.showMessage("已打开 %d 个拖入文件" % opened, 2500)
            except Exception:
                pass
        return opened

    def dragEnterEvent(self, event):
        try:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                return
        except Exception:
            pass
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        try:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                return
        except Exception:
            pass
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        try:
            if not event.mimeData().hasUrls():
                super().dropEvent(event)
                return
            paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            event.acceptProposedAction()
            self._open_dropped_paths(paths)
        except Exception as e:
            print(f"[MainWindow] 拖放处理失败: {e}")

    def _build_print_document(self):
        """把当前编辑器文本构建为 QTextDocument（供打印/预览复用）"""
        from PyQt5.QtGui import QFont, QTextDocument

        proxy = self.tabs.current_proxy()
        text = ""
        try:
            if proxy is not None:
                text = proxy.get_text() or ""
        except Exception:
            text = ""
        doc = QTextDocument()
        font = QFont("Consolas")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(10)
        doc.setDefaultFont(font)
        doc.setPlainText(text)
        return doc, proxy

    def _print_document(self):
        """文件 → 打印…（NPP 对齐）"""
        try:
            from PyQt5.QtPrintSupport import QPrintDialog, QPrinter

            doc, _proxy = self._build_print_document()
            if doc.isEmpty():
                self.status_bar.showMessage("没有可打印的内容", 2500)
                return
            printer = QPrinter(QPrinter.HighResolution)
            dlg = QPrintDialog(printer, self)
            dlg.setWindowTitle("打印")
            if dlg.exec_() == QPrintDialog.Accepted:
                doc.print_(printer)
                self.status_bar.showMessage("已发送到打印机", 2500)
        except Exception as e:
            self.status_bar.showMessage("打印失败: %s" % e, 3000)

    def _print_preview(self):
        """文件 → 打印预览…（NPP 对齐）"""
        try:
            from PyQt5.QtPrintSupport import QPrinter, QPrintPreviewDialog

            doc, _proxy = self._build_print_document()
            if doc.isEmpty():
                self.status_bar.showMessage("没有可打印的内容", 2500)
                return
            printer = QPrinter(QPrinter.HighResolution)
            dlg = QPrintPreviewDialog(printer, self)
            dlg.setWindowTitle("打印预览")
            dlg.resize(900, 700)
            dlg.paintRequested.connect(lambda pr: doc.print_(pr))
            dlg.exec_()
        except Exception as e:
            self.status_bar.showMessage("打印预览失败: %s" % e, 3000)
