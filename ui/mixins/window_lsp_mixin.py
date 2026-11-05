# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""MainWindow lsp 职责（v2.23 D2 拆分）。"""

from ui.main_window_common import *  # noqa: F401,F403
from ui.main_window_common import _TopLevelThemeFilter  # noqa: F401


class WindowLSPMixin:
    def _goto_definition(self):
        """转到定义（P6: F12）。

        实际请求由 `EditorProxy.goto_definition()` 发出；失败原因
        （未启用 LSP / 语言服务器缺失 等）通过 `lsp_error` 信号经
        `_on_lsp_message` 显示在状态栏。
        """
        try:
            proxy = self.tabs.current_proxy()
            if not proxy or not hasattr(proxy, "goto_definition"):
                self.status_bar.showMessage("没有活动的编辑器", 3000)
                return
            self._connect_lsp_signals(proxy)
            if not proxy.goto_definition():
                self.status_bar.showMessage("转到定义不可用（详见状态栏提示 / 日志）", 5000)
        except Exception as e:
            logger.error("转到定义失败: %s", e)
            try:
                self.status_bar.showMessage(f"转到定义失败: {e}", 5000)
            except Exception:
                pass

    def _lsp_pref_enabled(self) -> bool:
        """读取 LSP 开关偏好（健壮：prefs 不可用时返回 False）"""
        try:
            if self.prefs is None:
                return False
            return bool(self.prefs.get("lsp_enabled", False))
        except Exception:
            return False

    def _set_lsp_checked(self, checked: bool):
        """设置 LSP 菜单勾选状态（阻断信号，避免递归）"""
        try:
            if not hasattr(self, "lsp_action"):
                return
            self.lsp_action.blockSignals(True)
            self.lsp_action.setChecked(checked)
            self.lsp_action.blockSignals(False)
        except Exception:
            pass

    def _connect_lsp_signals(self, proxy):
        """把编辑器代理的 LSP 信号接到状态栏（幂等）。

        P6 要求"失败必须用户可见"：EditorProxy 通过 `lsp_error` 信号
        发出人类可读的原因，主窗口负责显示 + 记日志。
        """
        if getattr(proxy, "_lsp_ui_connected", False):
            return
        connected = False
        for sig_name, slot in (
            ("lsp_error", self._on_lsp_message),
            ("lsp_status_changed", self._on_lsp_status),
            ("definition_requested", self._on_definition_requested),
            # B 阶段：LSP 其余能力的结果展示
            ("hover_text", self._on_lsp_hover_text),
            ("references_ready", self._on_lsp_references),
            ("rename_applied", self._on_lsp_rename_applied),
            ("symbols_ready", self._on_lsp_symbols),
            ("code_actions_ready", self._on_lsp_code_actions),
            ("formatting_applied", self._on_lsp_formatting_applied),
            ("signature_help", self._on_lsp_signature),
        ):
            try:
                sig = getattr(proxy, sig_name, None)
                if sig is not None:
                    sig.connect(slot)
                    connected = True
            except Exception as e:
                logger.debug("连接 %s 失败: %s", sig_name, e)
        if connected:
            try:
                proxy._lsp_ui_connected = True
            except Exception:
                pass

    def _on_lsp_message(self, message: str):
        """LSP 用户可见提示（失败原因 / 安装提示）"""
        try:
            logger.warning("[LSP] %s", message)
        except Exception:
            pass
        try:
            self.status_bar.showMessage(str(message), 8000)
        except Exception:
            pass

    def _on_lsp_status(self, state: str):
        """LSP 状态变化 → 状态栏"""
        try:
            text = {
                "running": "LSP 已启动",
                "off": "LSP 已停止",
                "error": "LSP 错误（详见日志）",
                "unsupported": "当前文件类型无 LSP 支持",
                "no_server": "未配置该语言的 LSP 服务器",
                "not_found": "未找到语言服务器，请先安装",
            }.get(str(state), f"LSP: {state}")
            self.status_bar.showMessage(text, 4000)
        except Exception:
            pass

    # --------------------------------------------------------
    # B 阶段：LSP 其余能力的结果展示（此前结果信号零 connect）
    # --------------------------------------------------------
    def _on_lsp_hover_text(self, text: str):
        """悬停信息 → 弹窗展示（内容可能较长，用信息框而非状态栏）"""
        try:
            self._show_info("悬停信息", text)
        except Exception as e:
            logger.debug("显示悬停信息失败: %s", e)

    def _on_lsp_references(self, items: list):
        """引用列表 → 文本弹窗（点击跳转留待后续）"""
        try:
            lines = []
            for it in items or []:
                path = it.get("path") or ""
                name = os.path.basename(path) if path else "(未知)"
                lines.append(
                    "%s:%d:%d"
                    % (
                        name,
                        int(it.get("line", 0)) + 1,
                        int(it.get("character", 0)) + 1,
                    )
                )
            if not lines:
                self.status_bar.showMessage("未找到引用", 4000)
                return
            self._show_info(
                "引用（%d 处）" % len(lines),
                "\n".join(lines),
            )
        except Exception as e:
            logger.debug("显示引用失败: %s", e)

    def _on_lsp_rename_applied(self, count: int):
        """重命名结果：目前只报告影响范围

        真正跨文件应用 WorkspaceEdit 涉及多文件原子写入，未在本轮范围内；
        这里明确告知用户"会影响多少处"，而不是假装已经改好。
        """
        try:
            self.status_bar.showMessage("重命名将影响 %d 处（跨文件应用尚未实现）" % count, 8000)
        except Exception:
            pass

    def _on_lsp_symbols(self, symbols: list):
        """文档符号 → 列表展示"""
        try:
            lines = []
            for s in symbols or []:
                indent = "  " * int(s.get("depth", 0) or 0)
                lines.append(
                    "%s%s  (行 %d)"
                    % (
                        indent,
                        s.get("name") or "",
                        int(s.get("line", 0)) + 1,
                    )
                )
            if not lines:
                self.status_bar.showMessage("未获取到文档符号", 4000)
                return
            self._show_info("文档符号（%d 项）" % len(lines), "\n".join(lines))
        except Exception as e:
            logger.debug("显示文档符号失败: %s", e)

    def _on_lsp_formatting_applied(self, ok: bool):
        try:
            self.status_bar.showMessage(
                "已应用 LSP 格式化" if ok else "无需格式化或未返回结果",
                4000,
            )
        except Exception:
            pass

    def _on_lsp_signature(self, label: str):
        try:
            self.status_bar.showMessage("签名: %s" % label, 8000)
        except Exception:
            pass

    # --------------------------------------------------------
    # B 阶段：LSP 其余能力的用户入口
    # --------------------------------------------------------
    def _with_proxy(self, method_name: str, what: str):
        """取得当前编辑器代理并调用其 LSP 方法（统一的前置检查）"""
        try:
            proxy = self.tabs.current_proxy()
            if not proxy or not hasattr(proxy, method_name):
                self.status_bar.showMessage("没有活动的编辑器", 3000)
                return None
            self._connect_lsp_signals(proxy)
            return proxy
        except Exception as e:
            logger.error("%s失败: %s", what, e)
            return None

    def _lsp_hover(self):
        proxy = self._with_proxy("hover_at_cursor", "悬停信息")
        if proxy is not None:
            proxy.hover_at_cursor()

    def _lsp_find_references(self):
        proxy = self._with_proxy("find_references", "查找引用")
        if proxy is not None:
            proxy.find_references()

    def _lsp_rename(self):
        proxy = self._with_proxy("rename_symbol", "重命名")
        if proxy is None:
            return
        from PyQt5.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "重命名符号", "新名称:")
        if ok and name:
            proxy.rename_symbol(name)

    def _lsp_document_symbols(self):
        proxy = self._with_proxy("document_symbols", "文档符号")
        if proxy is not None:
            proxy.document_symbols()

    def _lsp_format(self):
        proxy = self._with_proxy("format_document", "格式化")
        if proxy is not None:
            proxy.format_document()

    def _lsp_signature(self):
        proxy = self._with_proxy("request_signature", "签名帮助")
        if proxy is not None:
            proxy.request_signature()

    def _on_definition_requested(self, filepath: str, line: int, character: int):
        """P6: 定义位于**别的文件**时打开它。

        同一文件内的跳转由 `EditorProxy._on_lsp_definition` 直接完成，
        不会走到这里。
        """
        try:
            if not filepath:
                return
            current = ""
            proxy = self.tabs.current_proxy()
            if proxy is not None and getattr(proxy, "document", None) is not None:
                current = proxy.document.filepath or ""

            if os.path.normcase(filepath) == os.path.normcase(current):
                return

            if hasattr(self.tabs, "open_file"):
                self.tabs.open_file(filepath, line=line)
            else:
                self.status_bar.showMessage(f"定义位于: {filepath}:{line + 1}", 6000)
        except Exception as e:
            logger.error("打开定义位置失败: %s", e)

    def _paste_plain(self):
        """粘贴为纯文本（P8-3: Ctrl+Alt+Shift+V）。

        与 `_paste` 的区别：直接插入系统剪贴板的纯文本，不经过
        QScintilla 的富文本/多光标粘贴路径。``insert()`` 在有选区时
        替换选区、无选区时插入。
        """
        try:
            proxy = self.tabs.current_proxy()
            if not proxy or not getattr(proxy, "sc", None):
                self.status_bar.showMessage("没有活动的编辑器", 3000)
                return
            text = QApplication.clipboard().text()
            if not text:
                self.status_bar.showMessage("剪贴板为空", 3000)
                return
            proxy.sc.insert(text)
            self.status_bar.showMessage("已粘贴为纯文本", 2000)
        except Exception as e:
            logger.error("粘贴为纯文本失败: %s", e)
            try:
                self.status_bar.showMessage(f"粘贴失败: {e}", 4000)
            except Exception:
                pass

    def _insert_datetime(self):
        """插入日期时间（P7/P8: 统一走 EditorProxy，格式来自 Preferences）。

        这里**覆盖**了 `EditOpsMixin._insert_datetime`
        （ui/mixins/edit_ops_mixin.py:139）—— 那份实现把格式硬编码为
        ``"%Y-%m-%d %H:%M:%S"``，**完全不读** Preferences 的
        ``date_format`` / ``time_format``，用户在首选项里改了没反应。

        `core/editor.py::insert_datetime` 是唯一读取这两个键的实现，
        编辑器的右键菜单（ui/editor_view.py:1535）已经在用它。此处把
        **编辑菜单** 也统一到同一条路径，避免两份实现再次漂移。
        """
        try:
            proxy = self.tabs.current_proxy()
            if proxy is None:
                self.status_bar.showMessage("没有活动的编辑器", 3000)
                return
            if hasattr(proxy, "insert_datetime"):
                proxy.insert_datetime()
                return
            # 兜底：代理缺该方法时退回 mixin 的历史实现
            super()._insert_datetime()
        except Exception as e:
            logger.error("插入日期时间失败: %s", e)
            try:
                self.status_bar.showMessage(f"插入日期时间失败: {e}", 4000)
            except Exception:
                pass

    def _toggle_lsp(self, checked: bool):
        """P6: 启用/停用当前编辑器的 LSP（工具菜单可勾选项）。

        - 默认关闭：大多数用户本机没有语言服务器。
        - **失败必须用户可见**：具体原因通过 `lsp_error` 信号进入
          状态栏（`_on_lsp_message`），并写入日志。
        - 失败时回滚勾选状态，避免菜单显示"已启用"但实际未生效。
        """
        try:
            proxy = self.tabs.current_proxy()
            if proxy is None or not hasattr(proxy, "toggle_lsp"):
                self.status_bar.showMessage("没有活动的编辑器，无法启用 LSP", 4000)
                self._set_lsp_checked(False)
                return

            self._connect_lsp_signals(proxy)

            if checked:
                ok = bool(proxy.toggle_lsp(True))
                if not ok:
                    # EditorProxy 已经通过 lsp_error 给出具体原因
                    self._set_lsp_checked(False)
                    return
                filepath = ""
                if getattr(proxy, "document", None) is not None:
                    filepath = proxy.document.filepath or ""
                if filepath:
                    self._lsp_clients[filepath] = proxy
            else:
                proxy.toggle_lsp(False)
                stale = [k for k, v in self._lsp_clients.items() if v is proxy]
                for k in stale:
                    self._lsp_clients.pop(k, None)

            if self.prefs is not None:
                try:
                    self.prefs.set("lsp_enabled", bool(checked))
                except Exception:
                    pass
        except Exception as e:
            logger.error("切换 LSP 失败: %s", e)
            self._set_lsp_checked(False)
            try:
                self.status_bar.showMessage(f"切换 LSP 失败: {e}", 5000)
            except Exception:
                pass
