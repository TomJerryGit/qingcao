# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405,F811
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

from core.editor_bookmarks import EditorBookmarksMixin  # noqa: F401
from core.editor_common import *  # noqa: F401,F403,F405
from core.editor_common import (  # noqa: F401
    _EOL_SPLIT_RE,
    _normalize_bytes,
)
from core.editor_cursor import EditorCursorMixin  # noqa: F401
from core.editor_editops import EditorEditOpsMixin  # noqa: F401
from core.editor_events import EditorEventsMixin  # noqa: F401
from core.editor_loading import EditorLoadingMixin  # noqa: F401
from core.editor_lsp import EditorLspMixin  # noqa: F401
from core.editor_save import EditorSaveMixin  # noqa: F401
from core.editor_search import EditorSearchMixin  # noqa: F401
from core.editor_textops import EditorTextOpsMixin  # noqa: F401


class EditorProxy(
    EditorEventsMixin,
    EditorLspMixin,
    EditorTextOpsMixin,
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
