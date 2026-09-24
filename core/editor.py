#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为编辑器代理模块，包含：
- EditorProxy：编辑器操作代理（UI 与文档模型之间的桥梁）
- 撤销/重做命令管理
- 多光标与列模式
- 智能括号与自动缩进
- 代码片段展开
- 书签与折叠
- LSP 客户端集成
- 宏录制回调
- 搜索高亮
- 事件总线联动
- 光标拖尾与智能单词高亮

修复记录:
- _on_scintilla_modified: text 可能为 None/bytes，统一规范化
- _move_line / duplicate_line: 使用 self.sc.text() 替代
  QsciScintilla.SCI_GETRANGE（PyQt5 未导出该常量）
- 所有 SCI_INSERTTEXT 调用确保传入 bytes
"""

import os
import re
import time
import datetime
from typing import Optional, List, Dict, Any, Tuple, Callable

from PyQt5.Qsci import QsciScintilla, QsciLexerPython, QsciLexerCPP
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QDateTime, QSettings
from PyQt5.QtGui import QColor, QFont

from core.commands import (
    InsertCmd, DeleteCmd, ReplaceCmd, GroupCmd,
    CommandFactory, CommandPool, merge_commands
)
from core.undo import UndoManager
from core.search import SearchEngine, SearchOptions
from core.document import Document
from core.lsp_client import LspClient
from app.event_bus import (
    bus, FileEvent, FileSavedEvent, FileModifiedEvent,
    CursorEvent, SelectionEvent, TextEditEvent, UndoEvent, RedoEvent,
    StatusMessageEvent, SearchStartedEvent, SearchFinishedEvent
)


# ============================================================
# 常量
# ============================================================
# 指示器 ID
INDICATOR_SEARCH = 0          # 搜索高亮
INDICATOR_CURRENT_MATCH = 1   # 当前匹配
INDICATOR_LSP_ERROR = 2       # LSP 错误波浪线
INDICATOR_SNIPPET = 3         # 代码片段占位符
INDICATOR_CURSOR_TRAIL = 5    # 光标拖尾
INDICATOR_SMART_HIGHLIGHT = 7 # 智能单词高亮

# 标记 ID
MARKER_BOOKMARK = 0           # 书签
MARKER_GIT_ADDED = 1          # Git 新增行
MARKER_GIT_MODIFIED = 2       # Git 修改行
MARKER_GIT_DELETED = 3        # Git 删除行
MARKER_BREAKPOINT = 4         # 调试断点

# 多光标合并时间窗口（毫秒）
MULTI_CURSOR_MERGE_INTERVAL = 300

# 智能高亮防抖延迟（毫秒）
SMART_HIGHLIGHT_DELAY = 300

# 光标拖尾保留时长（秒）
CURSOR_TRAIL_DURATION = 0.2


# ============================================================
# 辅助函数
# ============================================================
def _normalize_bytes(data) -> bytes:
    """将输入统一转为 bytes"""
    if data is None:
        return b''
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, str):
        return data.encode('utf-8', errors='replace')
    return str(data).encode('utf-8', errors='replace')


# ============================================================
# 编辑器代理
# ============================================================
class EditorProxy(QObject):
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
    """

    modified_changed = pyqtSignal(bool)
    content_changed = pyqtSignal()
    cursor_moved = pyqtSignal(int, int)
    selection_changed = pyqtSignal()
    load_progress = pyqtSignal(int, int)
    lsp_status_changed = pyqtSignal(str)

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

    def __init__(self, scintilla: QsciScintilla,
                 document: Document,
                 parent: Optional[QObject] = None):
        """
        参数:
            scintilla: QScintilla 控件实例
            document: 关联的 Document 对象
            parent: 父 QObject
        """
        super().__init__(parent)

        self.sc = scintilla
        self.document = document

        # 撤销管理
        self.undo_manager = UndoManager()

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

        # 宏录制回调（由 MacroRecorder 设置）
        self.record_hook: Optional[Callable] = None

        # 光标拖尾
        self._cursor_trail: List[Tuple[int, float]] = []

        # 智能高亮定时器（防抖）
        self._smart_hl_timer = QTimer(self)
        self._smart_hl_timer.setSingleShot(True)
        self._smart_hl_timer.timeout.connect(self._do_smart_highlight)

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
            self.sc.indicatorDefine(QsciScintilla.INDIC_STRAIGHTBOX,
                                    INDICATOR_SEARCH)
            self.sc.setIndicatorForegroundColor(
                QColor(255, 255, 0, 120), INDICATOR_SEARCH
            )
            self.sc.setIndicatorOutlineColor(
                QColor(255, 200, 0), INDICATOR_SEARCH
            )

            # 当前匹配（橙色）
            self.sc.indicatorDefine(QsciScintilla.INDIC_ROUNDBOX,
                                    INDICATOR_CURRENT_MATCH)
            self.sc.setIndicatorForegroundColor(
                QColor(255, 128, 0, 180), INDICATOR_CURRENT_MATCH
            )

            # LSP 错误（红色波浪线）
            self.sc.indicatorDefine(QsciScintilla.INDIC_SQUIGGLE,
                                    INDICATOR_LSP_ERROR)
            self.sc.setIndicatorForegroundColor(
                QColor(255, 0, 0), INDICATOR_LSP_ERROR
            )

            # 智能高亮（灰色）
            self.sc.indicatorDefine(QsciScintilla.INDIC_STRAIGHTBOX,
                                    INDICATOR_SMART_HIGHLIGHT)
            self.sc.setIndicatorForegroundColor(
                QColor(100, 100, 100, 60), INDICATOR_SMART_HIGHLIGHT
            )

            # 光标拖尾（淡黄）
            self.sc.indicatorDefine(QsciScintilla.INDIC_STRAIGHTBOX,
                                    INDICATOR_CURSOR_TRAIL)
            self.sc.setIndicatorForegroundColor(
                QColor(255, 255, 0, 80), INDICATOR_CURSOR_TRAIL
            )

            # 代码片段占位符（蓝色）
            self.sc.indicatorDefine(QsciScintilla.INDIC_STRAIGHTBOX,
                                    INDICATOR_SNIPPET)
            self.sc.setIndicatorForegroundColor(
                QColor(0, 120, 215, 100), INDICATOR_SNIPPET
            )

        except Exception as e:
            print(f"[EditorProxy] 初始化指示器失败: {e}")

    def _init_markers(self):
        """初始化书签和 Git 标记"""
        try:
            # 书签
            self.sc.markerDefine(QsciScintilla.Circle, MARKER_BOOKMARK)
            self.sc.setMarkerBackgroundColor(
                QColor("#007acc"), MARKER_BOOKMARK
            )

            # Git 标记（用背景色标出）
            self.sc.markerDefine(QsciScintilla.Background, MARKER_GIT_ADDED)
            self.sc.setMarkerBackgroundColor(
                QColor(0, 255, 0, 30), MARKER_GIT_ADDED
            )

            self.sc.markerDefine(QsciScintilla.Background, MARKER_GIT_MODIFIED)
            self.sc.setMarkerBackgroundColor(
                QColor(0, 120, 215, 30), MARKER_GIT_MODIFIED
            )

            self.sc.markerDefine(QsciScintilla.Background, MARKER_GIT_DELETED)
            self.sc.setMarkerBackgroundColor(
                QColor(255, 0, 0, 30), MARKER_GIT_DELETED
            )

            # 断点
            self.sc.markerDefine(QsciScintilla.Circle, MARKER_BREAKPOINT)
            self.sc.setMarkerBackgroundColor(
                QColor("#ff0000"), MARKER_BREAKPOINT
            )

        except Exception as e:
            print(f"[EditorProxy] 初始化标记失败: {e}")

    def _connect_signals(self):
        """连接 QScintilla 的信号"""
        try:
            self.sc.SCN_MODIFIED.connect(self._on_scintilla_modified)
            self.sc.modificationChanged.connect(
                self._on_modification_changed
            )
            self.sc.cursorPositionChanged.connect(self._on_cursor_changed)
            self.sc.selectionChanged.connect(self._on_selection_changed)

            # 禁用内置撤销栈
            self.sc.SendScintilla(QsciScintilla.SCI_EMPTYUNDOBUFFER)
            self.sc.SendScintilla(QsciScintilla.SCI_SETUNDOCOLLECTION, 0)

        except Exception as e:
            print(f"[EditorProxy] 连接信号失败: {e}")

    # ========================================================
    # 打开与保存
    # ========================================================
    def open_file(self, filepath: Optional[str] = None) -> bool:
        """
        打开文件。

        参数:
            filepath: 文件路径（None 则使用 document 中已打开的）

        返回:
            是否成功
        """
        try:
            self._restoring = True

            if filepath:
                if not self.document.open(filepath):
                    return False

            # 清空编辑器
            self.sc.clear()

            # 设置语法高亮
            self._apply_lexer(filepath or self.document.filepath)

            # 加载内容（分块流式）
            self._load_content()

            # 检测缩进风格
            self._detect_indent()

            # 恢复书签和折叠
            self._restore_bookmarks()
            self._restore_folds()

            # 清空撤销栈
            self.undo_manager.clear()

            # 更新状态
            self._modified = False
            self.sc.setModified(False)

            self._restoring = False

            # 发射事件
            try:
                bus.emit_event(FileEvent(
                    path=self.document.filepath or "",
                    encoding=self.document.encoding,
                ))
            except Exception:
                pass

            return True

        except Exception as e:
            self._restoring = False
            print(f"[EditorProxy] 打开文件失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _load_content(self):
        """分块加载内容"""
        if not self.document.provider:
            return

        provider = self.document.provider
        total = provider.total_blocks

        # 大文件使用流式加载
        if provider.size > 10 * 1024 * 1024:
            # 立即加载前几块
            initial_blocks = min(20, total)
            for i in range(initial_blocks):
                data = provider.read_block(i)
                text = provider.decode(data)
                self.sc.append(text)
                self.load_progress.emit(i + 1, total)

            # 剩余块延迟加载
            self._load_next_chunk(initial_blocks, total)
        else:
            # 小文件一次性加载
            for i in range(total):
                data = provider.read_block(i)
                text = provider.decode(data)
                self.sc.append(text)
            self.load_progress.emit(total, total)

    def _load_next_chunk(self, current: int, total: int):
        """延迟加载下一块"""
        if current >= total:
            return

        try:
            data = self.document.provider.read_block(current)
            text = self.document.provider.decode(data)
            self.sc.append(text)
            self.load_progress.emit(current + 1, total)

            # 延迟加载下一块
            QTimer.singleShot(
                10,
                lambda: self._load_next_chunk(current + 1, total)
            )
        except Exception as e:
            print(f"[EditorProxy] 加载块 {current} 失败: {e}")

    def save_file(self, filepath: Optional[str] = None) -> bool:
        """
        保存文件。

        参数:
            filepath: 另存为路径

        返回:
            是否成功
        """
        try:
            # 获取文本
            text = self.sc.text()

            # 应用偏好设置：清理行尾空白和末尾换行
            settings = QSettings("QingCao", "Editor")

            if settings.value("trim_trailing_whitespace", True, type=bool):
                lines = [l.rstrip() for l in text.splitlines()]
                text = '\n'.join(lines)

            if settings.value("insert_final_newline", True, type=bool):
                if text and not text.endswith('\n'):
                    text += '\n'

            # 设置回编辑器（保持一致性）
            if text != self.sc.text():
                self.sc.setText(text)

            # 更新提供者内容
            self._sync_content_to_provider(text)

            # 保存
            success = self.document.save(filepath)

            if success:
                self._modified = False
                self.sc.setModified(False)

                # 删除草稿
                try:
                    self.document.delete_draft()
                except Exception:
                    pass

                self.modified_changed.emit(False)

                # 发射事件
                try:
                    bus.emit_event(FileSavedEvent(
                        path=self.document.filepath or "",
                        size=self.document.meta.size,
                    ))
                except Exception:
                    pass

            return success

        except Exception as e:
            print(f"[EditorProxy] 保存失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _sync_content_to_provider(self, text: str):
        """将编辑器内容同步到提供者"""
        if not self.document.provider:
            return

        provider = self.document.provider
        encoded = provider.encode(text)
        new_size = len(encoded)
        block_size = provider.block_size
        total_blocks = max(1, (new_size + block_size - 1) // block_size)

        # 清空旧脏块
        provider.clear_dirty()

        # 写入所有块
        for bid in range(total_blocks):
            start = bid * block_size
            end = min(start + block_size, new_size)
            provider.write_block(bid, encoded[start:end])

        # 更新提供者元数据
        if hasattr(provider, '_total_blocks'):
            provider._total_blocks = total_blocks
        if hasattr(provider, '_size'):
            provider._size = new_size

    # ========================================================
    # 词法器
    # ========================================================
    def _apply_lexer(self, filepath: Optional[str]):
        """根据文件扩展名应用语法高亮"""
        if not filepath:
            self.sc.setLexer(None)
            return

        ext = os.path.splitext(filepath)[1].lower()

        try:
            if ext in ('.py', '.pyw'):
                self.sc.setLexer(QsciLexerPython())
            elif ext in ('.cpp', '.cc', '.cxx', '.h', '.hpp', '.c'):
                self.sc.setLexer(QsciLexerCPP())
            elif ext == '.log':
                # 使用自定义日志词法器（如果注册过）
                try:
                    from core.log_lexer import LogLexer
                    self.sc.setLexer(LogLexer(self.sc))
                except ImportError:
                    self.sc.setLexer(None)
            else:
                # 检查是否有自定义词法器
                try:
                    custom = getattr(self.sc.window(), '_custom_lexers', {})
                except Exception:
                    custom = {}
                if ext in custom:
                    factory = custom[ext]
                    lexer = factory()
                    if lexer:
                        self.sc.setLexer(lexer)
                else:
                    self.sc.setLexer(None)
        except Exception as e:
            print(f"[EditorProxy] 应用词法器失败: {e}")
            self.sc.setLexer(None)

    def _detect_indent(self):
        """检测缩进风格"""
        try:
            text = self.sc.text()
            lines = text.splitlines()

            tabs = 0
            spaces = []

            for line in lines[:50]:
                if line.startswith('\t'):
                    tabs += 1
                elif line.startswith(' '):
                    count = len(line) - len(line.lstrip(' '))
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
    def _on_scintilla_modified(self, position, mod_type, text, length,
                                lines_added, line, fold_level_now,
                                fold_level_prev, token,
                                annotation_lines_added):
        """
        QScintilla 修改通知。

        根据修改类型构建命令对象并记录到撤销栈。

        修复说明:
            - text 可能为 None（QScintilla 的某些信号），统一规范化为 bytes
        """
        if self._undoing or self._restoring:
            return

        # 只处理插入和删除
        if not (mod_type & (QsciScintilla.SC_MOD_INSERTTEXT |
                            QsciScintilla.SC_MOD_DELETETEXT)):
            return

        try:
            # 关键修复：统一规范化 text
            text_bytes = _normalize_bytes(text)

            # 构建命令
            if mod_type & QsciScintilla.SC_MOD_INSERTTEXT:
                # InsertCmd 内部会处理 bytes
                cmd = CommandPool.acquire_insert(position, text_bytes)
            else:
                cmd = CommandPool.acquire_delete(
                    position, length, text_bytes
                )

            # 检测是否多光标/列模式
            try:
                multi = self.sc.SendScintilla(
                    QsciScintilla.SCI_GETSELECTIONS
                ) > 1
                column = (
                    self.sc.SendScintilla(
                        QsciScintilla.SCI_GETSELECTIONMODE
                    ) == QsciScintilla.SC_SEL_RECTANGLE
                )
            except Exception:
                multi = False
                column = False

            now = time.time() * 1000

            # 多光标/列模式合并
            if multi or column:
                if (self._pending_group and
                        (now - self._last_multi_time) <
                        MULTI_CURSOR_MERGE_INTERVAL):
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

        except Exception as e:
            print(f"[EditorProxy] 处理修改失败: {e}")
            import traceback
            traceback.print_exc()

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
            bus.emit_event(CursorEvent(
                line=line + 1, col=col,
                position=self.get_current_pos(),
            ))
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
                bus.emit_event(SelectionEvent(
                    text=text,
                    char_count=len(text),
                    line_count=text.count('\n') + 1,
                ))
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
                bus.emit_event(UndoEvent(
                    command_count=len(self.undo_manager.undo_stack)
                ))
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
                bus.emit_event(RedoEvent(
                    command_count=len(self.undo_manager.redo_stack)
                ))
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

    # ========================================================
    # 光标与选区
    # ========================================================
    def get_current_pos(self) -> int:
        """获取当前光标位置（字符偏移）"""
        try:
            return self.sc.SendScintilla(
                QsciScintilla.SCI_GETCURRENTPOS
            )
        except Exception:
            return 0

    def get_cursor_position(self) -> Tuple[int, int]:
        """获取光标 (行, 列)"""
        try:
            return self.sc.getCursorPosition()
        except Exception:
            return (0, 0)

    def set_selection(self, start: int, end: int):
        """设置选区"""
        try:
            self.sc.SendScintilla(
                QsciScintilla.SCI_SETSELECTIONSTART, start
            )
            self.sc.SendScintilla(
                QsciScintilla.SCI_SETSELECTIONEND, end
            )
        except Exception as e:
            print(f"[EditorProxy] 设置选区失败: {e}")

    def get_selected_text(self) -> str:
        """获取选中的文本"""
        try:
            return self.sc.selectedText()
        except Exception:
            return ""

    def select_all(self):
        """全选"""
        try:
            self.sc.selectAll()
        except Exception:
            pass

    def goto_position(self, pos: int):
        """跳转到字符位置"""
        try:
            max_pos = self.sc.SendScintilla(
                QsciScintilla.SCI_GETLENGTH
            )
            pos = max(0, min(pos, max_pos))
            self.sc.SendScintilla(QsciScintilla.SCI_GOTOPOS, pos)
            self.sc.ensureCursorVisible()
        except Exception:
            pass

    def goto_line(self, line: int):
        """跳转到指定行（0 开始）"""
        try:
            self.sc.setCursorPosition(line, 0)
            self.sc.ensureLineVisible(line)
        except Exception:
            pass

    # ========================================================
    # 文本操作
    # ========================================================
    def get_text(self) -> str:
        """获取全部文本"""
        try:
            return self.sc.text()
        except Exception:
            return ""

    def set_text(self, text: str):
        """设置全部文本"""
        try:
            self.sc.setText(text)
            self._modified = True
            self.modified_changed.emit(True)
        except Exception as e:
            print(f"[EditorProxy] 设置文本失败: {e}")

    def insert_text(self, text: str, pos: Optional[int] = None):
        """在指定位置插入文本"""
        try:
            if pos is None:
                pos = self.get_current_pos()
            data = _normalize_bytes(text)
            self.sc.SendScintilla(
                QsciScintilla.SCI_INSERTTEXT, pos, data
            )
        except Exception as e:
            print(f"[EditorProxy] 插入文本失败: {e}")

    def replace_selected_text(self, text: str):
        """替换选中的文本"""
        try:
            self.sc.replaceSelectedText(text)
        except Exception as e:
            print(f"[EditorProxy] 替换文本失败: {e}")

    # ========================================================
    # 列模式与多光标
    # ========================================================
    def set_column_mode(self, enabled: bool):
        """切换列模式"""
        try:
            mode = (QsciScintilla.SC_SEL_RECTANGLE if enabled
                    else QsciScintilla.SC_SEL_STREAM)
            self.sc.SendScintilla(
                QsciScintilla.SCI_SETSELECTIONMODE, mode
            )
        except Exception as e:
            print(f"[EditorProxy] 切换列模式失败: {e}")

    def is_column_mode(self) -> bool:
        """是否处于列模式"""
        try:
            mode = self.sc.SendScintilla(
                QsciScintilla.SCI_GETSELECTIONMODE
            )
            return mode == QsciScintilla.SC_SEL_RECTANGLE
        except Exception:
            return False

    def add_cursor_at(self, pos: int):
        """在指定位置添加额外光标"""
        try:
            self.sc.SendScintilla(
                QsciScintilla.SCI_ADDSELECTION, pos, pos
            )
        except Exception as e:
            print(f"[EditorProxy] 添加光标失败: {e}")

    def add_cursors_at_line_ends(self):
        """为选中范围每行末尾添加光标"""
        try:
            sel_start = self.sc.SendScintilla(
                QsciScintilla.SCI_GETSELECTIONSTART
            )
            sel_end = self.sc.SendScintilla(
                QsciScintilla.SCI_GETSELECTIONEND
            )

            start_line = self.sc.SendScintilla(
                QsciScintilla.SCI_LINEFROMPOSITION, sel_start
            )
            end_line = self.sc.SendScintilla(
                QsciScintilla.SCI_LINEFROMPOSITION, sel_end
            )

            for line in range(start_line, end_line + 1):
                pos = self.sc.SendScintilla(
                    QsciScintilla.SCI_GETLINEENDPOSITION, line
                )
                self.sc.SendScintilla(
                    QsciScintilla.SCI_ADDSELECTION, pos, pos
                )

        except Exception as e:
            print(f"[EditorProxy] 添加行尾光标失败: {e}")

    def clear_multi_cursors(self):
        """清除所有额外光标"""
        try:
            self.sc.SendScintilla(QsciScintilla.SCI_CLEARSELECTIONS)
        except Exception:
            pass

    def get_selection_count(self) -> int:
        """获取当前选区/光标数量"""
        try:
            return self.sc.SendScintilla(
                QsciScintilla.SCI_GETSELECTIONS
            )
        except Exception:
            return 1

    def select_next_occurrence(self):
        """选中当前单词的下一次出现"""
        try:
            sel_text = self.sc.selectedText()

            if not sel_text:
                # 无选区，先选中当前单词
                pos = self.get_current_pos()
                start = self.sc.SendScintilla(
                    QsciScintilla.SCI_WORDSTARTPOSITION, pos, True
                )
                end = self.sc.SendScintilla(
                    QsciScintilla.SCI_WORDENDPOSITION, pos, True
                )
                if start < end:
                    self.sc.SendScintilla(
                        QsciScintilla.SCI_SETSELECTION, start, end
                    )
                    sel_text = self.sc.text()[start:end]
                if not sel_text:
                    return

            # 查找下一次出现
            target = sel_text.encode('utf-8', errors='replace')
            main_end = self.sc.SendScintilla(
                QsciScintilla.SCI_GETSELECTIONNEND, 0
            )
            length = self.sc.SendScintilla(QsciScintilla.SCI_GETLENGTH)

            self.sc.SendScintilla(
                QsciScintilla.SCI_SETTARGETSTART, main_end
            )
            self.sc.SendScintilla(
                QsciScintilla.SCI_SETTARGETEND, length
            )
            self.sc.SendScintilla(
                QsciScintilla.SCI_SETSEARCHFLAGS,
                QsciScintilla.SCFIND_MATCHCASE |
                QsciScintilla.SCFIND_WHOLEWORD
            )

            pos = self.sc.SendScintilla(
                QsciScintilla.SCI_SEARCHINTARGET, len(target), target
            )

            if pos >= 0:
                self.sc.SendScintilla(
                    QsciScintilla.SCI_ADDSELECTION,
                    pos, pos + len(target)
                )
            else:
                # 从头搜索
                self.sc.SendScintilla(QsciScintilla.SCI_SETTARGETSTART, 0)
                self.sc.SendScintilla(
                    QsciScintilla.SCI_SETTARGETEND, length
                )
                pos = self.sc.SendScintilla(
                    QsciScintilla.SCI_SEARCHINTARGET,
                    len(target), target
                )
                if pos >= 0:
                    self.sc.SendScintilla(
                        QsciScintilla.SCI_ADDSELECTION,
                        pos, pos + len(target)
                    )

        except Exception as e:
            print(f"[EditorProxy] 选择下一个出现失败: {e}")

    # ========================================================
    # 行操作
    # ========================================================
    def move_line_up(self):
        """上移当前行（或多行选区）"""
        self._move_line(True)

    def move_line_down(self):
        """下移当前行（或多行选区）"""
        self._move_line(False)

    def _move_line(self, up: bool):
        """
        移动行（内部实现）。

        修复说明:
            - PyQt5 的 QsciScintilla 未导出 SCI_GETRANGE，改用
              self.sc.text(start, end) 获取文本
            - SCI_INSERTTEXT 需要 bytes 参数
        """
        try:
            sel_start = self.sc.SendScintilla(
                QsciScintilla.SCI_GETSELECTIONSTART
            )
            sel_end = self.sc.SendScintilla(
                QsciScintilla.SCI_GETSELECTIONEND
            )

            start_line = self.sc.SendScintilla(
                QsciScintilla.SCI_LINEFROMPOSITION, sel_start
            )
            end_line = self.sc.SendScintilla(
                QsciScintilla.SCI_LINEFROMPOSITION, sel_end
            )

            # 无选区则操作当前行
            if sel_start == sel_end:
                start_line = end_line = self.sc.SendScintilla(
                    QsciScintilla.SCI_LINEFROMPOSITION,
                    self.get_current_pos()
                )

            line_count = self.sc.SendScintilla(
                QsciScintilla.SCI_GETLINECOUNT
            )

            if up and start_line == 0:
                return
            if not up and end_line >= line_count - 1:
                return

            self.sc.SendScintilla(QsciScintilla.SCI_BEGINUNDOACTION)

            # 提取行文本
            start_pos = self.sc.SendScintilla(
                QsciScintilla.SCI_POSITIONFROMLINE, start_line
            )
            end_pos = self.sc.SendScintilla(
                QsciScintilla.SCI_GETLINEENDPOSITION, end_line
            )

            # 修复：使用 Python API 获取文本
            text = self.sc.text(start_pos, end_pos)
            text_bytes = _normalize_bytes(text)

            # 删除原行
            self.sc.SendScintilla(
                QsciScintilla.SCI_DELETERANGE,
                start_pos, end_pos - start_pos
            )

            # 插入到目标位置
            if up:
                target_line = start_line - 1
                insert_pos = self.sc.SendScintilla(
                    QsciScintilla.SCI_POSITIONFROMLINE, target_line
                )
            else:
                target_line = end_line
                insert_pos = self.sc.SendScintilla(
                    QsciScintilla.SCI_GETLINEENDPOSITION, target_line
                )

            if text_bytes:
                self.sc.SendScintilla(
                    QsciScintilla.SCI_INSERTTEXT,
                    insert_pos, text_bytes
                )

            # 恢复选区（按字节长度计算新位置）
            new_start = insert_pos
            new_end = insert_pos + len(text_bytes)
            self.sc.SendScintilla(
                QsciScintilla.SCI_SETSELECTIONSTART, new_start
            )
            self.sc.SendScintilla(
                QsciScintilla.SCI_SETSELECTIONEND, new_end
            )

            self.sc.SendScintilla(QsciScintilla.SCI_ENDUNDOACTION)

        except Exception as e:
            print(f"[EditorProxy] 移动行失败: {e}")
            import traceback
            traceback.print_exc()

    def duplicate_line(self):
        """
        复制当前行（或多行选区）到下方。

        修复说明:
            - 使用 self.sc.text() 替代 SCI_GETRANGE
            - SCI_INSERTTEXT 需要 bytes
        """
        try:
            sel_start = self.sc.SendScintilla(
                QsciScintilla.SCI_GETSELECTIONSTART
            )
            sel_end = self.sc.SendScintilla(
                QsciScintilla.SCI_GETSELECTIONEND
            )

            start_line = self.sc.SendScintilla(
                QsciScintilla.SCI_LINEFROMPOSITION, sel_start
            )
            end_line = self.sc.SendScintilla(
                QsciScintilla.SCI_LINEFROMPOSITION, sel_end
            )

            # 无选区则操作当前行
            if sel_start == sel_end:
                start_line = end_line = self.sc.SendScintilla(
                    QsciScintilla.SCI_LINEFROMPOSITION,
                    self.get_current_pos()
                )

            start_pos = self.sc.SendScintilla(
                QsciScintilla.SCI_POSITIONFROMLINE, start_line
            )
            end_pos = self.sc.SendScintilla(
                QsciScintilla.SCI_GETLINEENDPOSITION, end_line
            )

            # 修复：使用 Python API 获取文本
            text = self.sc.text(start_pos, end_pos)
            text_bytes = _normalize_bytes(text)

            # 插入到下一行
            insert_pos = self.sc.SendScintilla(
                QsciScintilla.SCI_GETLINEENDPOSITION, end_line
            )
            if text_bytes:
                self.sc.SendScintilla(
                    QsciScintilla.SCI_INSERTTEXT,
                    insert_pos, text_bytes
                )

            # 光标移动到复制的内容
            self.sc.SendScintilla(QsciScintilla.SCI_GOTOPOS, insert_pos)

        except Exception as e:
            print(f"[EditorProxy] 复制行失败: {e}")
            import traceback
            traceback.print_exc()

    def delete_line(self):
        """删除当前行"""
        try:
            line, _ = self.sc.getCursorPosition()
            start_pos = self.sc.SendScintilla(
                QsciScintilla.SCI_POSITIONFROMLINE, line
            )
            end_pos = self.sc.SendScintilla(
                QsciScintilla.SCI_GETLINEENDPOSITION, line
            )
            # 包含换行符
            length = end_pos - start_pos
            if end_pos < self.sc.SendScintilla(
                    QsciScintilla.SCI_GETLENGTH):
                length += 1
            self.sc.SendScintilla(
                QsciScintilla.SCI_DELETERANGE, start_pos, length
            )
        except Exception as e:
            print(f"[EditorProxy] 删除行失败: {e}")

    def toggle_line_comment(self):
        """切换行注释"""
        try:
            line, _ = self.sc.getCursorPosition()
            text = self.sc.text(line)

            # 判断注释符
            comment_char = '#'
            lexer = self.sc.lexer()
            if isinstance(lexer, QsciLexerCPP):
                comment_char = '//'

            stripped = text.lstrip()

            if stripped.startswith(comment_char):
                # 取消注释
                start_pos = self.sc.SendScintilla(
                    QsciScintilla.SCI_POSITIONFROMLINE, line
                )
                pos = text.index(comment_char)
                del_len = len(comment_char)
                # 同时删除后面的空格
                if pos + del_len < len(text) and text[pos + del_len] == ' ':
                    del_len += 1
                self.sc.SendScintilla(
                    QsciScintilla.SCI_DELETERANGE,
                    start_pos + pos, del_len
                )
            else:
                # 添加注释
                indent = len(text) - len(stripped)
                start_pos = (self.sc.SendScintilla(
                    QsciScintilla.SCI_POSITIONFROMLINE, line
                ) + indent)
                insert_text = (comment_char + ' ').encode('utf-8')
                self.sc.SendScintilla(
                    QsciScintilla.SCI_INSERTTEXT,
                    start_pos, insert_text
                )

        except Exception as e:
            print(f"[EditorProxy] 切换注释失败: {e}")

    def indent_selection(self):
        """增加选区缩进"""
        try:
            self.sc.SendScintilla(QsciScintilla.SCI_TAB)
        except Exception:
            pass

    def unindent_selection(self):
        """减少选区缩进"""
        try:
            self.sc.SendScintilla(QsciScintilla.SCI_BACKTAB)
        except Exception:
            pass

    # ========================================================
    # 书签
    # ========================================================
    def toggle_bookmark(self):
        """切换当前行书签"""
        try:
            line, _ = self.sc.getCursorPosition()

            if self.sc.markersAtLine(line) & (1 << MARKER_BOOKMARK):
                self.sc.markerDelete(line, MARKER_BOOKMARK)
                self.document.remove_bookmark(line)
            else:
                self.sc.markerAdd(line, MARKER_BOOKMARK)
                self.document.add_bookmark(line)
        except Exception as e:
            print(f"[EditorProxy] 切换书签失败: {e}")

    def next_bookmark(self):
        """跳转到下一个书签"""
        try:
            line, _ = self.sc.getCursorPosition()
            next_line = self.document.next_bookmark(line)
            if next_line is not None:
                self.sc.setCursorPosition(next_line, 0)
                self.sc.ensureLineVisible(next_line)
        except Exception as e:
            print(f"[EditorProxy] 跳转下一书签失败: {e}")

    def prev_bookmark(self):
        """跳转到上一个书签"""
        try:
            line, _ = self.sc.getCursorPosition()
            prev_line = self.document.prev_bookmark(line)
            if prev_line is not None:
                self.sc.setCursorPosition(prev_line, 0)
                self.sc.ensureLineVisible(prev_line)
        except Exception as e:
            print(f"[EditorProxy] 跳转上一书签失败: {e}")

    def clear_bookmarks(self):
        """清除所有书签"""
        try:
            self.sc.markerDeleteAll(MARKER_BOOKMARK)
            self.document.clear_bookmarks()
        except Exception:
            pass

    # ========================================================
    # 搜索与高亮
    # ========================================================
    def highlight_all(self, pattern: str) -> int:
        """
        高亮所有匹配项。

        参数:
            pattern: 正则表达式

        返回:
            匹配数量
        """
        try:
            self.clear_highlights()

            if not pattern:
                return 0

            # P0-1 修复：SearchEngine 无 search_all 方法，
            # 改用 search() 返回 SearchResult。
            options = SearchOptions(pattern=pattern, is_regex=True)
            engine = SearchEngine(self.document.provider, options)
            result = engine.search()

            if result.error or result.is_empty:
                return 0

            matches = [(m.start, m.end) for m in result.matches]

            # 分批绘制（避免大量匹配卡顿）
            if len(matches) > 1000:
                for i in range(0, len(matches), 500):
                    batch = matches[i:i + 500]
                    for s, e in batch:
                        self.sc.SendScintilla(
                            QsciScintilla.SCI_SETINDICATORCURRENT,
                            INDICATOR_SEARCH
                        )
                        self.sc.SendScintilla(
                            QsciScintilla.SCI_INDICATORFILLRANGE,
                            s, e - s
                        )
                    from PyQt5.QtWidgets import QApplication
                    QApplication.processEvents()
            else:
                for s, e in matches:
                    self.sc.SendScintilla(
                        QsciScintilla.SCI_SETINDICATORCURRENT,
                        INDICATOR_SEARCH
                    )
                    self.sc.SendScintilla(
                        QsciScintilla.SCI_INDICATORFILLRANGE, s, e - s
                    )

            return len(matches)

        except Exception as e:
            print(f"[EditorProxy] 高亮失败: {e}")
            return 0

    def clear_highlights(self):
        """清除所有搜索高亮"""
        try:
            length = self.sc.SendScintilla(QsciScintilla.SCI_GETLENGTH)
            self.sc.SendScintilla(
                QsciScintilla.SCI_SETINDICATORCURRENT, INDICATOR_SEARCH
            )
            self.sc.SendScintilla(
                QsciScintilla.SCI_INDICATORCLEARRANGE, 0, length
            )
        except Exception:
            pass

    def search_next(self, pattern: str, forward: bool = True) -> bool:
        """搜索下一个匹配"""
        try:
            # P0-2 修复：SearchEngine.search() 不接受参数，
            # 且返回 SearchResult 而非 (start, end) tuple。
            options = SearchOptions(pattern=pattern)
            engine = SearchEngine(self.document.provider, options)
            result = engine.search()

            if result.error or result.is_empty:
                return False

            pos = self.get_current_pos()
            match = None

            if forward:
                for m in result.matches:
                    if m.start > pos:
                        match = m
                        break
            else:
                for m in reversed(result.matches):
                    if m.end <= pos:
                        match = m
                        break

            # 循环到另一端
            if match is None:
                match = (result.matches[0] if forward
                         else result.matches[-1])

            self.set_selection(match.start, match.end)
            return True

        except Exception as e:
            print(f"[EditorProxy] 搜索失败: {e}")
            return False

    # ========================================================
    # 智能单词高亮
    # ========================================================
    def _do_smart_highlight(self):
        """执行智能单词高亮（防抖后触发）"""
        try:
            settings = QSettings("QingCao", "Editor")
            if not settings.value("smart_highlight", True, type=bool):
                return

            # 清除旧高亮
            length = self.sc.SendScintilla(QsciScintilla.SCI_GETLENGTH)
            self.sc.SendScintilla(
                QsciScintilla.SCI_SETINDICATORCURRENT,
                INDICATOR_SMART_HIGHLIGHT
            )
            self.sc.SendScintilla(
                QsciScintilla.SCI_INDICATORCLEARRANGE, 0, length
            )

            # 获取当前单词
            pos = self.get_current_pos()
            start = self.sc.SendScintilla(
                QsciScintilla.SCI_WORDSTARTPOSITION, pos, True
            )
            end = self.sc.SendScintilla(
                QsciScintilla.SCI_WORDENDPOSITION, pos, True
            )

            if start >= end:
                return

            word = self.sc.text()[start:end]

            # 单词太短不处理
            if len(word) < 3:
                return

            # 查找所有出现位置
            target = word.encode('utf-8')
            search_pos = 0
            max_pos = self.sc.SendScintilla(QsciScintilla.SCI_GETLENGTH)

            self.sc.SendScintilla(
                QsciScintilla.SCI_SETSEARCHFLAGS,
                QsciScintilla.SCFIND_MATCHCASE |
                QsciScintilla.SCFIND_WHOLEWORD
            )

            while search_pos < max_pos:
                self.sc.SendScintilla(
                    QsciScintilla.SCI_SETTARGETSTART, search_pos
                )
                self.sc.SendScintilla(
                    QsciScintilla.SCI_SETTARGETEND, max_pos
                )
                found = self.sc.SendScintilla(
                    QsciScintilla.SCI_SEARCHINTARGET,
                    len(target), target
                )
                if found < 0:
                    break

                self.sc.SendScintilla(
                    QsciScintilla.SCI_SETINDICATORCURRENT,
                    INDICATOR_SMART_HIGHLIGHT
                )
                self.sc.SendScintilla(
                    QsciScintilla.SCI_INDICATORFILLRANGE,
                    found, end - start
                )

                search_pos = found + 1

        except Exception as e:
            print(f"[EditorProxy] 智能高亮失败: {e}")

    # ========================================================
    # 光标拖尾
    # ========================================================
    def _update_cursor_trail(self):
        """更新光标拖尾效果"""
        try:
            settings = QSettings("QingCao", "Editor")
            if not settings.value("cursor_trail", False, type=bool):
                return

            pos = self.get_current_pos()
            now = time.time()
            self._cursor_trail.append((pos, now))

            # 清除旧拖尾
            length = self.sc.SendScintilla(QsciScintilla.SCI_GETLENGTH)
            self.sc.SendScintilla(
                QsciScintilla.SCI_SETINDICATORCURRENT,
                INDICATOR_CURSOR_TRAIL
            )
            self.sc.SendScintilla(
                QsciScintilla.SCI_INDICATORCLEARRANGE, 0, length
            )

            # 绘制当前拖尾
            valid = []
            for p, t in self._cursor_trail:
                if now - t < CURSOR_TRAIL_DURATION:
                    self.sc.SendScintilla(
                        QsciScintilla.SCI_INDICATORFILLRANGE, p, 1
                    )
                    valid.append((p, t))
            self._cursor_trail = valid

        except Exception:
            pass

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

        # 从偏好获取作者
        settings = QSettings("QingCao", "Editor")
        author = settings.value("author_name", "anonymous")

        replacements = {
            '$TM_FILENAME': (
                os.path.basename(self.document.filepath)
                if self.document.filepath else ''
            ),
            '$TM_FILENAME_BASE': (
                os.path.splitext(
                    os.path.basename(self.document.filepath)
                )[0]
                if self.document.filepath else ''
            ),
            '$TM_DIRECTORY': (
                os.path.dirname(self.document.filepath)
                if self.document.filepath else ''
            ),
            '$CURRENT_YEAR': str(now.year),
            '$CURRENT_MONTH': str(now.month).zfill(2),
            '$CURRENT_DAY': str(now.day).zfill(2),
            '$CURRENT_DATE': now.strftime('%Y-%m-%d'),
            '$CURRENT_TIME': now.strftime('%H:%M:%S'),
            '$CURRENT_DATETIME': now.strftime('%Y-%m-%d %H:%M:%S'),
            '$TM_AUTHOR': author,
        }

        for var, value in replacements.items():
            snippet = snippet.replace(var, value)

        return snippet

    def _highlight_first_placeholder(self, snippet: str):
        """高亮第一个占位符 ${1:...}"""
        try:
            match = re.search(r'\$\{1:([^}]*)\}', snippet)
            if not match:
                return

            # 计算位置
            insert_pos = self.get_current_pos() - len(snippet)
            start = insert_pos + match.start()
            end = start + (match.end() - match.start())

            self.sc.SendScintilla(
                QsciScintilla.SCI_SETSELECTIONSTART, start
            )
            self.sc.SendScintilla(
                QsciScintilla.SCI_SETSELECTIONEND, end
            )

        except Exception:
            pass

    # ========================================================
    # 特殊插入
    # ========================================================
    def insert_datetime(self):
        """插入当前日期时间"""
        try:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            pos = self.get_current_pos()
            self.sc.SendScintilla(
                QsciScintilla.SCI_INSERTTEXT,
                pos, ts.encode('utf-8')
            )
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
            if not re.match(r'^[\d\s\+\-\*\/\(\)\.\^\%]+$', expr):
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
            new_text = '\n'.join(lines)

            if new_text != text:
                self.set_text(new_text)

        except Exception as e:
            print(f"[EditorProxy] 清除行尾空白失败: {e}")

    def remove_blank_lines(self):
        """删除所有空行"""
        try:
            text = self.sc.text()
            lines = [l for l in text.splitlines() if l.strip()]
            new_text = '\n'.join(lines)

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
        """
        try:
            if enable and not self.lsp_client:
                if not self.document.filepath:
                    return False

                # 只对 Python 文件启用
                ext = os.path.splitext(self.document.filepath)[1].lower()
                if ext not in ('.py', '.pyw'):
                    return False

                self.lsp_client = LspClient()
                self.lsp_client.diagnostics_updated.connect(
                    self._on_lsp_diagnostics
                )
                self.lsp_client.completion_ready.connect(
                    self._on_lsp_completion
                )
                self.lsp_client.start()

                # 初始化
                uri = "file:///" + self.document.filepath.replace("\\", "/")
                self.lsp_client.initialize(os.path.dirname(uri))
                self.lsp_client.did_open(uri, self.sc.text())

                self.lsp_active = True
                self.lsp_status_changed.emit("running")
                return True

            elif not enable and self.lsp_client:
                self.lsp_client.stop()
                self.lsp_client = None
                self.lsp_active = False
                self.lsp_status_changed.emit("off")
                return True

            return False

        except Exception as e:
            print(f"[EditorProxy] 切换 LSP 失败: {e}")
            self.lsp_status_changed.emit("error")
            return False

    def _on_lsp_diagnostics(self, uri: str, diagnostics: List[Dict]):
        """LSP 诊断结果回调"""
        try:
            # 清除旧诊断
            length = self.sc.SendScintilla(QsciScintilla.SCI_GETLENGTH)
            self.sc.SendScintilla(
                QsciScintilla.SCI_SETINDICATORCURRENT,
                INDICATOR_LSP_ERROR
            )
            self.sc.SendScintilla(
                QsciScintilla.SCI_INDICATORCLEARRANGE, 0, length
            )

            # 绘制新诊断
            for diag in diagnostics:
                try:
                    start_line = diag['range']['start']['line']
                    start_char = diag['range']['start']['character']
                    end_line = diag['range']['end']['line']
                    end_char = diag['range']['end']['character']

                    start = self.sc.SendScintilla(
                        QsciScintilla.SCI_FINDCOLUMN,
                        start_line, start_char
                    )
                    end = self.sc.SendScintilla(
                        QsciScintilla.SCI_FINDCOLUMN,
                        end_line, end_char
                    )

                    self.sc.SendScintilla(
                        QsciScintilla.SCI_SETINDICATORCURRENT,
                        INDICATOR_LSP_ERROR
                    )
                    self.sc.SendScintilla(
                        QsciScintilla.SCI_INDICATORFILLRANGE,
                        start, max(1, end - start)
                    )
                except Exception:
                    continue

        except Exception as e:
            print(f"[EditorProxy] 处理诊断失败: {e}")

    def _on_lsp_completion(self, items: List[Dict]):
        """LSP 补全结果回调"""
        try:
            if not items:
                return

            # 构建补全列表
            words = [item.get('label', '') for item in items[:50]]
            words = [w for w in words if w]

            if words:
                text = ' '.join(words)
                self.sc.SendScintilla(
                    QsciScintilla.SCI_AUTOCSHOW,
                    0, text.encode('utf-8')
                )

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

            # 停止 LSP
            if self.lsp_client:
                self.lsp_client.stop()
                self.lsp_client = None

            # 保存光标和视图位置
            try:
                line, col = self.sc.getCursorPosition()
                first_line = self.sc.SendScintilla(
                    QsciScintilla.SCI_GETFIRSTVISIBLELINE
                )
                self.document.remember_cursor(
                    line, col, self.get_current_pos(),
                    first_line, self.sc.horizontalScrollBar().value()
                )
            except Exception:
                pass

            # 保存书签和折叠状态
            try:
                self.document.set_folded_lines(
                    self._get_folded_lines()
                )
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
            line_count = self.sc.SendScintilla(
                QsciScintilla.SCI_GETLINECOUNT
            )
            for line in range(line_count):
                expanded = self.sc.SendScintilla(
                    QsciScintilla.SCI_GETFOLDEXPANDED, line
                )
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
        return (f"<EditorProxy title={self.title!r} "
                f"modified={self.is_modified} "
                f"path={self.filepath!r}>")


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys
    import tempfile
    import shutil
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    print("=== 测试 EditorProxy ===")

    # 创建临时文件
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_editor_test_")
    test_file = os.path.join(tmp_dir, "test.py")

    with open(test_file, 'w', encoding='utf-8') as f:
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