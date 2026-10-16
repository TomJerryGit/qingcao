# -*- coding: utf-8 -*-
"""
青草编辑器 - 能力接线 Mixin（P0-4/5/6/10 + P1 入口重排）
========================================================

本模块集中"把已实现但零引用的能力接到 UI 上"的代码，独立于
`ui/main_window.py`，避免与其它改动互相冲突。

接线清单（每项都注明"此前为何用不到"）：

| 能力 | 源 | 接线方式 |
|---|---|---|
| 本地格式化 | `core/formatter.py`（Black/autopep8/clang-format） | 工具菜单「格式化文档」 |
| LSP 状态/安装向导 | `ui/lsp_panel.py`（548 行） | 面板：LSP |
| 撤销历史 | `ui/undo_history_panel.py`（229 行） | 面板：撤销历史 |
| 崩溃统计 | `core/crash_stats.py`（240 行） | 帮助菜单「崩溃统计」 |
| 导出 PDF/HTML | `core/exporter.py`（157 行） | 文件菜单「导出」 |

**设计约束**：所有方法都做了防御性 `try/except` 与 `hasattr` 检查 ——
因为面板/引擎可能在打包产物中缺失（`build.py` 的 hiddenimports 会静默
跳过不存在模块），缺一个能力不该让整个菜单构建失败。
"""

import logging
import os


logger = logging.getLogger(__name__)


