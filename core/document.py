#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为文档模型模块，包含：
- Document：文档对象（封装提供者 + 元数据）
- DocumentModel：文档模型（多文档管理）
- DocumentMetadata：文档元数据
- DocumentState：文档状态枚举
- 行索引与位置映射
- 书签管理
- 折叠状态管理
- 光标与选区记忆
- 文档修改追踪
- 文档重命名与另存
- 文档比较与合并
- 文档缓存与资源释放
- 事件总线联动

修复记录:
- set_text: 保留原 provider，原地更新内容（不替换为 MemoryProvider）
- save: 将 meta.filepath 显式传给 provider，确保真正写盘
- _on_file_changed: 增加 hasattr 双保险，兼容缺失 check_external_change 的 provider
- _replace_full_content: 统一分块写入逻辑，供 set_text 使用
"""

import datetime
import hashlib
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import QFileSystemWatcher, QObject, QTimer, pyqtSignal

from app.event_bus import (
    FileClosedEvent,
    FileEncodingChangedEvent,
    FileModifiedEvent,
    FileOpenedEvent,
    FileReloadedEvent,
    FileSavedEvent,
    StatusMessageEvent,
    bus,
)
from core.content_provider import (
    HUGE_FILE_THRESHOLD,
    LARGE_FILE_THRESHOLD,
    ContentProvider,
    FileState,
    LocalFileProvider,
    MemoryProvider,
    ProviderFactory,
    detect_file_encoding,
    detect_file_eol,
    get_file_hash,
    is_binary_file,
)


# ============================================================
# 常量
# ============================================================
DEFAULT_ENCODING = 'utf-8'
DEFAULT_EOL = '\n'
MAX_LINE_INDEX_CACHE = 100000   # 行索引缓存的最大行数
AUTO_SAVE_DRAFT_INTERVAL = 60   # 草稿自动保存间隔（秒）


# ============================================================
# 文档状态枚举
# ============================================================
class DocumentState(Enum):
    """文档状态"""
    NEW = auto()           # 新建未保存
    CLEAN = auto()         # 已保存，无修改
    MODIFIED = auto()      # 已修改
    SAVING = auto()        # 保存中
    LOADING = auto()       # 加载中
    READONLY = auto()      # 只读
    ERROR = auto()         # 错误
    CLOSED = auto()        # 已关闭


# ============================================================
# 文档元数据
# ============================================================
@dataclass
class DocumentMetadata:
    """文档元数据"""
    # 基本
    filepath: Optional[str] = None
    title: str = "未命名"
    encoding: str = DEFAULT_ENCODING
    eol: str = DEFAULT_EOL
    has_bom: bool = False

    # 文件属性
    size: int = 0
    mtime: float = 0.0
    created_at: float = field(default_factory=time.time)
    last_modified_at: float = field(default_factory=time.time)
    last_saved_at: float = 0.0

    # 会话相关
    cursor_line: int = 0
    cursor_col: int = 0
    cursor_pos: int = 0
    first_visible_line: int = 0
    scroll_x: int = 0

    # 编辑状态
    modified: bool = False
    readonly: bool = False

    # 权限
    writable: bool = True

    # 统计
    line_count: int = 0
    char_count: int = 0

    # 语言
    language: str = ""

    # 自定义
    tags: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            'filepath': self.filepath,
            'title': self.title,
            'encoding': self.encoding,
            'eol': self.eol,
            'has_bom': self.has_bom,
            'size': self.size,
            'mtime': self.mtime,
            'created_at': self.created_at,
            'last_modified_at': self.last_modified_at,
            'last_saved_at': self.last_saved_at,
            'cursor_line': self.cursor_line,
            'cursor_col': self.cursor_col,
            'cursor_pos': self.cursor_pos,
            'first_visible_line': self.first_visible_line,
            'scroll_x': self.scroll_x,
            'modified': self.modified,
            'readonly': self.readonly,
            'line_count': self.line_count,
            'char_count': self.char_count,
            'language': self.language,
            'tags': list(self.tags),
            'notes': self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'DocumentMetadata':
        """从字典反序列化"""
        meta = cls()
        for key, value in d.items():
            if hasattr(meta, key):
                setattr(meta, key, value)
        return meta


# ============================================================
# 文档对象
# ============================================================
class Document(QObject):
    """
    文档对象。

    封装一个内容提供者（ContentProvider）和文档元数据。
    提供行索引、书签、折叠、修改追踪等高级功能。

    信号:
        modified_changed(bool): 修改状态变更
        saved(str): 保存成功（文件路径）
        reloaded(str): 重新加载（文件路径）
        encoding_changed(str, str): 编码变更（旧, 新）
        external_change_detected(str): 检测到外部修改
        bookmarks_changed(): 书签变更
        folds_changed(): 折叠状态变更
    """

    modified_changed = pyqtSignal(bool)
    saved = pyqtSignal(str)
    reloaded = pyqtSignal(str)
    encoding_changed = pyqtSignal(str, str)
    external_change_detected = pyqtSignal(str)
    # 文档关联的文件路径发生变化（另存为）
    #
    # 为什么需要（INV-L1/L2 修复）：
    #   另存为会更新 `meta.filepath`，但**依赖路径的外部状态**（例如
    #   EditorProxy 的 LSP document URI）必须同步更新。原先没有任何通知
    #   机制，只能在某个具体入口里手动补 —— 而"另存为"存在多条入口
    #   （`EditorProxy.save_file(path)`、`Document.save(path)`），
    #   漏掉任何一条就会出现"内容存到新文件、LSP 仍操作旧文档"。
    #   改为由 Document 在路径真正变化时**统一广播**，调用方无需各自记得。
    filepath_changed = pyqtSignal(str)
    bookmarks_changed = pyqtSignal()
    folds_changed = pyqtSignal()

    def __init__(self, provider: Optional[ContentProvider] = None,
                 parent: Optional[QObject] = None):
        super().__init__(parent)

        # 内容提供者
        self.provider: Optional[ContentProvider] = provider

        # 元数据
        self.meta: DocumentMetadata = DocumentMetadata()

        # 状态
        self._state: DocumentState = DocumentState.NEW

        # 书签（行号集合）
        self._bookmarks: set = set()

        # 折叠状态（行号集合）
        self._folded_lines: set = set()

        # 行索引缓存（行号 -> 起始字符位置）
        self._line_index: Optional[List[int]] = None
        self._line_index_dirty: bool = True

        # 文件监听器
        self._file_watcher: Optional[QFileSystemWatcher] = None

        # 草稿自动保存定时器
        self._draft_timer = QTimer(self)
        self._draft_timer.setInterval(AUTO_SAVE_DRAFT_INTERVAL * 1000)
        self._draft_timer.timeout.connect(self._save_draft)

        # 关联的编辑器（弱引用）
        self._editors: List[Any] = []

    # ========================================================
    # 打开与关闭
    # ========================================================
    def open(self, filepath: str, encoding: Optional[str] = None,
             readonly: bool = False, detect_encoding: bool = True) -> bool:
        """
        打开文件。

        参数:
            filepath: 文件路径
            encoding: 指定编码
            readonly: 只读模式
            detect_encoding: 是否自动检测编码

        返回:
            是否成功
        """
        self._state = DocumentState.LOADING

        try:
            # 创建本地文件提供者
            provider = LocalFileProvider()
            provider.open(
                filepath,
                encoding=encoding,
                readonly=readonly,
                detect_encoding=detect_encoding
            )
            # 释放旧 provider
            #
            # 修复（句柄/映射泄漏）：原先直接覆盖 `self.provider`，**从不
            # 关闭旧的** —— 旧 provider 的文件句柄与内存映射一直存活。
            # Windows 上这会**阻止外部程序覆盖该文件**，从而让"外部变更
            # 检测"永远不可用；反复打开文件还会持续累积句柄。
            _old_provider = self.provider
            self.provider = provider
            if _old_provider is not None and _old_provider is not provider:
                try:
                    _old_provider.close()
                except Exception as e:
                    print(f"[Document] 关闭旧 provider 失败: {e}")

            # 更新元数据
            self.meta = DocumentMetadata()
            self.meta.filepath = os.path.abspath(filepath)
            self.meta.title = os.path.basename(filepath)
            self.meta.encoding = provider.encoding
            self.meta.eol = provider.eol
            self.meta.has_bom = provider.has_bom
            self.meta.size = provider.size
            self.meta.mtime = provider.mtime
            self.meta.readonly = provider.readonly
            self.meta.writable = not provider.readonly
            self.meta.language = self._detect_language(filepath)

            # 更新状态
            self._state = (DocumentState.READONLY if provider.readonly
                           else DocumentState.CLEAN)

            # 初始化监听器
            self._setup_file_watcher(filepath)

            # 清空缓存
            self._invalidate_line_index()
            self._bookmarks.clear()
            self._folded_lines.clear()

            return True

        except Exception as e:
            self._state = DocumentState.ERROR
            print(f"[Document] 打开失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def open_from_text(self, text: str, title: str = "未命名",
                       encoding: str = DEFAULT_ENCODING) -> bool:
        """
        从文本创建新文档（未保存）。

        参数:
            text: 初始文本
            title: 文档标题
            encoding: 编码
        """
        self._state = DocumentState.NEW

        provider = MemoryProvider()
        provider.open(initial_text=text, encoding=encoding)
        self.provider = provider

        self.meta = DocumentMetadata()
        self.meta.filepath = None
        self.meta.title = title
        self.meta.encoding = encoding
        self.meta.eol = DEFAULT_EOL
        self.meta.size = len(text.encode(encoding))
        self.meta.writable = True
        self.meta.modified = bool(text)

        self._invalidate_line_index()

        if text:
            self._state = DocumentState.MODIFIED
            self.meta.modified = True

        return True

    def close(self):
        """关闭文档并释放资源"""
        # 停止定时器
        self._draft_timer.stop()

        # 移除文件监听
        self._remove_file_watcher()

        # 关闭提供者
        if self.provider:
            try:
                self.provider.close()
            except Exception:
                pass
            self.provider = None

        # 清空缓存
        self._bookmarks.clear()
        self._folded_lines.clear()
        self._invalidate_line_index()

        self._state = DocumentState.CLOSED

    # ========================================================
    # 保存
    # ========================================================
    def save(self, filepath: Optional[str] = None) -> bool:
        """
        保存文档。

        参数:
            filepath: 另存为路径（None 则保存到原路径）

        返回:
            是否成功

        修复说明:
            - 显式将目标路径传给 provider，避免 MemoryProvider
              在 filepath=None 时静默不写盘。
        """
        if not self.provider:
            print("[Document] 保存失败: provider 为 None")
            return False

        # 确定目标路径
        target = filepath or self.meta.filepath
        if not target:
            print("[Document] 保存失败: 无目标路径")
            return False

        target = os.path.abspath(target)

        self._state = DocumentState.SAVING

        try:
            # 更新编码到 provider
            self.provider.encoding = self.meta.encoding

            # 关键修复：把 target 传给 provider
            # - 若 target 与原路径相同：写脏块
            # - 若 target 不同：另存为完整文件
            success = self.provider.save(target)

            if success:
                # 更新元数据
                is_save_as = (
                    self.meta.filepath is None or
                    os.path.abspath(self.meta.filepath) != target
                )

                if is_save_as:
                    self.meta.filepath = target
                    self.meta.title = os.path.basename(target)
                    self.meta.language = self._detect_language(target)
                    self._setup_file_watcher(target)
                    # 统一广播路径变化：依赖路径的外部状态（LSP URI 等）
                    # 必须跟着换。原先无通知机制，只能由各调用点自行补，
                    # 漏掉任一条入口就会出现"内容存新文件、LSP 操作旧文档"。
                    try:
                        self.filepath_changed.emit(target)
                    except Exception:
                        pass

                self.meta.modified = False
                self.meta.last_saved_at = time.time()
                self.meta.size = self.provider.size

                try:
                    self.meta.mtime = os.path.getmtime(target)
                except Exception:
                    pass

                # 更新状态
                self._state = (DocumentState.READONLY if self.meta.readonly
                               else DocumentState.CLEAN)

                # 停止草稿定时器
                self._draft_timer.stop()

                # 删除草稿
                try:
                    self.delete_draft()
                except Exception:
                    pass

                # 发射信号
                self.modified_changed.emit(False)
                self.saved.emit(self.meta.filepath or "")

                return True
            else:
                self._state = DocumentState.MODIFIED
                print("[Document] provider.save 返回 False")
                return False

        except Exception as e:
            self._state = DocumentState.MODIFIED
            print(f"[Document] 保存失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def save_as(self, filepath: str) -> bool:
        """另存为"""
        return self.save(filepath)

    # ========================================================
    # 重新加载
    # ========================================================
    def reload(self) -> bool:
        """重新加载文件"""
        if not self.meta.filepath:
            return False

        try:
            # 双保险：检查 provider 是否有 reload 方法
            if not hasattr(self.provider, 'reload'):
                return False

            success = self.provider.reload()
            if success:
                self.meta.modified = False
                self.meta.encoding = self.provider.encoding
                self.meta.eol = self.provider.eol
                self.meta.size = self.provider.size
                self.meta.mtime = self.provider.mtime

                self._state = (DocumentState.READONLY if self.meta.readonly
                               else DocumentState.CLEAN)

                self._invalidate_line_index()

                self.modified_changed.emit(False)
                self.reloaded.emit(self.meta.filepath)

                return True
        except Exception as e:
            print(f"[Document] 重新加载失败: {e}")

        return False

    # ========================================================
    # 修改追踪
    # ========================================================
    def mark_modified(self):
        """标记为已修改"""
        if self._state in (DocumentState.READONLY, DocumentState.CLOSED):
            return

        if not self.meta.modified:
            self.meta.modified = True
            self.meta.last_modified_at = time.time()
            self._state = DocumentState.MODIFIED
            self.modified_changed.emit(True)

            # 启动草稿保存
            if not self._draft_timer.isActive():
                self._draft_timer.start()

            # 发射事件
            try:
                bus.emit_event(FileModifiedEvent(
                    path=self.meta.filepath or ""
                ))
            except Exception:
                pass

    def mark_saved(self):
        """标记为已保存"""
        if self.meta.modified:
            self.meta.modified = False
            self.meta.last_saved_at = time.time()
            self._state = (DocumentState.READONLY if self.meta.readonly
                           else DocumentState.CLEAN)
            self.modified_changed.emit(False)

            # 停止草稿定时器
            self._draft_timer.stop()

    @property
    def is_modified(self) -> bool:
        return self.meta.modified

    @property
    def state(self) -> DocumentState:
        return self._state

    @property
    def is_readonly(self) -> bool:
        return self.meta.readonly

    @property
    def is_new(self) -> bool:
        """是否为新文档（未保存过）"""
        return self.meta.filepath is None

    @property
    def filepath(self) -> Optional[str]:
        return self.meta.filepath

    @property
    def title(self) -> str:
        return self.meta.title

    @property
    def encoding(self) -> str:
        return self.meta.encoding

    @encoding.setter
    def encoding(self, value: str):
        if self.meta.encoding != value:
            old = self.meta.encoding
            self.meta.encoding = value
            if self.provider:
                self.provider.encoding = value
            self.encoding_changed.emit(old, value)

    @property
    def enc(self) -> str:
        """
        [已弃用] 兼容旧 API：编码别名。

        早期代码通过 `document.enc` 访问编码，
        新代码应使用 `document.encoding`。
        """
        return self.meta.encoding

    @enc.setter
    def enc(self, value: str):
        """[已弃用] 兼容旧 API：编码别名 setter。"""
        self.encoding = value

    # ========================================================
    # 编码检测
    # ========================================================
    def detect_encoding(self) -> str:
        """重新检测文件编码"""
        if not self.meta.filepath:
            return self.meta.encoding

        new_encoding = detect_file_encoding(self.meta.filepath)
        if new_encoding != self.meta.encoding:
            old = self.meta.encoding
            self.meta.encoding = new_encoding
            self.encoding_changed.emit(old, new_encoding)
        return new_encoding

    def change_encoding(self, encoding: str, reload: bool = True) -> bool:
        """
        切换编码并重新加载。

        参数:
            encoding: 目标编码
            reload: 是否重新读取文件内容
        """
        old = self.meta.encoding
        self.meta.encoding = encoding

        if self.provider:
            self.provider.encoding = encoding

        if reload and self.meta.filepath:
            try:
                if hasattr(self.provider, 'reload'):
                    re_ok = self.provider.reload()
            except Exception:
                re_ok = False
            else:
                # 关键（INV-C 修复）：重载之后必须**通知编辑器刷新**。
                #
                # 缺陷背景（审计测试复现）：
                #   `change_encoding` 重载了 provider（文本已按新编码正确
                #   解码），但没有任何代码把新文本写回 `EditorProxy.sc`
                #   —— 于是编辑器**继续显示旧编码解出的乱码**，而 provider
                #   已是正确文本。两者不一致时，任何基于 provider 的功能
                #   （查找/替换/另存为/全局替换）看到的是另一份内容。
                #
                #   发出 `reloaded` 信号，由 EditorProxy 负责把文本同步回
                #   编辑器（core 层不应直接操作 QScintilla）。
                if re_ok:
                    try:
                        self.reloaded.emit(self.meta.filepath or "")
                    except Exception:
                        pass

        self.encoding_changed.emit(old, encoding)
        return True

    # ========================================================
    # 行尾符
    # ========================================================
    def set_eol(self, eol: str):
        """设置行尾符（用户显式切换；实际转换在保存时由 provider 完成）

        修复（INV-E1，审计测试复现）：
            原先只改 `meta.eol` + 标脏。而保存路径写入时读的是
            **`provider._eol`**（见 `ContentProvider._apply_eol`），
            两者不同步 → 用户在状态栏切了 LF→CRLF，保存后磁盘仍是 LF。

            这里显式同步到 provider，并**标记为"用户显式指定"**：
            只有显式指定过才在保存时做行尾转换。否则会影响那些
            "探测结果本身不可靠"的文件（例如整篇没有换行的文件，
            `_detect_eol` 在 0 比 0 时默认取 CRLF，若照样转换，
            保存会把**原文没有的换行**也改写掉）。
        """
        self.meta.eol = eol
        try:
            if self.provider is not None:
                self.provider._eol = eol
                self.provider._eol_explicit = True
        except Exception as e:
            print(f"[Document] 同步行尾符到 provider 失败: {e}")
        self.mark_modified()

    def detect_eol(self) -> str:
        """检测文件行尾符"""
        if not self.meta.filepath:
            return self.meta.eol
        self.meta.eol = detect_file_eol(self.meta.filepath)
        return self.meta.eol

    def convert_eol(self, target: str) -> int:
        """
        转换行尾符。

        参数:
            target: 目标行尾符（'\\n' / '\\r\\n' / '\\r'）

        返回:
            替换的数量
        """
        if not self.provider:
            return 0

        current = self.meta.eol
        if current == target:
            return 0

        try:
            text = self.provider.read_text()
            # 规范化后转换
            text = text.replace('\r\n', '\n').replace('\r', '\n')
            if target == '\r\n':
                text = text.replace('\n', '\r\n')
            elif target == '\r':
                text = text.replace('\n', '\r')

            # 写回
            self._replace_full_content(text)
            self.meta.eol = target
            self.mark_modified()

            return text.count(target)
        except Exception as e:
            print(f"[Document] 转换行尾符失败: {e}")
            return 0

    # ========================================================
    # 内容操作
    # ========================================================
    def get_text(self) -> str:
        """获取全文"""
        if not self.provider:
            return ""
        return self.provider.read_text()

    def set_text(self, text: str):
        """
        设置全文（原地更新 provider 内容，不替换 provider）。

        修复说明:
            旧实现用 MemoryProvider 替换现有 provider，导致：
            - LocalFileProvider 被丢弃
            - 后续 save() 无法写回原文件
            新实现直接在现有 provider 上写内容。
        """
        if self.provider is None:
            # 无 provider：新建内存 provider
            provider = MemoryProvider()
            provider.open(initial_text=text, encoding=self.meta.encoding)
            self.provider = provider
        else:
            # 有 provider：原地更新内容
            self._replace_full_content(text)

        self.mark_modified()
        self._invalidate_line_index()

    def _replace_full_content(self, text: str):
        """
        替换 provider 的全部内容（内部用）。

        分块写入 + 更新 provider 元数据。
        """
        if not self.provider:
            return

        encoded = self.provider.encode(text)
        new_size = len(encoded)

        # 清空旧脏块
        self.provider.clear_dirty()

        # 计算块数
        block_size = self.provider.block_size
        total_blocks = max(
            1, (new_size + block_size - 1) // block_size
        )

        # A5 修复：先更新 provider 元数据，再写块。
        # write_block 会校验 `block_id < self._total_blocks`，
        # 若元数据仍是旧值（例如内容从 1 块变长到 2 块），
        # 新块会被**静默拒绝** → 内容被截断为旧长度。
        if hasattr(self.provider, '_total_blocks'):
            self.provider._total_blocks = total_blocks
        if hasattr(self.provider, '_size'):
            self.provider._size = new_size

        # 分块写入
        for bid in range(total_blocks):
            start = bid * block_size
            end = min(start + block_size, new_size)
            self.provider.write_block(bid, encoded[start:end])

        # 更新 meta
        self.meta.size = new_size

        self._invalidate_line_index()

    # ========================================================
    # 行索引
    # ========================================================
    def _invalidate_line_index(self):
        """使行索引失效"""
        self._line_index = None
        self._line_index_dirty = True

    def build_line_index(self) -> List[int]:
        """
        构建行索引（每行起始字符位置）。

        返回:
            行索引列表，索引 i 表示第 i 行在文本中的起始位置
        """
        if self._line_index is not None and not self._line_index_dirty:
            return self._line_index

        if not self.provider:
            self._line_index = [0]
            self._line_index_dirty = False
            return self._line_index

        text = self.provider.read_text()
        index = [0]
        for i, char in enumerate(text):
            if char == '\n':
                index.append(i + 1)

        self._line_index = index
        self._line_index_dirty = False
        self.meta.line_count = len(index)

        return index

    def get_line_count(self) -> int:
        """获取总行数"""
        return len(self.build_line_index())

    def get_line_start(self, line: int) -> int:
        """获取指定行的起始字符位置"""
        index = self.build_line_index()
        if 0 <= line < len(index):
            return index[line]
        return -1

    def get_line_end(self, line: int) -> int:
        """获取指定行的结束位置（不含换行符）"""
        index = self.build_line_index()
        if 0 <= line < len(index) - 1:
            return index[line + 1] - 1
        elif line == len(index) - 1 and self.provider:
            return self.provider.size
        return -1

    def get_line_text(self, line: int) -> str:
        """获取指定行的文本"""
        start = self.get_line_start(line)
        end = self.get_line_end(line)
        if start < 0 or end < 0:
            return ""
        text = self.get_text()
        return text[start:end]

    def get_position_line_col(self, position: int) -> Tuple[int, int]:
        """
        将字符位置转换为 (行, 列)。

        参数:
            position: 字符偏移

        返回:
            (行号, 列号)，均从 0 开始
        """
        index = self.build_line_index()
        if position <= 0:
            return (0, 0)

        # 二分查找
        import bisect
        line = bisect.bisect_right(index, position) - 1
        col = position - index[line]
        return (line, col)

    def get_position(self, line: int, col: int) -> int:
        """将 (行, 列) 转换为字符位置"""
        index = self.build_line_index()
        if line < 0:
            return 0
        if line >= len(index):
            return self.provider.size if self.provider else 0
        return index[line] + col

    # ========================================================
    # 书签管理
    # ========================================================
    def add_bookmark(self, line: int):
        """添加书签"""
        self._bookmarks.add(line)
        self.bookmarks_changed.emit()

    def remove_bookmark(self, line: int):
        """移除书签"""
        self._bookmarks.discard(line)
        self.bookmarks_changed.emit()

    def toggle_bookmark(self, line: int) -> bool:
        """
        切换书签状态。

        返回:
            True 表示已添加，False 表示已移除
        """
        if line in self._bookmarks:
            self._bookmarks.discard(line)
            self.bookmarks_changed.emit()
            return False
        else:
            self._bookmarks.add(line)
            self.bookmarks_changed.emit()
            return True

    def has_bookmark(self, line: int) -> bool:
        """检查指定行是否有书签"""
        return line in self._bookmarks

    def clear_bookmarks(self):
        """清除所有书签"""
        self._bookmarks.clear()
        self.bookmarks_changed.emit()

    def get_bookmarks(self) -> List[int]:
        """获取所有书签行号（排序）"""
        return sorted(self._bookmarks)

    def next_bookmark(self, from_line: int) -> Optional[int]:
        """获取下一个书签行号"""
        for line in sorted(self._bookmarks):
            if line > from_line:
                return line
        # 循环
        if self._bookmarks:
            return min(self._bookmarks)
        return None

    def prev_bookmark(self, from_line: int) -> Optional[int]:
        """获取上一个书签行号"""
        for line in sorted(self._bookmarks, reverse=True):
            if line < from_line:
                return line
        # 循环
        if self._bookmarks:
            return max(self._bookmarks)
        return None

    # ========================================================
    # 折叠状态管理
    # ========================================================
    def set_folded_lines(self, lines: List[int]):
        """设置折叠行列表"""
        self._folded_lines = set(lines)
        self.folds_changed.emit()

    def get_folded_lines(self) -> List[int]:
        """获取折叠行列表"""
        return sorted(self._folded_lines)

    def add_fold(self, line: int):
        """添加折叠"""
        self._folded_lines.add(line)
        self.folds_changed.emit()

    def remove_fold(self, line: int):
        """移除折叠"""
        self._folded_lines.discard(line)
        self.folds_changed.emit()

    def toggle_fold(self, line: int) -> bool:
        """切换折叠状态"""
        if line in self._folded_lines:
            self._folded_lines.discard(line)
            self.folds_changed.emit()
            return False
        else:
            self._folded_lines.add(line)
            self.folds_changed.emit()
            return True

    def is_folded(self, line: int) -> bool:
        """检查指定行是否折叠"""
        return line in self._folded_lines

    def clear_folds(self):
        """清除所有折叠"""
        self._folded_lines.clear()
        self.folds_changed.emit()

    # ========================================================
    # 光标记忆
    # ========================================================
    def remember_cursor(self, line: int, col: int, position: int = 0,
                        first_visible_line: int = 0, scroll_x: int = 0):
        """记住光标位置"""
        self.meta.cursor_line = line
        self.meta.cursor_col = col
        self.meta.cursor_pos = position
        self.meta.first_visible_line = first_visible_line
        self.meta.scroll_x = scroll_x

    def get_remembered_cursor(self) -> Tuple[int, int, int]:
        """获取记住的光标位置"""
        return (self.meta.cursor_line, self.meta.cursor_col,
                self.meta.cursor_pos)

    def get_remembered_view(self) -> Tuple[int, int]:
        """获取记住的视图位置"""
        return (self.meta.first_visible_line, self.meta.scroll_x)

    # ========================================================
    # 文件监听
    # ========================================================
    def _setup_file_watcher(self, filepath: str):
        """设置文件变更监听"""
        self._remove_file_watcher()

        if not filepath or not os.path.exists(filepath):
            return

        try:
            self._file_watcher = QFileSystemWatcher(self)
            self._file_watcher.addPath(filepath)
            self._file_watcher.fileChanged.connect(self._on_file_changed)
        except Exception as e:
            print(f"[Document] 设置文件监听失败: {e}")

    def _remove_file_watcher(self):
        """移除文件监听"""
        if self._file_watcher:
            try:
                self._file_watcher.deleteLater()
            except Exception:
                pass
            self._file_watcher = None

    def _on_file_changed(self, path: str):
        """
        文件变更回调。

        修复说明:
            - 使用 hasattr 双保险，即使 provider 未实现
              check_external_change 也不会崩溃
        """
        # 重新添加监听（某些系统上文件变更后需要重新添加）
        if self._file_watcher and path not in self._file_watcher.files():
            try:
                self._file_watcher.addPath(path)
            except Exception:
                pass

        # 检查 mtime（双保险）
        try:
            if not self.provider:
                return

            # 基类提供默认实现，子类可覆盖
            if hasattr(self.provider, 'check_external_change'):
                if self.provider.check_external_change():
                    self.external_change_detected.emit(path)
            # 若方法不存在，静默忽略（内存 provider 无外部文件）
        except Exception as e:
            print(f"[Document] 检查外部变更失败: {e}")

    # ========================================================
    # 草稿自动保存
    # ========================================================
    # ========================================================
    # 草稿目录（P1 修复：统一路径 + 补齐读取端）
    # ========================================================
    @staticmethod
    def _draft_dir() -> str:
        """草稿目录（**绝对路径**，全模块唯一来源）

        缺陷背景（已核实）：
            原先 `_save_draft` 与 `delete_draft` 各自拼一份相对路径
            `<仓库>/backup/drafts`，而 `main.py` 的 ensure_directories
            建的是 `<DATA_DIR>/drafts`（即 `data/drafts`）——
            两套路径互不相认。改为统一走应用根目录。
        """
        try:
            from infrastructure.plugin_loader import app_root_dir
            base = app_root_dir()
        except Exception:  # pragma: no cover
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "backup", "drafts")

    @staticmethod
    def _draft_name(filepath: Optional[str]) -> str:
        """由文件路径推导草稿文件名（无路径时返回空串）"""
        if not filepath:
            return ""
        return hashlib.md5(filepath.encode('utf-8')).hexdigest()[:16] + ".draft"

    def draft_path(self) -> Optional[str]:
        """当前文档的草稿文件路径（未命名文档返回 None）"""
        name = self._draft_name(self.meta.filepath)
        if not name:
            return None
        return os.path.join(self._draft_dir(), name)

    @staticmethod
    def read_draft(path: str):
        """读取草稿文件，返回 (原文路径, 正文) ；无法解析时返回 (None, None)

        格式（由 `_save_draft` 写入）::

            # QingCao Draft
            # Original: <路径或 (未命名)>
            # Saved: <ISO 时间>
            # Encoding: <编码>
            # ---
            <正文>

        返回:
            (original_path_or_empty, text) 或 (None, None)
        """
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                head = [f.readline() for _ in range(5)]
                text = f.read()
        except Exception:
            return None, None

        if not head or not head[0].startswith("# QingCao Draft"):
            return None, None

        original = ""
        for line in head[1:4]:
            if line.startswith("# Original:"):
                original = line.split(":", 1)[1].strip()
        if original == "(未命名)":
            original = ""
        return original, text

    @classmethod
    def list_drafts(cls) -> list:
        """列出所有草稿，返回 [(路径, 原文路径, 正文, mtime)]（按时间倒序）"""
        out = []
        d = cls._draft_dir()
        if not os.path.isdir(d):
            return out
        for name in os.listdir(d):
            if not name.endswith(".draft"):
                continue
            p = os.path.join(d, name)
            original, text = cls.read_draft(p)
            if text is None:
                continue
            try:
                mt = os.path.getmtime(p)
            except OSError:
                mt = 0.0
            out.append((p, original or "", text, mt))
        out.sort(key=lambda x: x[3], reverse=True)
        return out

    def _save_draft(self):
        """保存草稿到临时目录"""
        if not self.meta.modified:
            self._draft_timer.stop()
            return

        # 防御：provider 未打开时静默跳过，避免无意义的错误日志
        if not self.provider or not self.provider.is_open:
            self._draft_timer.stop()
            return

        try:
            draft_dir = self._draft_dir()
            os.makedirs(draft_dir, exist_ok=True)

            # 使用文件路径哈希作为草稿名
            # 未命名文档：原先用 `id(self)`（内存地址，每次运行都变）会被
            # `delete_draft()`（无 filepath 直接 return）永久遗弃成孤儿。
            # 现改为按标签序号稳定命名，与 autosave 的 untitled_N 对齐。
            if self.meta.filepath:
                name = self._draft_name(self.meta.filepath)
            else:
                name = "untitled_%d.draft" % getattr(self, '_untitled_index', 0)

            draft_file = os.path.join(draft_dir, name)

            # 原子写：先前缀临时文件，成功后替换，避免写一半留下坏草稿
            tmp_file = draft_file + ".tmp"
            with open(tmp_file, 'w', encoding='utf-8') as f:
                f.write("# QingCao Draft\n")
                f.write(f"# Original: {self.meta.filepath or '(未命名)'}\n")
                f.write(f"# Saved: {datetime.datetime.now().isoformat()}\n")
                f.write(f"# Encoding: {self.meta.encoding}\n")
                f.write("# ---\n")
                f.write(self.get_text())
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, draft_file)

        except Exception as e:
            print(f"[Document] 草稿保存失败: {e}")

    def delete_draft(self):
        """删除当前文档的草稿文件

        注意：调用方必须确保"内容已确实保存成功"，否则会丢掉唯一的
        崩溃恢复副本（见 `close_document` 的修复说明）。
        """
        draft_file = self.draft_path()
        if not draft_file:
            return
        try:
            if os.path.exists(draft_file):
                os.remove(draft_file)
        except Exception:
            pass

    # ========================================================
    # 语言识别
    # ========================================================
    def _detect_language(self, filepath: str) -> str:
        """根据文件扩展名检测语言"""
        if not filepath:
            return ""

        ext = os.path.splitext(filepath)[1].lower()
        language_map = {
            '.py': 'Python',
            '.pyw': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.jsx': 'JavaScript React',
            '.tsx': 'TypeScript React',
            '.java': 'Java',
            '.c': 'C',
            '.cpp': 'C++',
            '.cc': 'C++',
            '.cxx': 'C++',
            '.h': 'C/C++ Header',
            '.hpp': 'C++ Header',
            '.cs': 'C#',
            '.go': 'Go',
            '.rs': 'Rust',
            '.rb': 'Ruby',
            '.php': 'PHP',
            '.swift': 'Swift',
            '.kt': 'Kotlin',
            '.scala': 'Scala',
            '.m': 'Objective-C',
            '.sh': 'Shell',
            '.bat': 'Batch',
            '.ps1': 'PowerShell',
            '.html': 'HTML',
            '.htm': 'HTML',
            '.css': 'CSS',
            '.scss': 'SCSS',
            '.less': 'Less',
            '.json': 'JSON',
            '.xml': 'XML',
            '.yaml': 'YAML',
            '.yml': 'YAML',
            '.toml': 'TOML',
            '.ini': 'INI',
            '.md': 'Markdown',
            '.rst': 'reStructuredText',
            '.tex': 'LaTeX',
            '.sql': 'SQL',
            '.log': 'Log',
            '.csv': 'CSV',
            '.txt': 'Plain Text',
        }
        return language_map.get(ext, '')

    @property
    def language(self) -> str:
        return self.meta.language

    # ========================================================
    # 编辑器关联
    # ========================================================
    def add_editor(self, editor):
        """关联编辑器（弱引用）"""
        if editor not in self._editors:
            self._editors.append(editor)

    def remove_editor(self, editor):
        """取消关联编辑器"""
        if editor in self._editors:
            self._editors.remove(editor)

    def get_editors(self) -> List[Any]:
        """获取所有关联的编辑器"""
        return list(self._editors)

    def has_editors(self) -> bool:
        """是否有关联的编辑器"""
        return len(self._editors) > 0

    # ========================================================
    # 统计与信息
    # ========================================================
    def get_statistics(self) -> Dict[str, Any]:
        """获取文档统计信息"""
        text = self.get_text()
        lines = text.splitlines()
        words = len(text.split())
        chars = len(text)
        chars_no_space = len(''.join(text.split()))

        return {
            'lines': len(lines),
            'words': words,
            'chars': chars,
            'chars_no_space': chars_no_space,
            'paragraphs': len([l for l in lines if l.strip()]),
            'bookmarks': len(self._bookmarks),
            'folded': len(self._folded_lines),
            'modified': self.meta.modified,
            'encoding': self.meta.encoding,
            'eol': repr(self.meta.eol),
            'size': self.meta.size,
            'size_kb': round(self.meta.size / 1024, 2),
        }

    def get_info(self) -> Dict[str, Any]:
        """获取文档信息"""
        return {
            'title': self.meta.title,
            'filepath': self.meta.filepath,
            'encoding': self.meta.encoding,
            'eol': repr(self.meta.eol),
            'size': self.meta.size,
            'modified': self.meta.modified,
            'readonly': self.meta.readonly,
            'state': self._state.name,
            'language': self.meta.language,
            'line_count': self.meta.line_count,
            'char_count': self.meta.char_count,
        }

    def get_hash(self) -> Optional[str]:
        """获取文档内容哈希"""
        if not self.meta.filepath:
            return None
        return get_file_hash(self.meta.filepath)

    # ========================================================
    # 文件变更检测
    # ========================================================
    def has_external_change(self) -> bool:
        """检查是否有外部修改"""
        if self.provider:
            try:
                if hasattr(self.provider, 'check_external_change'):
                    return self.provider.check_external_change()
            except Exception:
                pass
        return False

    # ========================================================
    # 只读控制
    # ========================================================
    def set_readonly(self, readonly: bool) -> bool:
        """设置只读状态"""
        if readonly:
            self.meta.readonly = True
            self._state = DocumentState.READONLY
            if self.provider:
                try:
                    if hasattr(self.provider, 'set_readonly'):
                        self.provider.set_readonly(True)
                except Exception:
                    pass
            return True
        else:
            try:
                if self.provider:
                    if hasattr(self.provider, 'set_readonly'):
                        if self.provider.set_readonly(False):
                            self.meta.readonly = False
                            self._state = (
                                DocumentState.MODIFIED
                                if self.meta.modified
                                else DocumentState.CLEAN
                            )
                            return True
                        return False
                    else:
                        # provider 无此方法，直接改标志
                        self.meta.readonly = False
                        self._state = (
                            DocumentState.MODIFIED
                            if self.meta.modified
                            else DocumentState.CLEAN
                        )
                        return True
            except Exception:
                pass
            return False

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出文档信息"""
        info = self.get_info()
        stats = self.get_statistics()

        lines = [f"文档: {info['title']}", "=" * 60]
        lines.append(f"路径: {info['filepath'] or '(未保存)'}")
        lines.append(f"编码: {info['encoding']}")
        lines.append(f"行尾符: {info['eol']}")
        lines.append(f"大小: {stats['size_kb']} KB")
        lines.append(f"状态: {info['state']}")
        lines.append(f"语言: {info['language'] or '(未知)'}")
        lines.append("")
        lines.append(f"行数: {stats['lines']}")
        lines.append(f"词数: {stats['words']}")
        lines.append(f"字符数: {stats['chars']}")
        lines.append(f"段落数: {stats['paragraphs']}")
        lines.append(f"书签: {stats['bookmarks']}")
        lines.append(f"折叠: {stats['folded']}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<Document title={self.meta.title!r} "
                f"path={self.meta.filepath!r} "
                f"state={self._state.name} "
                f"modified={self.meta.modified}>")


