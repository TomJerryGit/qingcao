# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""编辑器代理聚合入口（v2.23 D1 拆分）。

原 3920 行的 core/editor.py 已按职责拆分：
- core/editor_common.py   公共导入/常量/辅助函数
- core/editor_save.py     保存/同步
- core/editor_loading.py  打开/加载
- core/editor_cursor.py   光标/选择/多光标
- core/editor_editops.py  行操作/注释/缩进
- core/editor_bookmarks.py 书签/断点/调试行
- core/editor_search.py   搜索/高亮
"""

from core.editor_bookmarks import EditorBookmarksMixin
from core.editor_common import *  # noqa: F401,F403
from core.editor_common import (  # noqa: F401
    _normalize_bytes,
)
from core.editor_cursor import EditorCursorMixin
from core.editor_editops import EditorEditOpsMixin
from core.editor_loading import EditorLoadingMixin
from core.editor_save import EditorSaveMixin
from core.editor_search import EditorSearchMixin


class EditorProxy(
    EditorSaveMixin,
    EditorLoadingMixin,
    EditorCursorMixin,
    EditorEditOpsMixin,
    EditorBookmarksMixin,
    EditorSearchMixin,
    QObject,
):
    """
    编辑器代理。

    职责:
    - 封装 QScintilla 的所有操作
    - 管理撤销/重做命令
    - 集成搜索引擎、LSP、宏录制
    - 提供高级编辑功能（多光标、列模式、片段等）
    - 联动事件总线

    信号:
        modified_changed(bool): 修改状态变更
        content_changed(): 内容变更
        cursor_moved(int, int): 光标移动（行, 列）
        selection_changed(): 选区变更
        load_progress(int, int): 加载进度（已加载块, 总块数）
        lsp_status_changed(str): LSP 状态变更
        lsp_error(str): LSP 失败原因 / 提示（P6，供主窗口显示）
        definition_requested(str, int, int): 定义位于其它文件（P6）
        breakpoints_changed(list): 断点集合变化（D3）
        external_change_detected(str): 文件被外部修改（从 Document 转发）
    """

    modified_changed = pyqtSignal(bool)
    content_changed = pyqtSignal()
    cursor_moved = pyqtSignal(int, int)
    selection_changed = pyqtSignal()
    load_progress = pyqtSignal(int, int)

    # 大文件分块加载：每个时间片最多占用的秒数
    #
    # 原实现是"每块固定等 10ms"（逐块 QTimer），10MB 文件纯空等就 1.6s+，
    # 100MB 要 16s+。改成时间片后，一个 slice 内连续加载多块，
    # 到点让出事件循环 —— 既保持 UI 可响应，又不浪费时间。
    _LOAD_SLICE_SECONDS = 0.012

    # 一次性同步加载的大小上限（字节）
    #
    # 实测：10MB 文件「一次 decode + 单次 setText」仅 0.13s，
    # 而逐块 append 需 10.85s（QScintilla append 超线性）。
    # 因此 32MB 以下直接一次性加载：最快，也最简单。
    _SYNC_LOAD_LIMIT = 64 * 1024 * 1024
    # v2.17：实测 50MB 一次性 setText 仅 ~0.8s（3M 行完整加载），
    # >64MB 仍走几何批量异步加载以控制峰值内存。

    # 超大文件几何递增批量 append 的批量上限（块数）
    #
    # 每轮批量翻倍，直到该上限。100MB ≈ 1600 个 64KB 块，
    # 按 1→2→4→…→1024 递增，约 15 次 append 即可加载完。
    _APPEND_BATCH_MAX_BLOCKS = 1024
    lsp_status_changed = pyqtSignal(str)
    # P6: LSP 的用户可见提示（失败原因 / 安装提示）
    lsp_error = pyqtSignal(str)
    # P6: 定义位于**其它文件**时请求主窗口打开（路径, 行, 列）
    definition_requested = pyqtSignal(str, int, int)
    # LSP 其余能力的结果转发（B 阶段接线）
    #   hover_ready       -> hover_text(str)：鼠标悬停信息
    #   references_ready  -> references_ready(list)：引用位置列表
    #   rename_ready      -> rename_applied(int)：重命名影响的位置数
    #   symbols_ready     -> symbols_ready(list)：文档符号（供大纲/跳转）
    #   code_actions_ready-> code_actions_ready(list)：可用的代码操作
    #   formatting_ready  -> formatting_applied(bool)：格式化结果
    #   signature_ready   -> signature_help(str)：签名帮助
    hover_text = pyqtSignal(str)
    references_ready = pyqtSignal(list)
    rename_applied = pyqtSignal(int)
    symbols_ready = pyqtSignal(list)
    code_actions_ready = pyqtSignal(list)
    formatting_applied = pyqtSignal(bool)
    signature_help = pyqtSignal(str)
    # D3: 断点集合变化（升序行号列表）—— 调试器据此把断点下发给被调试进程
    breakpoints_changed = pyqtSignal(list)
    # 外部文件变更（从 Document 转发；宿主据此提示用户，避免静默覆盖）
    external_change_detected = pyqtSignal(str)

    # --------------------------------------------------------
    # 内置代码片段
    # --------------------------------------------------------
    SNIPPETS = {
        "if": "if ${1:condition}:\n    ${2:pass}",
        "elif": "elif ${1:condition}:\n    ${2:pass}",
        "else": "else:\n    ${1:pass}",
        "for": "for ${1:item} in ${2:iterable}:\n    ${3:pass}",
        "while": "while ${1:condition}:\n    ${2:pass}",
        "def": "def ${1:name}(${2:args}):\n    ${3:return None}",
        "class": "class ${1:Name}:\n    def __init__(self${2:, args}):\n        ${3:pass}",
        "try": "try:\n    ${1:pass}\nexcept ${2:Exception} as e:\n    ${3:pass}",
        "with": "with ${1:expression} as ${2:var}:\n    ${3:pass}",
        "import": "import ${1:module}",
        "from": "from ${1:module} import ${2:name}",
        "main": "def main():\n    ${1:pass}\n\n\nif __name__ == '__main__':\n    main()",
        "file": "#!/usr/bin/env python\n# -*- coding: utf-8 -*-\n# @File : $TM_FILENAME\n# @Date : $CURRENT_DATE\n# @Author : $TM_AUTHOR\n",
    }

    def __init__(
        self, scintilla: QsciScintilla, document: Document, parent: Optional[QObject] = None
    ):
        """
        参数:
            scintilla: QScintilla 控件实例
            document: 关联的 Document 对象
            parent: 父 QObject
        """
        super().__init__(parent)

        self.sc = scintilla
        self.document = document

        # 反向引用：让"只拿到 QScintilla 控件"的组件（例如 VimMode）
        # 能找到本代理，从而使用**自研撤销栈**。
        #
        # 缺陷背景（审计用例 TestVimUndo 复现）：`VimMode.handle_key` 对
        # `u` / `Ctrl+R` 调用的是 `self.editor.undo()/redo()` —— 即
        # QScintilla **内置**撤销栈。而本代理在 `_connect_signals` 里执行了
        # `SCI_SETUNDOCOLLECTION(0)` 禁用内置栈，于是 Vim 的撤销**静默无效**
        # 且按键被 `handle_key` 吞掉（用户完全得不到反馈）。
        try:
            scintilla._qc_editor_proxy = self
        except Exception:
            pass

        # 撤销管理
        self.undo_manager = UndoManager()

        # 大文件分块加载状态
        #
        # `_load_aborted`：标签/窗口关闭时置位，让挂起的 QTimer 回调
        #   立即退出 —— 这是**段错误的根治**：原实现在关窗后仍有
        #   `singleShot` 回调去 `self.sc.append(...)`，而 sc 已被销毁。
        self._load_aborted = False
        self._load_cursor = 0
        self._load_total = 0
        self._load_batch_blocks = 1

        # 被删除内容的暂存（SC_MOD_BEFOREDELETE 阶段填充，DELETETEXT
        # 阶段用于构造可撤销的 DeleteCmd）。见 `read_buffer_range` 说明。
        self._pending_delete_text = None
        self._pending_delete_pos = -1
        self._pending_delete_len = 0

        # 状态标志
        self._undoing = False
        self._restoring = False
        self._modified = False

        # 命令合并相关
        self._pending_group: Optional[GroupCmd] = None
        self._last_cmd_time: float = 0.0

        # 多光标相关
        self._last_multi_time: float = 0.0

        # LSP 客户端
        self.lsp_client: Optional[LspClient] = None
        self.lsp_active: bool = False
        self._lsp_uri: str = ""
        # P6: 当前 LSP 服务器在 LspServerRegistry 中的语言键（用于安装提示）
        self._lsp_server_language: Optional[str] = None
        # P0-2: 文档变更 → didChange 的防抖定时器
        self._lsp_sync_timer = QTimer(self)
        self._lsp_sync_timer.setSingleShot(True)
        self._lsp_sync_timer.setInterval(LSP_SYNC_DELAY)
        self._lsp_sync_timer.timeout.connect(self._sync_lsp_document)

        # 宏录制回调（由 MacroRecorder 设置）
        self.record_hook: Optional[Callable] = None

        # 光标拖尾
        self._cursor_trail: List[Tuple[int, float]] = []

        # 智能高亮定时器（防抖）
        self._smart_hl_timer = QTimer(self)
        self._smart_hl_timer.setSingleShot(True)
        self._smart_hl_timer.timeout.connect(self._do_smart_highlight)

        # 缓冲区 → provider 同步定时器（防抖）
        #
        # 修复（INV-A「双内容源」根因）：
        #   在此之前，`document.provider` 只在**保存时**才与编辑器同步
        #   （`_sync_content_to_provider` 只在 save_file / 打开文件时调用）。
        #   于是打字过程中存在**两份内容**，所有基于 provider 的功能都会
        #   看到过期快照：
        #       * 编辑器内查找查不到刚输入的文字（实测 search_next 返回 False）
        #       * 「全部替换」在快照上替换后用快照覆盖编辑器 →
        #         未保存的编辑被静默丢弃
        #       * 另存为写入旧内容（P0-B，已单独修复入口）
        #       * 全局替换 / 插件读到的也是旧内容
        #
        #   现在在每次编辑后**防抖同步**缓冲区到 provider，让两者始终一致。
        #   间隔取 0ms：既让连续击键只触发一次（QTimer 会自动重启），
        #   又能在事件循环下一轮就生效（不依赖用户等待）。
        #   超大文件跳过（见 `_schedule_provider_sync`），避免拖慢打字。
        self._provider_sync_timer = QTimer(self)
        self._provider_sync_timer.setSingleShot(True)
        self._provider_sync_timer.setInterval(PROVIDER_SYNC_DELAY)
        self._provider_sync_timer.timeout.connect(self._sync_provider_now)
        # 超过该大小的文件不做实时同步（保存时仍会同步）
        self._provider_sync_max_bytes = 8 * 1024 * 1024
        # 小于该大小的文件**立即**同步（成本可忽略，保证 provider 始终新鲜）
        self._provider_sync_immediate_bytes = 256 * 1024

        # 指示器初始化
        self._init_indicators()
        self._init_markers()

        # 连接信号
        self._connect_signals()

        # 记录初始状态
        self._modified = False

    # ========================================================
    # 初始化
    # ========================================================
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

    def _on_modification_changed(self, modified: bool):
        """QScintilla 修改状态变更"""
        if self._modified != modified:
            self._modified = modified
            self.modified_changed.emit(modified)

            if modified:
                self.document.mark_modified()
            else:
                self.document.mark_saved()

    def _on_cursor_changed(self, line: int, col: int):
        """光标位置变更"""
        self.cursor_moved.emit(line + 1, col)

        # 发射事件总线
        try:
            bus.emit_event(
                CursorEvent(
                    line=line + 1,
                    col=col,
                    position=self.get_current_pos(),
                )
            )
        except Exception:
            pass

        # 光标拖尾
        self._update_cursor_trail()

    def _on_selection_changed(self):
        """选区变更"""
        self.selection_changed.emit()

        try:
            text = self.sc.selectedText()
            if text:
                bus.emit_event(
                    SelectionEvent(
                        text=text,
                        char_count=len(text),
                        line_count=text.count("\n") + 1,
                    )
                )
        except Exception:
            pass

    # ========================================================
    # 撤销/重做
    # ========================================================
    def undo(self):
        """撤销"""
        self._undoing = True
        try:
            # 提交待处理的组
            if self._pending_group:
                self.undo_manager.record(self._pending_group)
                self._pending_group = None

            self.undo_manager.undo(self.sc)

            # 发射事件
            try:
                bus.emit_event(UndoEvent(command_count=len(self.undo_manager.undo_stack)))
            except Exception:
                pass

            # 更新修改状态
            if not self.sc.isModified():
                self._modified = False
                self.modified_changed.emit(False)

        except Exception as e:
            print(f"[EditorProxy] 撤销失败: {e}")
        finally:
            self._undoing = False

    def redo(self):
        """重做"""
        self._undoing = True
        try:
            self.undo_manager.redo(self.sc)

            try:
                bus.emit_event(RedoEvent(command_count=len(self.undo_manager.redo_stack)))
            except Exception:
                pass

            self._modified = True
            self.modified_changed.emit(True)

        except Exception as e:
            print(f"[EditorProxy] 重做失败: {e}")
        finally:
            self._undoing = False

    def can_undo(self) -> bool:
        """是否可撤销"""
        return len(self.undo_manager.undo_stack) > 0

    def can_redo(self) -> bool:
        """是否可重做"""
        return len(self.undo_manager.redo_stack) > 0

    def _on_document_filepath_changed(self, new_path: str):
        """文档另存为新路径 → 同步 LSP 文档 URI

        缺陷背景（INV-L1/L2，审计测试复现）：
            `Document.save(new_path)` 会更新 `document.filepath`，但
            `EditorProxy._lsp_uri` 仍是**旧路径**的 URI。而
            `_notify_lsp_saved()` / `request_definition()` 都用
            `self._lsp_uri or ...` 取值 —— 一旦它是真值就永远用旧的。

            后果：另存为之后，
              * didSave / didChange 发给**旧文档**
              * 服务器对旧路径产生诊断 → 画到当前编辑器（跨文件污染）
              * request_completion / request_definition 用新路径，服务器不认识
                → 补全与跳转失效

        处理：向服务器注销旧文档，以新 URI 重新 did_open。
        """
        try:
            new_uri = LspClient.path_to_uri(new_path or "")
            if not new_uri or new_uri == self._lsp_uri:
                return

            # URI 必须**始终**与文件路径保持一致 —— 它描述的是"当前编辑的
            # 是哪个文件"，与有没有连上语言服务器无关。
            # （审计用例 `test_save_as_updates_lsp_uri` 正是在没有 lsp_client
            #   的情况下断言这一点：不能因为"服务器没开"就让 URI 停留在旧值，
            #   否则之后一启用 LSP 就会对着旧文档操作。）
            old_uri = self._lsp_uri
            self._lsp_uri = new_uri

            # 通知服务器注销旧文档、以新 URI 打开 —— 这一步才需要连接
            if not (self.lsp_active and self.lsp_client):
                return
            if old_uri:
                try:
                    self.lsp_client.did_close(old_uri)
                except Exception:
                    pass
            try:
                lang = lsp_language_for_file(new_path or "")
                self.lsp_client.did_open(new_uri, lang, self.sc.text())
            except Exception as e:
                logger.debug("另存为后 did_open 失败: %s", e)
        except Exception as e:
            logger.warning("同步 LSP URI 失败: %s", e)

    def _on_document_reloaded(self, filepath: str = ""):
        """文档被重新加载（换编码 / 外部改动重载）后刷新编辑器文本

        缺陷背景（INV-C，审计测试复现）：
            `Document.reload()` 与 `Document.change_encoding()` 都会重载
            provider（文本已按新编码正确解码），`reloaded` 信号也 emit 了，
            但**全仓零 connect** —— 编辑器继续显示旧编码解出的乱码，而
            provider 已是正确文本。两者不一致时，查找/替换/另存为/全局
            替换都会看到与屏幕不同的内容。

        实现要点：
            1. 文本以 **provider** 为准（它是刚按新编码解码的结果）；
            2. 保留光标位置（重载不应把用户弹回文件开头）；
            3. 重载等于"文件被整体替换"，旧的撤销历史对新内容无效，
               因此清空撤销/重做栈，避免撤销把文件改回重载前的样子；
            4. 同步 `_modified` 与 Scintilla 的脏标记（重载后无未保存修改）。
        """
        try:
            provider = getattr(self.document, "provider", None)
            if provider is None:
                return
            try:
                text = provider.read_text()
            except Exception as e:
                logger.debug("重载后读取 provider 失败: %s", e)
                return

            # 保留光标
            line = col = 0
            try:
                line, col = self.sc.getCursorPosition()
            except Exception:
                pass

            try:
                self.sc.setText(text)
            except Exception as e:
                logger.warning("重载后刷新编辑器文本失败: %s", e)
                return

            # 恢复光标（行号可能因内容变化而越界，做钳制）
            try:
                total = max(1, self.sc.lines())
                self.sc.setCursorPosition(min(line, total - 1), col)
            except Exception:
                pass

            # 重载是整体替换：旧撤销历史不再适用
            try:
                if getattr(self, "undo_manager", None) is not None:
                    self.undo_manager.clear()
            except Exception:
                pass
            try:
                self.sc.SendScintilla(QsciScintilla.SCI_EMPTYUNDOBUFFER)
            except Exception:
                pass

            # 重载后内容与磁盘一致 → 干净状态
            self._modified = False
            try:
                self.sc.setModified(False)
            except Exception:
                pass
            self.modified_changed.emit(False)

        except Exception as e:
            logger.warning("处理文档重载信号失败: %s", e)

    # ========================================================
    # 代码片段
    # ========================================================
    def expand_snippet(self, trigger: str) -> bool:
        """
        展开代码片段。

        参数:
            trigger: 触发词（如 "if" / "for"）

        返回:
            是否成功
        """
        snippet = self.SNIPPETS.get(trigger)
        if not snippet:
            return False

        try:
            # 替换内置变量
            snippet = self._replace_snippet_vars(snippet)

            # 选中当前词并替换
            self.sc.selectCurrentWord()
            self.sc.removeSelectedText()
            self.sc.insert(snippet)

            # 高亮第一个占位符
            self._highlight_first_placeholder(snippet)

            return True

        except Exception as e:
            print(f"[EditorProxy] 展开片段失败: {e}")
            return False

    def _replace_snippet_vars(self, snippet: str) -> str:
        """替换片段中的内置变量"""
        now = datetime.datetime.now()

        # 从偏好获取作者（P8: 统一走 Preferences；author_name 不在
        # DEFAULTS 里，缺失时用 "anonymous"）
        prefs = self._prefs()
        if prefs is not None:
            author = prefs.get("author_name", "anonymous")
        else:
            author = "anonymous"

        replacements = {
            "$TM_FILENAME": (
                os.path.basename(self.document.filepath) if self.document.filepath else ""
            ),
            "$TM_FILENAME_BASE": (
                os.path.splitext(os.path.basename(self.document.filepath))[0]
                if self.document.filepath
                else ""
            ),
            "$TM_DIRECTORY": (
                os.path.dirname(self.document.filepath) if self.document.filepath else ""
            ),
            "$CURRENT_YEAR": str(now.year),
            "$CURRENT_MONTH": str(now.month).zfill(2),
            "$CURRENT_DAY": str(now.day).zfill(2),
            "$CURRENT_DATE": now.strftime("%Y-%m-%d"),
            "$CURRENT_TIME": now.strftime("%H:%M:%S"),
            "$CURRENT_DATETIME": now.strftime("%Y-%m-%d %H:%M:%S"),
            "$TM_AUTHOR": author,
        }

        for var, value in replacements.items():
            snippet = snippet.replace(var, value)

        return snippet

    def _highlight_first_placeholder(self, snippet: str):
        """高亮第一个占位符 ${1:...}"""
        try:
            match = re.search(r"\$\{1:([^}]*)\}", snippet)
            if not match:
                return

            # 计算位置
            insert_pos = self.get_current_pos() - len(snippet)
            start = insert_pos + match.start()
            end = start + (match.end() - match.start())

            self.sc.SendScintilla(QsciScintilla.SCI_SETSELECTIONSTART, start)
            self.sc.SendScintilla(QsciScintilla.SCI_SETSELECTIONEND, end)

        except Exception:
            pass

    # ========================================================
    # 特殊插入
    # ========================================================
    def insert_datetime(self):
        """插入当前日期时间。

        P7/P8 接线：格式来自 Preferences 的 ``date_format`` /
        ``time_format``（原先硬编码 ``"%Y-%m-%d %H:%M:%S"``，
        用户在首选项里改了这一项也没有任何效果）。
        """
        try:
            prefs = self._prefs()
            date_fmt = time_fmt = None
            if prefs is not None:
                date_fmt = prefs.get("date_format", None)
                time_fmt = prefs.get("time_format", None)
            fmt = resolve_datetime_format(date_fmt, time_fmt)
            ts = datetime.datetime.now().strftime(fmt)
            pos = self.get_current_pos()
            self.sc.SendScintilla(QsciScintilla.SCI_INSERTTEXT, pos, ts.encode("utf-8"))
        except Exception as e:
            print(f"[EditorProxy] 插入日期时间失败: {e}")

    def eval_expression(self) -> bool:
        """
        计算选中文本的数学表达式并替换结果。

        返回:
            是否成功
        """
        try:
            expr = self.sc.selectedText()
            if not expr:
                return False

            # 安全限制：仅允许数字、运算符、括号、空格
            if not re.match(r"^[\d\s\+\-\*\/\(\)\.\^\%]+$", expr):
                return False

            # 计算
            result = eval(expr, {"__builtins__": {}})

            if isinstance(result, (int, float)):
                # 格式化结果
                if isinstance(result, float):
                    if result.is_integer():
                        result_str = str(int(result))
                    else:
                        result_str = f"{result:.6g}"
                else:
                    result_str = str(result)

                self.sc.replaceSelectedText(result_str)
                return True

        except Exception as e:
            print(f"[EditorProxy] 计算表达式失败: {e}")

        return False

    # ========================================================
    # 大小写转换
    # ========================================================
    def to_upper(self):
        """选中文本转大写"""
        text = self.sc.selectedText()
        if text:
            self.sc.replaceSelectedText(text.upper())

    def to_lower(self):
        """选中文本转小写"""
        text = self.sc.selectedText()
        if text:
            self.sc.replaceSelectedText(text.lower())

    def toggle_case(self):
        """选中文本大小写切换"""
        text = self.sc.selectedText()
        if text:
            self.sc.replaceSelectedText(text.swapcase())

    # ========================================================
    # 行尾空白清理
    # ========================================================
    def trim_trailing_whitespace(self):
        """清除所有行的行尾空白"""
        try:
            text = self.sc.text()
            lines = [l.rstrip() for l in text.splitlines()]
            new_text = "\n".join(lines)

            if new_text != text:
                self.set_text(new_text)

        except Exception as e:
            print(f"[EditorProxy] 清除行尾空白失败: {e}")

    def remove_blank_lines(self):
        """删除所有空行"""
        try:
            text = self.sc.text()
            lines = [l for l in text.splitlines() if l.strip()]
            new_text = "\n".join(lines)

            if new_text != text:
                self.set_text(new_text)

        except Exception as e:
            print(f"[EditorProxy] 删除空行失败: {e}")

    # ========================================================
    # LSP 集成
    # ========================================================
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
    def close(self) -> bool:
        """
        关闭编辑器代理，释放资源。

        返回:
            是否成功（若文档有未保存修改则返回 False）
        """
        try:
            # 停止定时器
            self._smart_hl_timer.stop()
            self._lsp_sync_timer.stop()

            # 停止 LSP（P0-2: 先通知 didClose 再关闭进程）
            if self.lsp_client:
                try:
                    if self._lsp_uri:
                        self.lsp_client.did_close(self._lsp_uri)
                except Exception:
                    pass
                self.lsp_client.stop()
                self.lsp_client = None
                self.lsp_active = False
                self._lsp_uri = ""

            # 保存光标和视图位置
            try:
                line, col = self.sc.getCursorPosition()
                first_line = self.sc.SendScintilla(QsciScintilla.SCI_GETFIRSTVISIBLELINE)
                self.document.remember_cursor(
                    line,
                    col,
                    self.get_current_pos(),
                    first_line,
                    self.sc.horizontalScrollBar().value(),
                )
            except Exception:
                pass

            # 保存书签和折叠状态
            try:
                self.document.set_folded_lines(self._get_folded_lines())
            except Exception:
                pass

            # 关闭文档
            self.document.close()

            return True

        except Exception as e:
            print(f"[EditorProxy] 关闭失败: {e}")
            return False

    def _get_folded_lines(self) -> List[int]:
        """获取当前所有折叠的行号"""
        folded = []
        try:
            line_count = self.sc.SendScintilla(QsciScintilla.SCI_GETLINECOUNT)
            for line in range(line_count):
                expanded = self.sc.SendScintilla(QsciScintilla.SCI_GETFOLDEXPANDED, line)
                if expanded == 0:
                    folded.append(line)
        except Exception:
            pass
        return folded

    # ========================================================
    # 属性
    # ========================================================
    @property
    def is_modified(self) -> bool:
        """文档是否已修改"""
        return self._modified

    @property
    def filepath(self) -> Optional[str]:
        """文件路径"""
        return self.document.filepath

    @property
    def encoding(self) -> str:
        """编码"""
        return self.document.encoding

    @property
    def prov(self):
        """
        [已弃用] 兼容旧 API：内容提供者。

        早期代码通过 `proxy.prov` 访问 ContentProvider，
        新代码应使用 `proxy.document.provider`。

        保留此别名以便：
        - 兼容 app/plugins.py 等尚未迁移的调用方
        - 兼容第三方插件

        返回：
            ContentProvider 实例或 None
        """
        if self.document:
            return self.document.provider
        return None

    @prov.setter
    def prov(self, value):
        """
        [已弃用] 兼容旧 API：设置内容提供者。

        早期代码通过 `proxy.prov = provider` 更新，
        新代码应使用 `proxy.document.provider = provider`。
        """
        if self.document:
            self.document.provider = value

    @property
    def title(self) -> str:
        """标题"""
        return self.document.title

    @property
    def language(self) -> str:
        """语言"""
        return self.document.language

    @property
    def is_readonly(self) -> bool:
        """是否只读"""
        return self.document.is_readonly

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出编辑器状态"""
        lines = [f"EditorProxy: {self.title}", "=" * 60]
        lines.append(f"文件: {self.filepath or '(未保存)'}")
        lines.append(f"编码: {self.encoding}")
        lines.append(f"语言: {self.language or '(未知)'}")
        lines.append(f"修改: {self.is_modified}")
        lines.append(f"只读: {self.is_readonly}")
        lines.append(f"撤销栈: {len(self.undo_manager.undo_stack)}")
        lines.append(f"重做栈: {len(self.undo_manager.redo_stack)}")
        lines.append(f"选区数: {self.get_selection_count()}")
        lines.append(f"LSP: {'启用' if self.lsp_active else '禁用'}")
        lines.append(f"书签: {len(self.document.get_bookmarks())}")
        lines.append(f"折叠: {len(self.document.get_folded_lines())}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"<EditorProxy title={self.title!r} modified={self.is_modified} path={self.filepath!r}>"
        )


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import shutil
    import sys
    import tempfile

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    print("=== 测试 EditorProxy ===")

    # 创建临时文件
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_editor_test_")
    test_file = os.path.join(tmp_dir, "test.py")

    with open(test_file, "w", encoding="utf-8") as f:
        f.write("#!/usr/bin/env python\n")
        f.write("# -*- coding: utf-8 -*-\n\n")
        f.write("def main():\n")
        f.write("    print('Hello, 青草!')\n")
        f.write("    return 0\n\n")
        f.write("if __name__ == '__main__':\n")
        f.write("    main()\n")

    # 创建编辑器
    sc = QsciScintilla()
    doc = Document()
    proxy = EditorProxy(sc, doc)

    # 打开文件
    print(f"打开文件: {proxy.open_file(test_file)}")
    print()
    print(proxy.dump())
    print()

    # 测试获取文本
    text = proxy.get_text()
    print(f"文本长度: {len(text)} 字符")
    print(f"行数: {sc.SendScintilla(QsciScintilla.SCI_GETLINECOUNT)}")
    print()

    # 测试光标
    proxy.goto_line(4)
    line, col = proxy.get_cursor_position()
    print(f"光标位置: ({line}, {col})")
    print(f"字符偏移: {proxy.get_current_pos()}")
    print()

    # 测试插入
    proxy.insert_text("# 测试插入\n")
    print(f"插入后修改状态: {proxy.is_modified}")
    print()

    # 测试撤销
    proxy.undo()
    print(f"撤销后修改状态: {proxy.is_modified}")
    print()

    # 测试书签
    proxy.toggle_bookmark()
    print(f"书签: {doc.get_bookmarks()}")
    proxy.next_bookmark()
    print()

    # 测试代码片段
    proxy.expand_snippet("if")
    print("片段展开测试完成")
    print()

    # 测试搜索高亮
    count = proxy.highlight_all("print")
    print(f"搜索 'print' 匹配数: {count}")
    proxy.clear_highlights()
    print()

    # 测试移动行（关键修复）
    print("=== 测试移动行 ===")
    proxy.goto_line(3)
    try:
        proxy.move_line_down()
        print("move_line_down 成功")
    except Exception as e:
        print(f"move_line_down 失败: {e}")

    try:
        proxy.move_line_up()
        print("move_line_up 成功")
    except Exception as e:
        print(f"move_line_up 失败: {e}")

    # 测试复制行（关键修复）
    try:
        proxy.duplicate_line()
        print("duplicate_line 成功")
    except Exception as e:
        print(f"duplicate_line 失败: {e}")
    print()

    # 测试保存
    print(f"保存: {proxy.save_file()}")
    print()

    # 测试关闭
    print(f"关闭: {proxy.close()}")

    # 清理
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print()
    print("测试完成。")
