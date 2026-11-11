# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""面板/导出/工具菜单（v2.25 从 capability_wiring 拆出）。"""

from ui.mixins.capability_wiring_common import *  # noqa: F401,F403


class PanelsExportMixin:
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
                if hasattr(self.lsp, "set_installer"):
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
            panel = getattr(self, "undo_history", None)
            if proxy is None or panel is None:
                return
            if getattr(proxy, "_undo_history_connected", False):
                return
            um = getattr(proxy, "undo_manager", None)
            if um is None:
                return

            def _refresh(*_a):
                try:
                    if hasattr(panel, "refresh"):
                        panel.refresh()
                except Exception:
                    pass

            try:
                um.stack_changed.connect(_refresh)
                proxy._undo_history_connected = True
            except Exception:
                pass
            for setter in ("set_manager", "set_undo_manager"):
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
        panels.append(("LSP 状态", "panel.lsp", self._toggle_lsp_panel))
        panels.append(("撤销历史", "panel.undo_history", self._toggle_undo_history_panel))
        return panels

    def _show_feedback(self, checked=False):
        """打开反馈与建议对话框（本地保存）"""
        try:
            from ui.feedback_dialog import FeedbackDialog
            from version import __version__

            FeedbackDialog(self, version=__version__).exec_()
        except Exception as e:
            print(f"[MainWindow] 反馈对话框打开失败: {e}")

    def _toggle_terminal(self, checked):
        """切换终端面板"""
        if self._ensure_panel("terminal") and getattr(self, "terminal", None):
            self.terminal.setVisible(checked)
            if checked:
                try:
                    self.terminal.input.setFocus()
                except Exception:
                    pass

    def _toggle_lsp_panel(self, checked):
        """切换 LSP 面板"""
        if self._ensure_panel("lsp") and getattr(self, "lsp", None):
            self.lsp.setVisible(checked)

    def _toggle_undo_history_panel(self, checked):
        """切换撤销历史面板"""
        if self._ensure_panel("undo_history") and getattr(self, "undo_history", None):
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

        self._add_action(self.export_menu, "导出为 PDF…", None, self._export_current_as_pdf)
        self._add_action(self.export_menu, "导出为 HTML…", None, self._export_current_as_html)
        self._add_action(
            self.export_menu, "导出为 Markdown…", None, self._export_current_as_markdown
        )

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
                    acts[0].setToolTip("需要 reportlab：pip install reportlab")
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
                self,
                "导出",
                os.path.join(os.path.dirname(proxy.document.filepath or ""), default),
                filters,
            )
            if not path:
                return

            import core.exporter as exporter

            text = proxy.get_text()
            title = os.path.basename(proxy.document.filepath or "未命名")
            language = "text"
            try:
                language = getattr(proxy.document.meta, "language", "text") or "text"
            except Exception:
                pass

            if fmt == "pdf":
                ok = exporter.to_pdf(text, path, title=title)
                if isinstance(ok, tuple):  # 可能返回 (ok, msg)
                    ok = ok[0]
            elif fmt == "html":
                content = exporter.to_html(text, title=title, language=language)
                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(content)
                ok = True
            else:
                content = exporter.to_markdown(text, title=title, language=language)
                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(content)
                ok = True

            self.status_bar.showMessage(
                f"已导出: {os.path.basename(path)}" if ok else "导出失败（详见日志）", 5000
            )
        except ImportError as e:
            self.status_bar.showMessage(
                f"导出失败：缺少依赖（{e}）。PDF 需要 reportlab：pip install reportlab", 9000
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
                QMessageBox.information(self, "崩溃统计", "没有记录到崩溃。")
                return
            top = stats.get_top_exceptions(5)
            recent = stats.get_recent_count(7)
            lines = [
                f"累计崩溃次数：{total}",
                f"最近 7 天：{recent}",
                "",
                "最常见异常：",
            ]
            for item in top or []:
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
    # 代码模板（core/code_templates.py）
    # ========================================================
    def _new_from_template(self):
        """从模板新建文件（`ui/template_picker_dialog.py`）

        `core/code_templates.py`（240 行）提供了 8 个真实模板：
        Python 类 / 函数 / 测试 / 主程序、JS 函数 / 类、`.gitignore`、`README`。
        此前**零引用**，用户只能每次手敲 class 骨架。
        """
        try:
            from ui.template_picker_dialog import show_template_picker

            text, filename = show_template_picker(self)
            if text is None:
                return

            # 直接建标签（**不要**调 `_new_file()` —— 那会再弹一次
            # "选择文件类型"对话框，用户在模板对话框里已经选过了）
            title = filename or "未命名"
            editor = self.tabs.add_tab(title)
            if editor is None:
                self.status_bar.showMessage("新建标签失败", 4000)
                return
            proxy = getattr(editor, "proxy", None)
            if proxy is None:
                self.status_bar.showMessage("新建标签失败（无编辑器）", 4000)
                return
            proxy.set_text(text)

            # 切到编辑区
            try:
                if self.central_stack:
                    self.central_stack.setCurrentIndex(0)
            except Exception:
                pass

            self.status_bar.showMessage("已从模板生成「%s」，保存时请确认文件名" % title, 6000)
        except Exception as e:
            print(f"[MainWindow] 从模板新建失败: {e}")
            try:
                self.status_bar.showMessage(f"从模板新建失败: {e}", 6000)
            except Exception:
                pass

    # ========================================================
    # 会话快照（core/snapshot.py + ui/snapshot_manager_dialog.py）
    # ========================================================
    def _show_snapshot_dialog(self):
        """打开会话快照对话框

        `core/snapshot.py`（191 行）+ `ui/snapshot_manager_dialog.py`（154 行）
        此前**零引用**。功能：把"当前所有打开的文件 + 光标位置 + 窗口布局"
        存成快照，随时一键恢复 —— 对应真实的"切任务再切回来"场景。

        注意：恢复会**关闭当前所有标签**，因此对话框里已加"未保存修改保护"
        （先统一提示保存/放弃/取消，避免逐个模态框导致半恢复状态）。
        """
        try:
            from ui.snapshot_manager_dialog import SnapshotDialog

            dlg = SnapshotDialog(self, self)
            dlg.exec_()
        except Exception as e:
            print(f"[MainWindow] 会话快照失败: {e}")
            try:
                self.status_bar.showMessage(f"会话快照失败: {e}", 6000)
            except Exception:
                pass

    # ========================================================
    # 代码片段库（ui/snippet_market_dialog.py + core/snippet_market.py）
    # ========================================================
    def _show_snippet_library(self):
        """打开代码片段库（本地片段包）

        ## 从"网络市场"改为"本地库"的原因

        原实现是网络市场客户端，`MARKET_API` 指向
        `https://api.github.com/repos/qingcao-editor/snippets/contents`
        —— **实测该地址返回 HTTP 404，仓库不存在**。
        接上 UI 也只会显示 4 条硬编码示例，"市场"是假的。

        现改为扫描本地片段包目录（默认 `<应用根>/data/snippet_packs`，
        可自选目录）：零运维、零信任风险（不执行第三方下载内容），
        核心价值（复用别人写好的片段）不变。
        """
        try:
            from ui.snippet_market_dialog import SnippetMarketDialog

            dlg = SnippetMarketDialog(self)
            dlg.exec_()
        except Exception as e:
            print(f"[MainWindow] 代码片段库失败: {e}")
            try:
                self.status_bar.showMessage(f"代码片段库失败: {e}", 6000)
            except Exception:
                pass

    # ========================================================
    # 性能剖析（core/profiler.py + ui/profiler_panel.py）
    # ========================================================
    def _show_profiler(self):
        """打开性能剖析对话框（`ui/profiler_panel.py`）

        ## 这两个模块此前是零引用的
        `core/profiler.py`（67 行，cProfile 封装）与
        `ui/profiler_panel.py`（166 行，完整对话框）此前**零引用**，
        用户完全看不到 —— 而"某个插件让编辑器变慢"正是最常见的困扰。

        ## ★ 使用局限（必须如实告知，否则用户会误读报告）
        `cProfile` 只统计 **Python 帧**。Qt 的 C++ 事件循环、Scintilla 的
        绘制/排版耗时**都不会出现在报告里**。因此本工具适合排查：

        * 插件的 Python 回调慢（如 AI 请求解析、日志格式化）；
        * 搜索/正则匹配慢（`core/search.py`）；
        * 大文件解析/语法分析慢。

        **不适合**用来测"编辑器滚动卡不卡""窗口重绘慢不慢" ——
        那类问题请看「工具 → 📊 性能监控」（`ui/perf_monitor.py`），
        它读的是进程级 CPU/内存与 Scintilla 的行数/字节数。
        """
        try:
            from ui.profiler_panel import ProfilerDialog

            dlg = ProfilerDialog(self)
            try:
                dlg.setToolTip(
                    "cProfile 只统计 Python 帧：Qt 事件循环与 Scintilla 的\n"
                    "绘制/排版耗时不在报告里。\n"
                    "适合排查插件回调 / 搜索 / 解析慢；\n"
                    "要看整体流畅度请用「工具 → 📊 性能监控」。"
                )
            except Exception:
                pass
            dlg.exec_()
        except Exception as e:
            print(f"[MainWindow] 性能剖析失败: {e}")
            try:
                self.status_bar.showMessage(f"性能剖析失败: {e}", 6000)
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
            menu = self._make_menu("⭐ 特色功能")
            anchor = getattr(self, "_view_menu_action", None) or self.view_menu.menuAction()
            # ⚠️ 实测坑：`QMenuBar.insertMenu()` 返回的是 **QAction**
            #   （即菜单的 menuAction），不是 QMenu。原实现把返回值直接
            #   赋给 `self.feature_menu`，后续 `addSeparator()` 就抛
            #   `AttributeError: 'QAction' object has no attribute
            #   'addSeparator'`，整个 MainWindow 构造失败。
            self.menuBar().insertMenu(anchor, menu)
            self.feature_menu = menu
        except Exception:
            try:
                self.feature_menu = self.menuBar().addMenu("⭐ 特色功能")
            except Exception as e:
                if logger:
                    logger.debug("创建特色功能菜单失败: %s", e)
                return

        # AI：直接列出 AI 助手插件**真实注册**的命令（命令面板里同源）
        self._add_plugin_commands_submenu("🤖 AI 助手（ai_assistant）", "ai_assistant", "ai")
        self.feature_menu.addSeparator()
        self._add_plugin_commands_submenu("🔀 Git（git_deep）", "git_deep", "git")
        self.feature_menu.addSeparator()
        # 调试：**复用工具菜单里已存在的 F5 动作**，绝不新建。
        #
        # ⚠️ 实测教训：先前这里用 `_add_action(..., "▶ 运行当前文件", "F5", ...)`
        #   新建了一个 QAction，于是全仓出现**两个 F5** ——
        #   `tests/test_shortcuts.py::test_f5_is_run_current_file` 与
        #   `test_no_duplicate_non_empty_shortcuts` 立刻失败，Qt 也会判定
        #   ambiguous shortcut 导致 F5 彻底失效。
        #   正确做法是把已有 QAction 加进本菜单（同一动作可在多菜单出现）。
        run_action = self._find_action_with_text("▶ 运行当前文件")
        if run_action is not None:
            self.feature_menu.addAction(run_action)
        else:
            self._add_action(self.feature_menu, "▶ 运行当前文件", None, self._debug_run)
        self._add_action(self.feature_menu, "⚙ 在当前行切换断点", None, self._debug_breakpoint)
        self.feature_menu.addSeparator()
        self._add_action(self.feature_menu, "🧠 LSP 状态 / 安装向导", None, self._show_panel_lsp)
        self._add_action(
            self.feature_menu, "📊 问题（LSP 诊断）", None, lambda: self._show_panel("problems")
        )
        self._sync_feature_plugin_visibility()

    def _sync_feature_plugin_visibility(self):
        """按插件命令是否存在，显示/隐藏「特色功能」中的插件子菜单（v2.19 P2）"""
        try:
            menus = getattr(self, "_feature_plugin_menus", {}) or {}
        except Exception:
            return
        for menu in menus.values():
            try:
                has_items = any(not a.isSeparator() for a in menu.actions())
                menu.menuAction().setVisible(bool(has_items))
            except Exception:
                continue
        # 清理相邻分隔符（避免隐藏后出现连续分隔线）
        try:
            acts = self.feature_menu.actions()
            for i, act in enumerate(acts):
                if not act.isSeparator():
                    continue
                left = next((x for x in reversed(acts[:i]) if not x.isSeparator()), None)
                right = next((x for x in acts[i + 1 :] if not x.isSeparator()), None)
                visible = any(x is not None and x.isVisible() for x in (left, right))
                act.setVisible(visible)
        except Exception:
            pass
