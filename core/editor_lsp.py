# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""LSP 集成职责（v2.24 拆出）。"""
from core.editor_common import *  # noqa: F401,F403,F405
from core.editor_common import _EOL_SPLIT_RE, _normalize_bytes  # noqa: F401


class EditorLspMixin:
    def _lsp_language_id(self) -> str:
        """根据文件扩展名推断 LSP languageId"""
        path = self.document.filepath or ""
        ext = os.path.splitext(path)[1].lower()
        return LSP_LANGUAGE_BY_EXT.get(ext, "plaintext")

    def _sync_lsp_document(self):
        """把编辑器当前全文同步给语言服务器（didChange 全量）。

        修复说明（P0-2）:
            原实现只在 toggle_lsp 里发一次 did_open，之后**从不**
            调用 did_change / did_save，语言服务器永远停留在
            打开时的快照，补全与诊断都是过期的。
        """
        if not (self.lsp_active and self.lsp_client):
            return
        try:
            self.lsp_client.did_change(
                self._lsp_uri or LspClient.path_to_uri(self.document.filepath or ""),
                self.sc.text(),
            )
        except Exception as e:
            print(f"[EditorProxy] LSP 同步失败: {e}")

    def _notify_lsp_saved(self, filepath: Optional[str] = None):
        """通知语言服务器文件已保存（didSave）"""
        if not (self.lsp_active and self.lsp_client):
            return
        try:
            uri = self._lsp_uri or LspClient.path_to_uri(filepath or self.document.filepath or "")
            self.lsp_client.did_save(uri, self.sc.text())
        except Exception as e:
            print(f"[EditorProxy] LSP didSave 失败: {e}")

    def toggle_lsp(self, enable: bool) -> bool:
        """
        启用/禁用 LSP。

        参数:
            enable: True 启用，False 禁用

        返回:
            是否成功

        P6 修复（三个已核实的缺陷）:
            1. 原实现调用 LspClient 的 ``start()`` 时**零参数**；而
               :meth:`LspClient.start` 的 ``command`` 是**必填位置参数**，
               必然 TypeError，又被外层 ``except Exception`` 吞掉，
               LSP 从未真正启动过。现在从 :class:`LspServerRegistry`
               按语言取 command，并传 working_dir。
            2. 原实现硬编码 ``ext not in ('.py', '.pyw') → return False``，
               与模块级 ``LSP_LANGUAGE_BY_EXT``（20+ 种语言）自相矛盾。
               现在统一用 ``lsp_language_for_file()`` 判断支持性。
            3. 失败原因必须**用户可见**：通过 ``lsp_error`` 信号送出，
               由主窗口显示在状态栏并写日志，不再只 print。
        """
        try:
            if enable and not self.lsp_client:
                filepath = self.document.filepath or ""
                if not filepath:
                    self.lsp_status_changed.emit("unsupported")
                    self._report_lsp_error("无法启用 LSP：请先保存当前文件（未保存的文件没有路径）")
                    return False

                # P6: 用 LSP_LANGUAGE_BY_EXT 取代硬编码的 .py/.pyw 判断
                language = lsp_language_for_file(filepath)
                if not language:
                    ext = os.path.splitext(filepath)[1].lower() or "(无扩展名)"
                    self.lsp_status_changed.emit("unsupported")
                    self._report_lsp_error(f"无法启用 LSP：暂不支持 {ext} 类型的文件")
                    return False

                server_language = lsp_server_language_for_file(filepath)
                command = None
                if server_language:
                    try:
                        command = LspServerRegistry.get_command(server_language)
                    except Exception:
                        command = None
                if not command:
                    self.lsp_status_changed.emit("no_server")
                    self._report_lsp_error(f"无法启用 LSP：{language} 暂无内置的语言服务器配置")
                    return False

                # 服务器可执行文件缺失时给出**具体、可操作**的提示
                if not lsp_command_available(command):
                    self.lsp_status_changed.emit("not_found")
                    self._report_lsp_error(
                        f"未找到语言服务器 {command[0]}，请先安装："
                        f"{lsp_install_hint(server_language)}"
                    )
                    return False

                self.lsp_client = LspClient()
                self.lsp_client.diagnostics_updated.connect(self._on_lsp_diagnostics)
                self.lsp_client.completion_ready.connect(self._on_lsp_completion)
                # P6: 服务器自身的错误也要让用户看到（附安装提示）
                self.lsp_client.error_occurred.connect(self._on_lsp_client_error)
                # P6: request_definition 的结果回调
                self.lsp_client.definition_ready.connect(self._on_lsp_definition)
                # LSP 其余能力的结果回调（B 阶段接线）
                # 这些信号在 LspClient 里本就存在，但此前**全仓零 connect**，
                # 于是 request_hover/references/rename/document_symbols/
                # code_actions/formatting/signature_help 虽然实现了却永远
                # 不会有结果回到宿主 —— 属于"写好了没接线"。
                self.lsp_client.hover_ready.connect(self._on_lsp_hover)
                self.lsp_client.references_ready.connect(self._on_lsp_references)
                self.lsp_client.rename_ready.connect(self._on_lsp_rename)
                self.lsp_client.document_symbols_ready.connect(self._on_lsp_symbols)
                self.lsp_client.code_actions_ready.connect(self._on_lsp_code_actions)
                self.lsp_client.formatting_ready.connect(self._on_lsp_formatting)
                self.lsp_client.signature_help_ready.connect(self._on_lsp_signature)
                self._lsp_server_language = server_language

                # P6: 修 start() 调用 —— 传 command + working_dir
                working_dir = os.path.dirname(filepath) or os.getcwd()
                self.lsp_client.start(list(command), working_dir=working_dir)

                # 初始化
                # P0-2 修复：URI 用 path_to_uri 生成（正确 URL 编码），
                # 不再手工拼接；root_uri 为文件所在目录的 URI。
                uri = LspClient.path_to_uri(self.document.filepath)
                root_uri = LspClient.path_to_uri(os.path.dirname(self.document.filepath))
                self.lsp_client.initialize(root_uri)
                # P0-2 修复：原为 did_open(uri, self.sc.text())，
                # 参数错位（language_id 收到全文、text 缺失、
                # version=None），导致后续 did_change 抛
                # TypeError 且 LSP 静默失效。
                self.lsp_client.did_open(
                    uri,
                    self._lsp_language_id(),
                    self.sc.text(),
                )
                self._lsp_uri = uri

                self.lsp_active = True
                self.lsp_status_changed.emit("running")
                return True

            elif not enable and self.lsp_client:
                # P0-2: 关闭前先通知服务端并停掉待发的同步
                try:
                    if self._lsp_uri:
                        self.lsp_client.did_close(self._lsp_uri)
                except Exception:
                    pass
                self._lsp_sync_timer.stop()
                self.lsp_client.stop()
                self.lsp_client = None
                self.lsp_active = False
                self._lsp_uri = ""
                self._lsp_server_language = None
                self.lsp_status_changed.emit("off")
                return True

            return False

        except Exception as e:
            logger.error("[EditorProxy] 切换 LSP 失败: %s", e)
            self._report_lsp_error(f"切换 LSP 失败: {e}")
            self.lsp_status_changed.emit("error")
            return False

    def _report_lsp_error(self, message: str):
        """P6: LSP 的失败/提示必须**用户可见**。

        同时做两件事（刻意不只 print）：
            1. 写 logging（进入日志文件）；
            2. 发 ``lsp_error`` 信号 —— 主窗口接到后显示在状态栏
               （见 ui/main_window.py::_on_lsp_message）。
        """
        try:
            logger.warning("[EditorProxy][LSP] %s", message)
        except Exception:
            pass
        try:
            self.lsp_error.emit(str(message))
        except Exception:
            pass

    def _on_lsp_client_error(self, message: str):
        """P6: 语言服务器自身的错误 → 附上安装提示后交给用户。"""
        try:
            hint = lsp_install_hint(getattr(self, "_lsp_server_language", None))
            text = str(message)
            if hint:
                text = f"{text}（可尝试：{hint}）"
            self._report_lsp_error(text)
        except Exception as e:
            logger.error("[EditorProxy] 处理 LSP 错误失败: %s", e)
        # 启动阶段就失败时，不要留下半死的客户端
        if not self.lsp_active and self.lsp_client is not None:
            try:
                self.lsp_client.stop()
            except Exception:
                pass
            self.lsp_client = None

    def _lsp_ready(self, what: str) -> bool:
        """LSP 请求的前置检查（不满足时给出**用户可见**提示）

        返回是否可以直接发起请求。
        """
        if not (self.lsp_active and self.lsp_client and self._lsp_uri):
            self._report_lsp_error("%s需要先启用 LSP：工具 → 启用 LSP（智能补全）" % what)
            return False
        return True

    def goto_definition(self) -> bool:
        """P6: 转到定义（F12）。

        这是 :meth:`LspClient.request_definition` 的**生产调用点**
        （此前该方法零调用方）。结果由 ``_on_lsp_definition`` 处理：
        同一文件内直接跳转，其它文件通过 ``definition_requested``
        信号交给主窗口打开。

        返回:
            请求是否已发出
        """
        if not (self.lsp_active and self.lsp_client and self._lsp_uri):
            self._report_lsp_error("转到定义需要先启用 LSP：工具 → 启用 LSP（智能补全）")
            return False
        try:
            line, col = self.sc.getCursorPosition()
            self.lsp_client.request_definition(self._lsp_uri, line, col)
            return True
        except Exception as e:
            logger.error("[EditorProxy] 请求转到定义失败: %s", e)
            self._report_lsp_error(f"转到定义失败: {e}")
            return False

    def _on_lsp_definition(self, result):
        """P6: LSP 转到定义结果 → 跳转（或请求主窗口打开目标文件）。"""
        try:
            if not result:
                self._report_lsp_error("未找到定义")
                return

            locations = result if isinstance(result, list) else [result]
            target = locations[0] if locations else None
            if not isinstance(target, dict):
                self._report_lsp_error("未找到定义")
                return

            uri = target.get("uri") or ""
            start = (target.get("range") or {}).get("start") or {}
            line = int(start.get("line", 0) or 0)
            character = int(start.get("character", 0) or 0)
            path = LspClient.uri_to_path(uri) if uri else ""

            current = self.document.filepath or ""
            if path and os.path.normcase(path) != os.path.normcase(current):
                # 定义在别的文件：交给主窗口打开
                self.definition_requested.emit(path, line, character)
                return

            pos = self._lsp_pos_to_scintilla(line, character)
            if pos < 0:
                self._report_lsp_error("定义位置无效，无法跳转")
                return
            self.sc.SendScintilla(QsciScintilla.SCI_GOTOPOS, pos)
            self.sc.ensureLineVisible(line)
        except Exception as e:
            logger.error("[EditorProxy] 处理转到定义结果失败: %s", e)

    # --------------------------------------------------------
    # LSP 其余能力（B 阶段接线：此前请求方法有实现、结果信号零 connect）
    # --------------------------------------------------------

    def _cursor_lsp_pos(self):
        """当前光标的 (line, character)"""
        line, col = self.sc.getCursorPosition()
        return line, col

    def hover_at_cursor(self) -> bool:
        """悬停信息（把结果文本通过 `hover_text` 交给宿主显示）"""
        if not self._lsp_ready("查看悬停信息"):
            return False
        try:
            line, col = self._cursor_lsp_pos()
            self.lsp_client.request_hover(self._lsp_uri, line, col)
            return True
        except Exception as e:
            self._report_lsp_error(f"悬停请求失败: {e}")
            return False

    def _on_lsp_hover(self, result):
        """悬停结果 → 提取纯文本"""
        try:
            if not result:
                self._report_lsp_error("此处没有可用信息")
                return
            contents = result.get("contents")
            text = ""
            if isinstance(contents, dict):
                text = contents.get("value") or ""
            elif isinstance(contents, list):
                parts = []
                for item in contents:
                    if isinstance(item, dict):
                        parts.append(item.get("value") or "")
                    else:
                        parts.append(str(item))
                text = "\n".join(p for p in parts if p)
            else:
                text = str(contents or "")
            text = text.strip()
            if not text:
                self._report_lsp_error("此处没有可用信息")
                return
            self.hover_text.emit(text)
        except Exception as e:
            logger.error("[EditorProxy] 处理悬停结果失败: %s", e)

    def find_references(self) -> bool:
        """查找引用（结果通过 `references_ready` 交给宿主列表显示）"""
        if not self._lsp_ready("查找引用"):
            return False
        try:
            line, col = self._cursor_lsp_pos()
            self.lsp_client.request_references(self._lsp_uri, line, col, include_declaration=True)
            return True
        except Exception as e:
            self._report_lsp_error(f"查找引用失败: {e}")
            return False

    def _on_lsp_references(self, result):
        try:
            items = []
            for loc in result or []:
                if not isinstance(loc, dict):
                    continue
                uri = loc.get("uri") or ""
                start = (loc.get("range") or {}).get("start") or {}
                items.append(
                    {
                        "path": LspClient.uri_to_path(uri) if uri else "",
                        "line": int(start.get("line", 0) or 0),
                        "character": int(start.get("character", 0) or 0),
                    }
                )
            if not items:
                self._report_lsp_error("未找到引用")
                return
            self.references_ready.emit(items)
        except Exception as e:
            logger.error("[EditorProxy] 处理引用结果失败: %s", e)

    def rename_symbol(self, new_name: str) -> bool:
        """重命名符号（返回影响的位置数由 `rename_applied` 通知）"""
        if not new_name:
            self._report_lsp_error("重命名需要提供新名称")
            return False
        if not self._lsp_ready("重命名"):
            return False
        try:
            line, col = self._cursor_lsp_pos()
            self.lsp_client.request_rename(self._lsp_uri, line, col, new_name)
            return True
        except Exception as e:
            self._report_lsp_error(f"重命名失败: {e}")
            return False

    def _on_lsp_rename(self, result):
        """重命名结果：统计将被改动的位置数

        注意：这里**只统计并报告**，不直接改写文件 —— 跨文件应用
        WorkspaceEdit 涉及多文件原子写入，超出本次范围；宿主可据此提示
        用户（"将影响 N 处"）并决定后续动作。
        """
        try:
            if not result:
                self._report_lsp_error("重命名未返回结果")
                return
            changes = result.get("changes") or {}
            count = 0
            if isinstance(changes, dict):
                for edits in changes.values():
                    count += len(edits or [])
            else:
                for doc_edit in result.get("documentChanges") or []:
                    if isinstance(doc_edit, dict):
                        count += len(doc_edit.get("edits") or [])
            self.rename_applied.emit(count)
        except Exception as e:
            logger.error("[EditorProxy] 处理重命名结果失败: %s", e)

    def document_symbols(self) -> bool:
        """请求文档符号（结果通过 `symbols_ready` 交给宿主）"""
        if not self._lsp_ready("获取文档符号"):
            return False
        try:
            self.lsp_client.request_document_symbols(self._lsp_uri)
            return True
        except Exception as e:
            self._report_lsp_error(f"获取文档符号失败: {e}")
            return False

    def _on_lsp_symbols(self, result):
        try:
            symbols = []

            def walk(items, depth=0):
                for it in items or []:
                    if not isinstance(it, dict):
                        continue
                    name = it.get("name") or ""
                    rng = it.get("range") or it.get("location", {}).get("range") or {}
                    start = (rng or {}).get("start") or {}
                    if name:
                        symbols.append(
                            {
                                "name": name,
                                "kind": it.get("kind", 0),
                                "line": int(start.get("line", 0) or 0),
                                "character": int(start.get("character", 0) or 0),
                                "depth": depth,
                            }
                        )
                    children = it.get("children")
                    if children:
                        walk(children, depth + 1)

            walk(result or [])
            if not symbols:
                self._report_lsp_error("未获取到文档符号")
                return
            self.symbols_ready.emit(symbols)
        except Exception as e:
            logger.error("[EditorProxy] 处理文档符号失败: %s", e)

    def code_actions(self) -> bool:
        """请求代码操作（结果通过 `code_actions_ready` 交给宿主选择）"""
        if not self._lsp_ready("获取代码操作"):
            return False
        try:
            line, col = self._cursor_lsp_pos()
            rng = {
                "start": {"line": line, "character": 0},
                "end": {"line": line, "character": col},
            }
            # context 是 LSP 规范里的必填字段（diagnostics 可为空列表）
            self.lsp_client.request_code_actions(self._lsp_uri, rng, {"diagnostics": []})
            return True
        except Exception as e:
            self._report_lsp_error(f"获取代码操作失败: {e}")
            return False

    def _on_lsp_code_actions(self, result):
        try:
            actions = []
            for a in result or []:
                if not isinstance(a, dict):
                    continue
                title = a.get("title") or ""
                if title:
                    actions.append({"title": title, "raw": a})
            if not actions:
                self._report_lsp_error("此处没有可用的代码操作")
                return
            self.code_actions_ready.emit(actions)
        except Exception as e:
            logger.error("[EditorProxy] 处理代码操作失败: %s", e)

    def format_document(self) -> bool:
        """请求格式化文档（结果通过 `formatting_applied` 通知）"""
        if not self._lsp_ready("格式化文档"):
            return False
        try:
            prefs = self._prefs()
            tab_size = 4
            insert_spaces = True
            if prefs is not None:
                try:
                    tab_size = int(prefs.get("indent_size", 4) or 4)
                    insert_spaces = not bool(prefs.get("indent_use_tabs", False))
                except Exception:
                    pass
            options = {
                "tabSize": max(1, tab_size),
                "insertSpaces": insert_spaces,
            }
            self.lsp_client.request_formatting(self._lsp_uri, options)
            return True
        except Exception as e:
            self._report_lsp_error(f"格式化请求失败: {e}")
            return False

    def _on_lsp_formatting(self, result):
        """格式化结果：就地应用文本编辑（单文件内）"""
        try:
            if not result:
                self._report_lsp_error("无需格式化或未返回结果")
                self.formatting_applied.emit(False)
                return
            applied = 0
            for edit in result:
                if not isinstance(edit, dict):
                    continue
                rng = edit.get("range") or {}
                start = rng.get("start") or {}
                end = rng.get("end") or {}
                start_pos = self._lsp_pos_to_scintilla(
                    int(start.get("line", 0) or 0),
                    int(start.get("character", 0) or 0),
                )
                end_pos = self._lsp_pos_to_scintilla(
                    int(end.get("line", 0) or 0),
                    int(end.get("character", 0) or 0),
                )
                if start_pos < 0 or end_pos < 0:
                    continue
                data = _normalize_bytes(edit.get("newText") or "")
                self.sc.SendScintilla(QsciScintilla.SCI_SETTARGETSTART, start_pos)
                self.sc.SendScintilla(QsciScintilla.SCI_SETTARGETEND, end_pos)
                self.sc.SendScintilla(QsciScintilla.SCI_REPLACETARGETRE, len(data), data)
                applied += 1
            self.formatting_applied.emit(applied > 0)
            if applied:
                self.modified_changed.emit(True)
        except Exception as e:
            logger.error("[EditorProxy] 应用格式化结果失败: %s", e)
            self.formatting_applied.emit(False)

    def request_signature(self) -> bool:
        """请求签名帮助（结果通过 `signature_help` 信号交给宿主）

        命名说明：方法名刻意不叫 `signature_help` —— 本类已有同名**信号**
        `signature_help`，同名会覆盖信号（ruff F811 / 运行时属性冲突）。
        """
        if not self._lsp_ready("签名帮助"):
            return False
        try:
            line, col = self._cursor_lsp_pos()
            self.lsp_client.request_signature_help(self._lsp_uri, line, col)
            return True
        except Exception as e:
            self._report_lsp_error(f"签名帮助请求失败: {e}")
            return False

    def _on_lsp_signature(self, result):
        try:
            if not result:
                self._report_lsp_error("此处没有签名信息")
                return
            sigs = result.get("signatures") or []
            if not sigs:
                self._report_lsp_error("此处没有签名信息")
                return
            active = result.get("activeSignature", 0) or 0
            idx = active if 0 <= active < len(sigs) else 0
            label = ""
            if isinstance(sigs[idx], dict):
                label = sigs[idx].get("label") or ""
            if not label and isinstance(sigs[0], dict):
                label = sigs[0].get("label") or ""
            if not label:
                self._report_lsp_error("此处没有签名信息")
                return
            self.signature_help.emit(label)
        except Exception as e:
            logger.error("[EditorProxy] 处理签名帮助失败: %s", e)

    def _lsp_pos_to_scintilla(self, line: int, character: int) -> int:
        """LSP position → Scintilla 字节偏移

        P3-4: LSP 的 character 是 UTF-16 code unit 偏移，
        SCI_FINDCOLUMN 期望的是"视觉列"，两者对 emoji /
        4 字节 CJK 扩展字符不一致。

        改用：字符偏移 → UTF-8 字节偏移 + 行起始位置。
        （简化：假设 BMP 字符，不处理代理对；对 4 字节 CJK
          扩展字符会略有偏差，但远好于原实现。）
        """
        try:
            if line < 0 or character < 0:
                return -1
            line_text = self.sc.text(line)
            prefix = line_text[:character]
            byte_offset = len(prefix.encode("utf-8", errors="replace"))
            line_start = self.sc.SendScintilla(QsciScintilla.SCI_POSITIONFROMLINE, line)
            if line_start < 0:
                return -1
            return line_start + byte_offset
        except Exception:
            return -1

    def _on_lsp_diagnostics(self, uri: str, diagnostics: List[Dict]):
        """LSP 诊断结果回调

        修复（INV-L2，审计测试复现的跨标签状态泄漏）：
            原实现**不比较 uri 与 self._lsp_uri**，任何来源的诊断都会被
            画到当前编辑器上 —— 这是"标签 A 的诊断出现在标签 B"的通道。
            一个语言服务器可能同时服务多个文件（或收到已关闭文件的迟到
            诊断），脏数据就会污染当前视图。

            现在先做 URI 归属检查：不匹配则直接忽略。
        """
        try:
            # 只接受属于本编辑器当前文档的诊断
            if not uri or not self._lsp_uri or uri != self._lsp_uri:
                logger.debug(
                    "忽略非本文件的 LSP 诊断: uri=%r 当前=%r",
                    uri,
                    self._lsp_uri,
                )
                return

            # 清除旧诊断
            length = self.sc.SendScintilla(QsciScintilla.SCI_GETLENGTH)
            self.sc.SendScintilla(QsciScintilla.SCI_SETINDICATORCURRENT, INDICATOR_LSP_ERROR)
            self.sc.SendScintilla(QsciScintilla.SCI_INDICATORCLEARRANGE, 0, length)

            # 绘制新诊断
            for diag in diagnostics:
                try:
                    start_line = diag["range"]["start"]["line"]
                    start_char = diag["range"]["start"]["character"]
                    end_line = diag["range"]["end"]["line"]
                    end_char = diag["range"]["end"]["character"]

                    # P3-4: LSP character 是 UTF-16 code unit 偏移，
                    # 用 _lsp_pos_to_scintilla 转成字节偏移
                    start = self._lsp_pos_to_scintilla(start_line, start_char)
                    end = self._lsp_pos_to_scintilla(end_line, end_char)

                    if start < 0 or end < 0:
                        continue

                    self.sc.SendScintilla(
                        QsciScintilla.SCI_SETINDICATORCURRENT, INDICATOR_LSP_ERROR
                    )
                    self.sc.SendScintilla(
                        QsciScintilla.SCI_INDICATORFILLRANGE, start, max(1, end - start)
                    )
                except Exception:
                    continue

            # 同步到全局问题管理器 → 问题面板
            #
            # 修复（生产者缺口，已核实）：
            #   `core/problems.py` 的 `ProblemManager.set_file_problems()`
            #   **全仓零调用** —— 于是 `ui/problems_panel.py` 虽然实现了
            #   完整 UI，挂上去也永远是空白（消费者有了、生产者没有）。
            #   诊断此前只画成 Scintilla 指示器，用户无法列表查看。
            self._publish_problems(uri, diagnostics)

        except Exception as e:
            print(f"[EditorProxy] 处理诊断失败: {e}")

    def _publish_problems(self, uri: str, diagnostics: List[Dict]):
        """把 LSP 诊断写入全局 ProblemManager（供问题面板显示）"""
        try:
            from core.problems import Problem, get_problem_manager
        except Exception:
            return
        try:
            path = ""
            try:
                path = getattr(self.document, "filepath", "") or ""
            except Exception:
                path = ""
            if not path:
                # 未保存文件：用 URI 作为键，至少能在面板里列出
                path = uri or ""

            # LSP severity: 1=Error 2=Warning 3=Information 4=Hint
            sev_map = {1: "error", 2: "warning", 3: "info", 4: "hint"}

            problems = []
            for d in diagnostics or []:
                try:
                    rng = d.get("range") or {}
                    st = rng.get("start") or {}
                    en = rng.get("end") or {}
                    code = d.get("code")
                    problems.append(
                        Problem(
                            filepath=path,
                            line=int(st.get("line", 0)),
                            col=int(st.get("character", 0)),
                            severity=sev_map.get(d.get("severity"), "info"),
                            message=str(d.get("message") or ""),
                            source=str(d.get("source") or "lsp"),
                            code="" if code is None else str(code),
                            end_line=int(en.get("line", 0)),
                            end_col=int(en.get("character", 0)),
                        )
                    )
                except Exception:
                    continue

            get_problem_manager().set_file_problems(path, problems)
        except Exception as e:
            logger.debug("发布诊断到问题管理器失败: %s", e)

    def _on_lsp_completion(self, items: List[Dict]):
        """LSP 补全结果回调"""
        try:
            if not items:
                return

            # 构建补全列表
            words = [item.get("label", "") for item in items[:50]]
            words = [w for w in words if w]

            if words:
                text = " ".join(words)
                self.sc.SendScintilla(QsciScintilla.SCI_AUTOCSHOW, 0, text.encode("utf-8"))

        except Exception as e:
            print(f"[EditorProxy] 处理补全失败: {e}")

    def request_completion(self):
        """请求 LSP 补全"""
        if not self.lsp_client or not self.document.filepath:
            return

        try:
            line, col = self.sc.getCursorPosition()
            uri = "file:///" + self.document.filepath.replace("\\", "/")
            self.lsp_client.request_completion(uri, line, col)
        except Exception as e:
            print(f"[EditorProxy] 请求补全失败: {e}")

    # ========================================================
    # 关闭
    # ========================================================