class CapabilityWiringMixin:
    """能力接线 Mixin —— 由 MainWindow 继承

    依赖属性：``self.tabs``、``self.status_bar``、``self.panel_menu``、
    ``self.tools_menu``、``self.file_menu``、``self.help_menu``、
    ``self._ensure_panel``
    """

    # ========================================================
    # P0-4：本地格式化（core/formatter.py 此前零引用）
    # ========================================================
    def _setup_format_menu(self):
        """在工具菜单挂「格式化文档」子菜单"""
        try:
            from core.formatter import get_formatter_registry

            available = [f.name for f in get_formatter_registry()
                         .list_available()]
        except Exception:
            available = []

        try:
            self.format_menu = self.tools_menu.addMenu("🪄 格式化文档")
        except Exception as e:
            if logger:
                logger.debug("创建格式化菜单失败: %s", e)
            return

        # 始终提供"自动选择"，即使当前机器一个格式化器都没装 ——
        # 菜单项存在但点击时给出明确安装提示，比菜单项凭空消失好。
        self._add_action(self.format_menu, "自动选择可用格式化器",
                         "Ctrl+Alt+Shift+F", self._format_document)
        if available:
            self.format_menu.addSeparator()
            for name in available:
                label = {
                    "black": "Black（Python）",
                    "autopep8": "autopep8（Python）",
                    "clang-format": "clang-format（C/C++/Java/JS）",
                }.get(name, name)
                self._add_action(
                    self.format_menu, label, None,
                    lambda _checked=False, n=name: self._format_document(n),
                )
        else:
            self.format_menu.addSeparator()
            act = self._add_action(
                self.format_menu, "（未检测到本地格式化器）", None, None
            )
            try:
                if act is not None:
                    act.setEnabled(False)
                    act.setToolTip(
                        "安装方式：pip install black 或 pip install autopep8"
                    )
            except Exception:
                pass

    # ========================================================
    # 面板：LSP 状态 / 撤销历史（对应孤立 UI 文件）
    # ========================================================
    def _build_panel_lsp(self):
        """构造 LSP 面板（`ui/lsp_panel.py` 此前零实例化）

        该模块还包含 `LspInstallerDialog`（语言服务器安装向导）——
        用户启用 LSP 失败时，这里能引导安装，而不是只给一句
        "请 pip install ..." 的状态栏文字。

        ⚠️ 属性名必须是 **`self.lsp`**：`MainWindow._ensure_panel(name)`
        会做 `getattr(self, name)`，而 name 来自 `_LAZY_PANELS`（'lsp'）。
        用别的名字（如 `lsp_panel`）会让 `_ensure_panel('lsp')` 返回 False。
        """
        try:
            from ui.lsp_panel import LspPanel
            # 注意签名是 `(main_window=None, parent=None)` —— 主窗口要按
            # **关键字**传，否则会被当成 main_window 而不是 parent。
            self.lsp = LspPanel(main_window=self, parent=self)
            try:
                self.lsp.setObjectName("LspPanel")
            except Exception:
                pass
            self.addDockWidget(self._right_dock_area(), self.lsp)
            self.lsp.hide()
            try:
                if hasattr(self.lsp, 'set_installer'):
                    from core.lsp_installer import LspInstaller
                    self.lsp.set_installer(LspInstaller())
            except Exception:
                pass
        except Exception as e:
            print(f"[MainWindow] LspPanel 加载失败: {e}")
            self.lsp = None

    def _build_panel_undo_history(self):
        """构造撤销历史面板（`ui/undo_history_panel.py` 此前零实例化）

        ⚠️ 属性名必须是 **`self.undo_history`**（理由同上）。
        """
        try:
            from ui.undo_history_panel import UndoHistoryPanel
            self.undo_history = UndoHistoryPanel(main_window=self, parent=self)
            try:
                self.undo_history.setObjectName("UndoHistoryPanel")
            except Exception:
                pass
            self.addDockWidget(self._bottom_dock_area(), self.undo_history)
            self.undo_history.hide()
            self._connect_undo_history()
        except Exception as e:
            print(f"[MainWindow] UndoHistoryPanel 加载失败: {e}")
            self.undo_history = None

    def _connect_undo_history(self):
        """把当前标签的撤销栈变化实时喂给撤销历史面板"""
        try:
            proxy = self.tabs.current_proxy()
            panel = getattr(self, 'undo_history', None)
            if proxy is None or panel is None:
                return
            if getattr(proxy, '_undo_history_connected', False):
                return
            um = getattr(proxy, 'undo_manager', None)
            if um is None:
                return

            def _refresh(*_a):
                try:
                    if hasattr(panel, 'refresh'):
                        panel.refresh()
                except Exception:
                    pass

            try:
                um.stack_changed.connect(_refresh)
                proxy._undo_history_connected = True
            except Exception:
                pass
            for setter in ('set_manager', 'set_undo_manager'):
                if hasattr(panel, setter):
                    try:
                        getattr(panel, setter)(um)
                    except Exception:
                        pass
                    break
        except Exception as e:
            if logger:
                logger.debug("连接撤销历史面板失败: %s", e)

    # --------------------------------------------------------
    # 面板菜单接线（由 Lead 在 main_window 里调用一次）
    # --------------------------------------------------------
    def _append_panel_menu_items(self, panels: list) -> list:
        """向面板子菜单追加"LSP / 撤销历史"两项

        参数:
            panels: `_build_panel_menu` 里已有的 (名称, action, slot) 列表

        返回:
            追加后的列表（便于链式调用）
        """
        panels.append(("LSP 状态", "panel.lsp",
                       self._toggle_lsp_panel))
        panels.append(("撤销历史", "panel.undo_history",
                       self._toggle_undo_history_panel))
        return panels

    def _toggle_lsp_panel(self, checked):
        """切换 LSP 面板"""
        if self._ensure_panel('lsp') and getattr(self, 'lsp', None):
            self.lsp.setVisible(checked)

    def _toggle_undo_history_panel(self, checked):
        """切换撤销历史面板"""
        if self._ensure_panel('undo_history') and \
                getattr(self, 'undo_history', None):
            self.undo_history.setVisible(checked)
            if checked:
                self._connect_undo_history()

    def _right_dock_area(self):
        """右侧停靠区（避免各面板各自 import Qt 常量）"""
        try:
            from PyQt5.QtCore import Qt
            return Qt.RightDockWidgetArea
        except Exception:
            return 2

    def _bottom_dock_area(self):
        """底部停靠区"""
        try:
            from PyQt5.QtCore import Qt
            return Qt.BottomDockWidgetArea
        except Exception:
            return 8

    # ========================================================
    # P0-10：导出（core/exporter.py 此前零引用）
    # ========================================================
    def _setup_export_menu(self):
        """在文件菜单挂「导出」子菜单

        兑现 `requirements.txt` 里"文件 → 导出 → PDF"的承诺
        （此前文档写了、菜单里却没有）。
        """
        try:
            self.export_menu = self.file_menu.addMenu("📤 导出")
        except Exception as e:
            if logger:
                logger.debug("创建导出菜单失败: %s", e)
            return

        self._add_action(self.export_menu, "导出为 PDF…", None,
                         self._export_current_as_pdf)
        self._add_action(self.export_menu, "导出为 HTML…", None,
                         self._export_current_as_html)
        self._add_action(self.export_menu, "导出为 Markdown…", None,
                         self._export_current_as_markdown)

        # reportlab 是可选依赖：缺失时禁用 PDF 项并说明原因
        try:
            import reportlab  # noqa: F401
            pdf_ok = True
        except Exception:
            pdf_ok = False
        if not pdf_ok:
            try:
                acts = self.export_menu.actions()
                if acts:
                    acts[0].setEnabled(False)
                    acts[0].setToolTip(
                        "需要 reportlab：pip install reportlab"
                    )
            except Exception:
                pass

    def _export_current(self, fmt: str):
        """导出当前文件（fmt: 'pdf' / 'html' / 'md'）

        对接 `core/exporter.py` 的**模块级函数**（不是类）：
        `to_html(text, title, language)` / `to_pdf(text, output_path, title)`
        / `to_markdown(...)`。
        """
        try:
            proxy = self.tabs.current_proxy()
            if proxy is None:
                self.status_bar.showMessage("没有活动的编辑器", 3000)
                return
            from PyQt5.QtWidgets import QFileDialog

            ext = {"pdf": "pdf", "html": "html", "md": "md"}[fmt]
            default = f"导出.{ext}"
            filters = {
                "pdf": "PDF (*.pdf)",
                "html": "HTML (*.html)",
                "md": "Markdown (*.md)",
            }[fmt]
            path, _ = QFileDialog.getSaveFileName(
                self, "导出",
                os.path.join(os.path.dirname(
                    proxy.document.filepath or ""), default),
                filters,
            )
            if not path:
                return

            import core.exporter as exporter
            text = proxy.get_text()
            title = os.path.basename(proxy.document.filepath or "未命名")
            language = "text"
            try:
                language = getattr(proxy.document.meta, "language", "text") \
                    or "text"
            except Exception:
                pass

            if fmt == "pdf":
                ok = exporter.to_pdf(text, path, title=title)
                if isinstance(ok, tuple):        # 可能返回 (ok, msg)
                    ok = ok[0]
            elif fmt == "html":
                content = exporter.to_html(text, title=title,
                                           language=language)
                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(content)
                ok = True
            else:
                content = exporter.to_markdown(text, title=title,
                                               language=language)
                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(content)
                ok = True

            self.status_bar.showMessage(
                f"已导出: {os.path.basename(path)}" if ok
                else "导出失败（详见日志）", 5000
            )
        except ImportError as e:
            self.status_bar.showMessage(
                f"导出失败：缺少依赖（{e}）。PDF 需要 reportlab："
                f"pip install reportlab", 9000
            )
        except Exception as e:
            print(f"[MainWindow] 导出失败: {e}")
            try:
                self.status_bar.showMessage(f"导出失败: {e}", 8000)
            except Exception:
                pass

    def _export_current_as_pdf(self):
        self._export_current("pdf")

    def _export_current_as_html(self):
        self._export_current("html")

    def _export_current_as_markdown(self):
        self._export_current("md")

    # ========================================================
    # P0-6：崩溃统计（core/crash_stats.py 此前零引用）
    # ========================================================
    def _show_crash_stats(self):
        """显示崩溃统计（`CrashStats` 有能力、此前无入口）

        `crash_stats.py` 提供 `get_total_count` / `get_top_exceptions` /
        `get_recent_count` / `should_notify` / `cleanup_old` —— 这些信息
        对"这个版本是不是经常崩"的判断很有用，但此前完全看不到。
        """
        try:
            from PyQt5.QtWidgets import QMessageBox

            from core.crash_stats import CrashStats
            stats = CrashStats()
            total = stats.get_total_count()
            if not total:
                QMessageBox.information(
                    self, "崩溃统计", "没有记录到崩溃。"
                )
                return
            top = stats.get_top_exceptions(5)
            recent = stats.get_recent_count(7)
            lines = [
                f"累计崩溃次数：{total}",
                f"最近 7 天：{recent}",
                "",
                "最常见异常：",
            ]
            for item in (top or []):
                try:
                    name, cnt = item[0], item[1]
                except Exception:
                    name, cnt = str(item), ""
                lines.append(f"  {cnt} 次  {name}")
            summary = stats.get_summary()
            if summary:
                lines.append("")
                lines.append("汇总：")
                for k, v in list(summary.items())[:8]:
                    lines.append(f"  {k}: {v}")
            QMessageBox.information(self, "崩溃统计", "\n".join(lines))
        except Exception as e:
            print(f"[MainWindow] 崩溃统计失败: {e}")
            try:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.warning(self, "崩溃统计", f"读取失败: {e}")
            except Exception:
                pass

    # ========================================================
    # P1-7：差异化能力入口提升（用户找不到 = 差异化不存在）
    # ========================================================
    def _setup_feature_menu(self):
        """建「AI / Git / 调试」一级可见的入口聚合菜单

        背景（P1-7）：
            AI、Git、调试器这三条**差异化主线**目前分散在插件注册路径
            （`工具/Git/...`、AI 助手自己的菜单）。试用者很容易以为
            "这编辑器没有这些能力"。因此这里做一个聚合入口把它们
            提升为一级可见 —— 只做**导航**，不重复实现功能。
        """
        try:
            self.feature_menu = self.menuBar().insertMenu(
                getattr(self, '_view_menu_action', None)
                or self.view_menu.menuAction(),
                self._make_menu("⭐ 特色功能"),
            )
        except Exception:
            try:
                self.feature_menu = self.menuBar().addMenu("⭐ 特色功能")
            except Exception as e:
                if logger:
                    logger.debug("创建特色功能菜单失败: %s", e)
                return

        # AI：调用插件已注册的命令（不重复实现）
        self._add_action(self.feature_menu, "🤖 AI 助手", None,
                         lambda: self._invoke_plugin_command("ai_assistant"))
        self._add_action(self.feature_menu, "💬 AI 行内补全", None,
                         self._toggle_ai_inline)
        self.feature_menu.addSeparator()
        self._add_action(self.feature_menu, "🔀 Git 状态/差异", None,
                         lambda: self._invoke_plugin_command("git_deep"))
        self.feature_menu.addSeparator()
        self._add_action(self.feature_menu, "🐞 启动调试 (F7)", "F7",
                         self._debug_run)
        self._add_action(self.feature_menu, "⚙ 编辑器内设置 (F9 断点)",
                         None, self._debug_breakpoint)
        self.feature_menu.addSeparator()
        self._add_action(self.feature_menu, "🧠 LSP 智能（子菜单见工具）",
                         None, self._show_panel_lsp)

    def _make_menu(self, title):
        """创建一个 QMenu（抽出来便于异常处理）"""
        from PyQt5.QtWidgets import QMenu
        return QMenu(title, self)

    def _invoke_plugin_command(self, plugin_name: str):
        """触发某个插件注册的命令/面板（找不到时给出明确提示）"""
        try:
            # 优先：插件注册的命令（命令面板里同源）
            mgr = getattr(self, 'plugin_manager', None) or \
                getattr(self, 'plugins', None)
            cmds = []
            if self.act_mgr is not None and hasattr(
                    self.act_mgr, 'list_plugin_commands'):
                cmds = self.act_mgr.list_plugin_commands(plugin_name)
            if cmds:
                first = cmds[0]
                slot = getattr(first, 'slot', None) or \
                    getattr(first, 'callback', None)
                if callable(slot):
                    slot()
                    return
            # 退化：显示该插件的面板（若已挂载）
            for attr in ('ai_panel', 'git_panel', 'debug_panel'):
                w = getattr(self, attr, None)
                if w is not None:
                    w.setVisible(True)
                    return
            self.status_bar.showMessage(
                f"未找到插件「{plugin_name}」的入口："
                f"请确认该插件已启用（工具 → 插件管理）", 8000
            )
        except Exception as e:
            print(f"[MainWindow] 调用插件命令失败: {e}")

    def _toggle_ai_inline(self):
        """开关 AI 行内补全（`ui/ai_inline_completer.py`）"""
        try:
            completer = getattr(self, 'ai_inline_completer', None)
            if completer is None:
                self.status_bar.showMessage(
                    "AI 行内补全不可用：请先在插件中配置 AI 服务商"
                    "（工具 → 插件管理 → AI 助手）", 8000
                )
                return
            enabled = getattr(completer, 'enabled', False)
            if hasattr(completer, 'set_enabled'):
                completer.set_enabled(not enabled)
                self.status_bar.showMessage(
                    f"AI 行内补全已{'关闭' if enabled else '开启'}", 3000
                )
        except Exception as e:
            print(f"[MainWindow] 切换 AI 行内补全失败: {e}")

    def _debug_run(self):
        """启动调试（复用已有能力，找不到就明确提示）"""
        try:
            if hasattr(self, '_run_current_file'):
                self._run_current_file()
            else:
                self.status_bar.showMessage("调试不可用", 3000)
        except Exception as e:
            print(f"[MainWindow] 启动调试失败: {e}")

    def _debug_breakpoint(self):
        """切换当前行断点"""
        try:
            proxy = self.tabs.current_proxy()
            if proxy is None:
                return
            if hasattr(proxy, 'toggle_breakpoint'):
                proxy.toggle_breakpoint()
                n = len(proxy.get_breakpoints()) \
                    if hasattr(proxy, 'get_breakpoints') else 0
                self.status_bar.showMessage(f"当前断点数: {n}", 3000)
            else:
                self.status_bar.showMessage("该编辑器不支持断点", 3000)
        except Exception as e:
            print(f"[MainWindow] 切换断点失败: {e}")

    def _show_panel_lsp(self):
        """打开 LSP 面板"""
        try:
            if self._ensure_panel('lsp') and getattr(self, 'lsp', None):
                self.lsp.setVisible(True)
                self.lsp.raise_()
        except Exception as e:
            print(f"[MainWindow] 打开 LSP 面板失败: {e}")
