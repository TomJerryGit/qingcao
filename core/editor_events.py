# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""事件与标记初始化职责（v2.24 拆出）。"""
from core.editor_common import *  # noqa: F401,F403,F405
from core.editor_common import _EOL_SPLIT_RE, _normalize_bytes  # noqa: F401


class EditorEventsMixin:
    def _init_indicators(self):
        """初始化指示器"""
        try:
            # 搜索高亮（黄色半透明）
            self.sc.indicatorDefine(QsciScintilla.INDIC_STRAIGHTBOX, INDICATOR_SEARCH)
            self.sc.setIndicatorForegroundColor(QColor(255, 255, 0, 120), INDICATOR_SEARCH)
            self.sc.setIndicatorOutlineColor(QColor(255, 200, 0), INDICATOR_SEARCH)

            # 当前匹配（橙色）
            self.sc.indicatorDefine(QsciScintilla.INDIC_ROUNDBOX, INDICATOR_CURRENT_MATCH)
            self.sc.setIndicatorForegroundColor(QColor(255, 128, 0, 180), INDICATOR_CURRENT_MATCH)

            # LSP 错误（红色波浪线）
            self.sc.indicatorDefine(QsciScintilla.INDIC_SQUIGGLE, INDICATOR_LSP_ERROR)
            self.sc.setIndicatorForegroundColor(QColor(255, 0, 0), INDICATOR_LSP_ERROR)

            # 智能高亮（灰色）
            self.sc.indicatorDefine(QsciScintilla.INDIC_STRAIGHTBOX, INDICATOR_SMART_HIGHLIGHT)
            self.sc.setIndicatorForegroundColor(
                QColor(100, 100, 100, 60), INDICATOR_SMART_HIGHLIGHT
            )

            # 光标拖尾（淡黄）
            self.sc.indicatorDefine(QsciScintilla.INDIC_STRAIGHTBOX, INDICATOR_CURSOR_TRAIL)
            self.sc.setIndicatorForegroundColor(QColor(255, 255, 0, 80), INDICATOR_CURSOR_TRAIL)

            # 代码片段占位符（蓝色）
            self.sc.indicatorDefine(QsciScintilla.INDIC_STRAIGHTBOX, INDICATOR_SNIPPET)
            self.sc.setIndicatorForegroundColor(QColor(0, 120, 215, 100), INDICATOR_SNIPPET)

        except Exception as e:
            print(f"[EditorProxy] 初始化指示器失败: {e}")

    def _init_markers(self):
        """初始化书签和 Git 标记"""
        try:
            # 书签
            self.sc.markerDefine(QsciScintilla.Circle, MARKER_BOOKMARK)
            self.sc.setMarkerBackgroundColor(QColor("#007acc"), MARKER_BOOKMARK)

            # Git 标记（用背景色标出）
            self.sc.markerDefine(QsciScintilla.Background, MARKER_GIT_ADDED)
            self.sc.setMarkerBackgroundColor(QColor(0, 255, 0, 30), MARKER_GIT_ADDED)

            self.sc.markerDefine(QsciScintilla.Background, MARKER_GIT_MODIFIED)
            self.sc.setMarkerBackgroundColor(QColor(0, 120, 215, 30), MARKER_GIT_MODIFIED)

            self.sc.markerDefine(QsciScintilla.Background, MARKER_GIT_DELETED)
            self.sc.setMarkerBackgroundColor(QColor(255, 0, 0, 30), MARKER_GIT_DELETED)

            # 断点
            self.sc.markerDefine(QsciScintilla.Circle, MARKER_BREAKPOINT)
            self.sc.setMarkerBackgroundColor(QColor("#ff0000"), MARKER_BREAKPOINT)

        except Exception as e:
            print(f"[EditorProxy] 初始化标记失败: {e}")

    def _connect_signals(self):
        """连接 QScintilla 的信号"""
        try:
            self.sc.SCN_MODIFIED.connect(self._on_scintilla_modified)
            self.sc.modificationChanged.connect(self._on_modification_changed)
            self.sc.cursorPositionChanged.connect(self._on_cursor_changed)
            self.sc.selectionChanged.connect(self._on_selection_changed)

            # 禁用内置撤销栈
            self.sc.SendScintilla(QsciScintilla.SCI_EMPTYUNDOBUFFER)
            self.sc.SendScintilla(QsciScintilla.SCI_SETUNDOCOLLECTION, 0)

        except Exception as e:
            print(f"[EditorProxy] 连接信号失败: {e}")

        # 外部文件变更 → 转发给宿主（接线修复）
        #
        # 缺陷背景：`Document.external_change_detected` 会 emit，但全仓
        # 零 connect —— 文件被外部程序修改时信号无人接收，用户下次保存
        # 就会**静默覆盖别人的修改**。宿主 app/tabs.py 另有一条 watcher
        # 路径可以弹提示，但那条依赖文件系统通知；Document 侧的 mtime
        # 检查正是 watcher 丢事件时的兜底。
        try:
            if getattr(self, "document", None) is not None:
                self.document.external_change_detected.connect(self._on_external_change)
        except Exception as e:
            logger.warning("连接外部变更信号失败: %s", e)

        # 文档被重新加载（换编码 / 外部改动重载）→ 刷新编辑器文本
        #
        # `Document.reload()` / `change_encoding()` 都会 emit `reloaded`，
        # 但原先全仓零 connect → 编辑器继续显示旧编码解出的乱码，
        # 而 provider 已是正确文本。见 `_on_document_reloaded` 的说明。
        try:
            if getattr(self, "document", None) is not None:
                self.document.reloaded.connect(self._on_document_reloaded)
        except Exception as e:
            logger.warning("连接文档重载信号失败: %s", e)

        # 文档路径变化（另存为）→ 更新 LSP 文档 URI
        #
        # 由 Document 统一广播（`filepath_changed`），因此**无论从哪个入口**
        # 另存为都正确：`EditorProxy.save_file(path)`、`Document.save(path)`、
        # 以及将来新增的入口。原先没有通知机制，只能在具体入口里手动补。
        try:
            if getattr(self, "document", None) is not None:
                self.document.filepath_changed.connect(self._on_document_filepath_changed)
        except Exception as e:
            logger.warning("连接路径变化信号失败: %s", e)

    def _on_external_change(self, path: str):
        """文件被外部修改时的兜底处理。

        只做"记日志 + 转发信号"：真正的重载/提示决策交给宿主
        （`app/tabs.py` 已有带对话框的处理路径）。EditorProxy 属于 core
        层，不应该直接弹 QMessageBox。
        """
        logger.warning("检测到外部文件变更: %s", path)
        try:
            self.external_change_detected.emit(path)
        except Exception:
            pass

    # ========================================================
    # 词法器
    # ========================================================

    def _apply_lexer(self, filepath: Optional[str]):
        """根据文件扩展名应用语法高亮。

        P8/P5 清理（重复副本）:
            本方法此前与 ``ui/editor_view.py`` 中
            ``EditorWidget.set_lexer_by_filename()`` 是同一逻辑的两份
            副本，而且已经漂移 —— ui 侧由 P5 扩展到了 30+ 种语言的
            映射表（``LEXER_BY_EXTENSION``），core 侧只剩下
            .py/.c/.log 三个分支。

            权威实现是 **ui/editor_view.py**（见其中的 docstring）。
            core 这里不再维护第二份映射表，直接委托给控件自身的
            ``set_lexer_by_filename()``：它会按"插件注册表 → .log 专用
            → 内置映射表 → 无高亮"的优先级处理，并顺带设置字体。

            控件未实现该方法（例如裸 QsciScintilla）时退化为清空
            词法器 —— 宁可没有高亮，也不要在这里复活第二份映射表。
        """
        setter = getattr(self.sc, "set_lexer_by_filename", None)
        if callable(setter):
            try:
                setter(filepath)
                return
            except Exception as e:
                print(f"[EditorProxy] 应用词法器失败: {e}")
        try:
            self.sc.setLexer(None)
        except Exception:
            pass

    def _detect_indent(self):
        """检测缩进风格"""
        try:
            text = self.sc.text()
            lines = text.splitlines()

            tabs = 0
            spaces = []

            for line in lines[:50]:
                if line.startswith("\t"):
                    tabs += 1
                elif line.startswith(" "):
                    count = len(line) - len(line.lstrip(" "))
                    if count > 0:
                        spaces.append(count)

            if tabs > len(spaces):
                self.sc.setIndentationsUseTabs(True)
                self.sc.setTabWidth(4)
            elif spaces:
                width = min(spaces)
                self.sc.setIndentationsUseTabs(False)
                self.sc.setIndentationWidth(width)
                self.sc.setTabWidth(width)

        except Exception as e:
            print(f"[EditorProxy] 检测缩进失败: {e}")

    # ========================================================
    # 书签与折叠恢复
    # ========================================================

    def _restore_bookmarks(self):
        """恢复书签标记"""
        try:
            for line in self.document.get_bookmarks():
                self.sc.markerAdd(line, MARKER_BOOKMARK)
        except Exception:
            pass

    def _restore_folds(self):
        """恢复折叠状态"""
        try:
            for line in self.document.get_folded_lines():
                self.sc.SendScintilla(QsciScintilla.SCI_TOGGLEFOLD, line)
        except Exception:
            pass

    # ========================================================
    # Scintilla 修改回调
    # ========================================================

    def _on_scintilla_modified(
        self,
        position,
        mod_type,
        text,
        length,
        lines_added,
        line,
        fold_level_now,
        fold_level_prev,
        token,
        annotation_lines_added,
    ):
        """
        QScintilla 修改通知。

        根据修改类型构建命令对象并记录到撤销栈。

        修复说明:
            - text 可能为 None（QScintilla 的某些信号），统一规范化为 bytes
        """
        if self._undoing or self._restoring:
            return
        if getattr(self, "_deferred_loading", False):
            return

        # 删除**之前**的通知：此时缓冲区里还有被删内容，先暂存下来。
        #
        # 修复（DeleteCmd 无法撤销）：SCN_MODIFIED 对删除不提供文本，
        # 若直接用它构造 DeleteCmd，`deleted_text` 会是空 bytes，
        # 而 `DeleteCmd.undo()` 在空内容时直接返回 —— 删除永久不可撤销。
        # 详见 `read_buffer_range` 的说明。
        if mod_type & QsciScintilla.SC_MOD_BEFOREDELETE:
            try:
                captured = self.read_buffer_range(position, length)
                if captured:
                    self._pending_delete_text = captured
                    self._pending_delete_pos = position
                    self._pending_delete_len = length
            except Exception as e:
                logger.debug("暂存被删内容失败: %s", e)
            # BEFOREDELETE 本身不需要记录命令，等 DELETETEXT 通知再记录
            return

        # 只处理插入和删除
        if not (mod_type & (QsciScintilla.SC_MOD_INSERTTEXT | QsciScintilla.SC_MOD_DELETETEXT)):
            return

        try:
            # 关键修复：统一规范化 text
            text_bytes = _normalize_bytes(text)

            # 构建命令
            if mod_type & QsciScintilla.SC_MOD_INSERTTEXT:
                # InsertCmd 内部会处理 bytes
                cmd = CommandPool.acquire_insert(position, text_bytes)
            else:
                # 删除：SCN_MODIFIED 不带文本，用 BEFOREDELETE 阶段暂存的
                # 内容（位置/长度匹配时）。这样撤销才能真正还原被删文本。
                deleted = b""
                try:
                    if (
                        getattr(self, "_pending_delete_text", None)
                        and self._pending_delete_pos == position
                        and self._pending_delete_len == length
                    ):
                        deleted = self._pending_delete_text
                except Exception:
                    deleted = b""
                if not deleted:
                    # 兜底：按当前缓冲区位置取（多光标/合并删除等场景）
                    deleted = self.read_buffer_range(position, length)
                self._pending_delete_text = None
                cmd = CommandPool.acquire_delete(position, length, deleted)

            # C 阶段：单光标连续插入走"原地追加"快路径，
            # 跳过 CommandPool / 命令对象分配（实测占输入延迟大头）。
            try:
                if mod_type & QsciScintilla.SC_MOD_INSERTTEXT:
                    _multi = self.sc.SendScintilla(QsciScintilla.SCI_GETSELECTIONS) > 1
                    _column = (
                        self.sc.SendScintilla(QsciScintilla.SCI_GETSELECTIONMODE)
                        == QsciScintilla.SC_SEL_RECTANGLE
                    )
                    if not _multi and not _column:
                        if self.undo_manager.try_append_typing(position, text_bytes):
                            return
            except Exception:
                pass

            # 检测是否多光标/列模式
            try:
                multi = self.sc.SendScintilla(QsciScintilla.SCI_GETSELECTIONS) > 1
                column = (
                    self.sc.SendScintilla(QsciScintilla.SCI_GETSELECTIONMODE)
                    == QsciScintilla.SC_SEL_RECTANGLE
                )
            except Exception:
                multi = False
                column = False

            now = time.time() * 1000

            # 多光标/列模式合并
            if multi or column:
                if (
                    self._pending_group
                    and (now - self._last_multi_time) < MULTI_CURSOR_MERGE_INTERVAL
                ):
                    self._pending_group.add(cmd)
                    self._last_multi_time = now
                    return
                else:
                    # 提交旧组
                    if self._pending_group:
                        self.undo_manager.record(self._pending_group)
                        self._pending_group = None

                    # 开始新组
                    self._pending_group = GroupCmd([cmd])
                    self._last_multi_time = now
                    return

            # 普通命令
            if self._pending_group:
                self.undo_manager.record(self._pending_group)
                self._pending_group = None

            self.undo_manager.record(cmd)

            # 标记文档为已修改
            if not self._modified:
                self._modified = True
                self.document.mark_modified()
                self.modified_changed.emit(True)

            # 触发内容变更信号
            self.content_changed.emit()

            # 触发智能高亮
            self._smart_hl_timer.start(SMART_HIGHLIGHT_DELAY)

            # 缓冲区 → provider 实时同步（消除"双内容源"）
            # 让查找/替换/另存为/插件读到的内容与屏幕一致，见
            # `_schedule_provider_sync` 的说明。
            self._schedule_provider_sync()

            # P0-2: 触发 LSP 文本同步（防抖）
            if self.lsp_active and self.lsp_client:
                self._lsp_sync_timer.start(LSP_SYNC_DELAY)

        except Exception as e:
            print(f"[EditorProxy] 处理修改失败: {e}")
            import traceback

            traceback.print_exc()

    # ========================================================
    # LSP 文本同步（P0-2）
    # ========================================================