# ============================================================
# 文档模型（多文档管理）
# ============================================================
class DocumentModel(QObject):
    """
    文档模型。

    管理所有打开的文档，提供按路径查找、批量操作等接口。

    信号:
        document_opened(str): 文档打开（文件路径）
        document_closed(str): 文档关闭（文件路径）
        document_modified(str): 文档修改（文件路径）
    """

    document_opened = pyqtSignal(str)
    document_closed = pyqtSignal(str)
    document_modified = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

        # 文档字典：文件路径 -> Document
        self._documents: Dict[str, Document] = {}

        # 未命名文档列表
        self._untitled: List[Document] = []

        # 最近关闭的文档（用于恢复）
        self._closed_documents: List[Dict[str, Any]] = []

    # ========================================================
    # 打开与关闭
    # ========================================================
    def open_document(self, filepath: str, **kwargs) -> Optional[Document]:
        """
        打开文档。

        如果文档已打开，返回现有对象。

        参数:
            filepath: 文件路径
            **kwargs: 传递给 Document.open 的参数

        返回:
            Document 实例或 None
        """
        filepath = os.path.abspath(filepath)

        # 检查是否已打开
        if filepath in self._documents:
            return self._documents[filepath]

        # 创建新文档
        doc = Document()
        if doc.open(filepath, **kwargs):
            self._documents[filepath] = doc

            # 连接信号
            doc.modified_changed.connect(
                lambda m, p=filepath: self._on_doc_modified(p, m)
            )

            self.document_opened.emit(filepath)
            return doc

        return None

    def create_document(self, text: str = "",
                        title: str = "未命名") -> Document:
        """创建未命名文档"""
        doc = Document()
        doc.open_from_text(text, title)
        self._untitled.append(doc)
        return doc

    def close_document(self, document: Document) -> bool:
        """
        关闭文档。

        参数:
            document: Document 实例

        返回:
            是否成功关闭
        """
        if document is None:
            return False

        filepath = document.meta.filepath

        # 从未命名列表移除
        if document in self._untitled:
            self._untitled.remove(document)

        # 从字典移除
        if filepath and filepath in self._documents:
            del self._documents[filepath]

        # 删除草稿 —— **仅在内容未被修改时**
        #
        # 缺陷背景（真实缺陷，已核实）：
        #   原实现**无条件** delete_draft()，不看 meta.modified。
        #   于是"未保存就关闭标签"会把唯一一份草稿删掉，而退出路径
        #   （Discard）也会走到这里 —— 用户未保存的编辑彻底消失，
        #   且因为草稿原本就没有读取端，连手动找回都不可能。
        #
        # 现在的规则：
        #   * 已修改（有未保存内容）→ **保留草稿**，让它成为崩溃/下次启动
        #     的恢复来源；
        #   * 未修改（内容已落盘）→ 草稿已无价值，删除。
        if not getattr(document.meta, 'modified', False):
            try:
                document.delete_draft()
            except Exception:
                pass

        # 关闭文档
        document.close()

        self.document_closed.emit(filepath or "")

        return True

    def close_all(self) -> int:
        """关闭所有文档，返回关闭数量"""
        count = 0
        for doc in list(self._documents.values()):
            if self.close_document(doc):
                count += 1
        for doc in list(self._untitled):
            if self.close_document(doc):
                count += 1
        return count

    # ========================================================
    # 查询
    # ========================================================
    def get_document(self, filepath: str) -> Optional[Document]:
        """按路径获取文档"""
        if not filepath:
            return None
        return self._documents.get(os.path.abspath(filepath))

    def has_document(self, filepath: str) -> bool:
        """检查文档是否已打开"""
        return os.path.abspath(filepath) in self._documents

    def get_all_documents(self) -> List[Document]:
        """获取所有文档"""
        return list(self._documents.values()) + list(self._untitled)

    def get_open_files(self) -> List[str]:
        """获取所有已打开文件的路径"""
        return list(self._documents.keys())

    def get_modified_documents(self) -> List[Document]:
        """获取所有已修改的文档"""
        result = []
        for doc in self.get_all_documents():
            if doc.is_modified:
                result.append(doc)
        return result

    def count(self) -> int:
        """获取文档总数"""
        return len(self._documents) + len(self._untitled)

    def is_empty(self) -> bool:
        """是否没有打开任何文档"""
        return self.count() == 0

    # ========================================================
    # 信号处理
    # ========================================================
    def _on_doc_modified(self, filepath: str, modified: bool):
        """文档修改回调"""
        if modified:
            self.document_modified.emit(filepath)

    # ========================================================
    # 批量操作
    # ========================================================
    def save_all(self) -> Tuple[int, int]:
        """
        保存所有已修改的文档。

        返回:
            (成功数, 失败数)
        """
        success = 0
        failed = 0
        for doc in self.get_modified_documents():
            if doc.save():
                success += 1
            else:
                failed += 1
        return (success, failed)

    def reload_all(self) -> int:
        """重新加载所有文档"""
        count = 0
        for doc in self.get_all_documents():
            if doc.reload():
                count += 1
        return count

    # ========================================================
    # 统计
    # ========================================================
    def get_statistics(self) -> Dict[str, Any]:
        """获取整体统计"""
        total_lines = 0
        total_chars = 0
        modified_count = 0
        readonly_count = 0

        for doc in self.get_all_documents():
            stats = doc.get_statistics()
            total_lines += stats['lines']
            total_chars += stats['chars']
            if doc.is_modified:
                modified_count += 1
            if doc.is_readonly:
                readonly_count += 1

        return {
            'document_count': self.count(),
            'named_count': len(self._documents),
            'untitled_count': len(self._untitled),
            'modified_count': modified_count,
            'readonly_count': readonly_count,
            'total_lines': total_lines,
            'total_chars': total_chars,
        }

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出模型信息"""
        stats = self.get_statistics()
        lines = ["DocumentModel", "=" * 60]
        lines.append(f"文档总数: {stats['document_count']}")
        lines.append(f"已保存: {stats['named_count']}")
        lines.append(f"未命名: {stats['untitled_count']}")
        lines.append(f"已修改: {stats['modified_count']}")
        lines.append(f"只读: {stats['readonly_count']}")
        lines.append(f"总行数: {stats['total_lines']}")
        lines.append(f"总字符: {stats['total_chars']}")
        lines.append("")
        lines.append("打开的文件:")
        for fp in self._documents.keys():
            doc = self._documents[fp]
            modified = ' *' if doc.is_modified else ''
            lines.append(f"  - {fp}{modified}")
        for doc in self._untitled:
            modified = ' *' if doc.is_modified else ''
            lines.append(f"  - (未命名) {doc.title}{modified}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return self.count()

    def __contains__(self, filepath: str) -> bool:
        return self.has_document(filepath)

    def __repr__(self) -> str:
        return f"<DocumentModel documents={self.count()}>"


# ============================================================
# 文档比较
# ============================================================
def compare_documents(doc1: Document, doc2: Document) -> Dict[str, Any]:
    """
    比较两个文档。

    参数:
        doc1: 文档1
        doc2: 文档2

    返回:
        比较结果字典
    """
    text1 = doc1.get_text()
    text2 = doc2.get_text()

    lines1 = text1.splitlines()
    lines2 = text2.splitlines()

    import difflib
    differ = difflib.SequenceMatcher(None, lines1, lines2)

    added = 0
    removed = 0
    modified = 0

    for tag, i1, i2, j1, j2 in differ.get_opcodes():
        if tag == 'insert':
            added += j2 - j1
        elif tag == 'delete':
            removed += i2 - i1
        elif tag == 'replace':
            modified += max(i2 - i1, j2 - j1)

    return {
        'identical': text1 == text2,
        'line_count_1': len(lines1),
        'line_count_2': len(lines2),
        'added_lines': added,
        'removed_lines': removed,
        'modified_lines': modified,
        'similarity': differ.ratio(),
        'diff': list(difflib.unified_diff(
            lines1, lines2,
            fromfile=doc1.title,
            tofile=doc2.title,
            lineterm=''
        )),
    }


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import shutil
    import tempfile

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    print("=== 测试 Document ===")

    # 创建临时文件
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_doc_test_")
    test_file = os.path.join(tmp_dir, "test.py")

    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("#!/usr/bin/env python\n")
        f.write("# -*- coding: utf-8 -*-\n")
        f.write("\n")
        f.write("def main():\n")
        f.write("    print('Hello, 青草!')\n")
        f.write("    return 0\n")
        f.write("\n")
        f.write("if __name__ == '__main__':\n")
        f.write("    main()\n")

    # 打开文档
    doc = Document()
    success = doc.open(test_file)
    print(f"打开: {success}")
    print(doc)
    print()
    print(doc.dump())
    print()

    # 测试行索引
    print("=== 测试行索引 ===")
    print(f"总行数: {doc.get_line_count()}")
    print(f"第 5 行: {doc.get_line_text(4)!r}")
    print(f"位置 (4, 4) -> 字符偏移: {doc.get_position(4, 4)}")
    print(f"字符偏移 50 -> (行, 列): {doc.get_position_line_col(50)}")
    print()

    # 测试书签
    print("=== 测试书签 ===")
    doc.add_bookmark(3)
    doc.add_bookmark(7)
    doc.toggle_bookmark(4)
    print(f"书签: {doc.get_bookmarks()}")
    print(f"从行 3 下一个: {doc.next_bookmark(3)}")
    print(f"从行 5 上一个: {doc.prev_bookmark(5)}")
    print()

    # 测试折叠
    print("=== 测试折叠 ===")
    doc.add_fold(4)
    print(f"折叠行: {doc.get_folded_lines()}")
    print(f"第 4 行是否折叠: {doc.is_folded(4)}")
    print()

    # 测试修改追踪
    print("=== 测试修改追踪 ===")
    print(f"修改前状态: {doc.state.name}, 已修改: {doc.is_modified}")
    doc.mark_modified()
    print(f"修改后状态: {doc.state.name}, 已修改: {doc.is_modified}")
    doc.save()
    print(f"保存后状态: {doc.state.name}, 已修改: {doc.is_modified}")
    print()

    # 测试 set_text + save 的完整流程（关键修复）
    print("=== 测试 set_text + save 写盘 ===")
    original = doc.get_text()
    new_text = original + "# extra line\n"
    doc.set_text(new_text)
    print(f"set_text 后已修改: {doc.is_modified}")

    save_ok = doc.save()
    print(f"save 返回: {save_ok}")

    # 验证磁盘内容
    with open(test_file, encoding='utf-8') as f:
        disk_content = f.read()
    print(f"磁盘包含 'extra line': {'extra line' in disk_content}")
    print()

    # 测试 provider 兼容性（关键修复）
    print("=== 测试 provider 兼容性 ===")
    print(f"provider 类型: {type(doc.provider).__name__}")
    print(
        f"check_external_change 存在: "
        f"{hasattr(doc.provider, 'check_external_change')}"
    )
    print(f"has_external_change: {doc.has_external_change()}")
    print()

    # 测试内存 provider 的兼容性
    mem_doc = Document()
    mem_doc.open_from_text("test content")
    print(f"内存文档 provider: {type(mem_doc.provider).__name__}")
    print(
        f"check_external_change 存在: "
        f"{hasattr(mem_doc.provider, 'check_external_change')}"
    )
    print(
        f"调用结果: {mem_doc.provider.check_external_change()}"
    )
    print(f"has_external_change: {mem_doc.has_external_change()}")
    mem_doc.close()
    print()

    # 测试统计
    print("=== 测试统计 ===")
    stats = doc.get_statistics()
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print()

    # 测试文档模型
    print("=== 测试 DocumentModel ===")
    model = DocumentModel()

    # 打开多个文档
    test_file2 = os.path.join(tmp_dir, "test2.txt")
    with open(test_file2, 'w', encoding='utf-8') as f:
        f.write("另一个测试文件\n")

    doc1 = model.open_document(test_file)
    doc2 = model.open_document(test_file2)
    doc3 = model.create_document("未命名内容", "无标题")

    print(model.dump())
    print()

    # 测试查找
    print(f"查找 test.py: {model.get_document(test_file) is not None}")
    print(f"是否已打开: {model.has_document(test_file)}")
    print(f"打开的文件: {model.get_open_files()}")
    print()

    # 测试修改文档
    doc1.mark_modified()
    print(f"已修改文档: {len(model.get_modified_documents())}")
    print()

    # 测试保存全部
    success, failed = model.save_all()
    print(f"保存全部: 成功 {success}, 失败 {failed}")
    print()

    # 测试文档比较
    print("=== 测试文档比较 ===")
    doc_a = Document()
    doc_a.open_from_text("line 1\nline 2\nline 3\n")
    doc_b = Document()
    doc_b.open_from_text("line 1\nline 2 modified\nline 3\nline 4\n")

    result = compare_documents(doc_a, doc_b)
    print(f"相同: {result['identical']}")
    print(f"相似度: {result['similarity']:.2%}")
    print(f"新增行: {result['added_lines']}")
    print(f"删除行: {result['removed_lines']}")
    print(f"修改行: {result['modified_lines']}")
    print()

    # 关闭所有
    print(f"关闭所有: {model.close_all()}")
    print(f"模型大小: {len(model)}")

    # 清理
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print()
    print("测试完成。")