#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ruff: noqa: UP006, UP045, UP035, UP007, F821
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
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

from __future__ import annotations

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
DEFAULT_ENCODING = "utf-8"
DEFAULT_EOL = "\n"
MAX_LINE_INDEX_CACHE = 100000  # 行索引缓存的最大行数
AUTO_SAVE_DRAFT_INTERVAL = 60  # 草稿自动保存间隔（秒）


# ============================================================
# 文档状态枚举
# ============================================================


class DocumentState(Enum):
    """文档状态"""

    NEW = auto()  # 新建未保存
    CLEAN = auto()  # 已保存，无修改
    MODIFIED = auto()  # 已修改
    SAVING = auto()  # 保存中
    LOADING = auto()  # 加载中
    READONLY = auto()  # 只读
    ERROR = auto()  # 错误
    CLOSED = auto()  # 已关闭


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
            "filepath": self.filepath,
            "title": self.title,
            "encoding": self.encoding,
            "eol": self.eol,
            "has_bom": self.has_bom,
            "size": self.size,
            "mtime": self.mtime,
            "created_at": self.created_at,
            "last_modified_at": self.last_modified_at,
            "last_saved_at": self.last_saved_at,
            "cursor_line": self.cursor_line,
            "cursor_col": self.cursor_col,
            "cursor_pos": self.cursor_pos,
            "first_visible_line": self.first_visible_line,
            "scroll_x": self.scroll_x,
            "modified": self.modified,
            "readonly": self.readonly,
            "line_count": self.line_count,
            "char_count": self.char_count,
            "language": self.language,
            "tags": list(self.tags),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> DocumentMetadata:
        """从字典反序列化"""
        meta = cls()
        for key, value in d.items():
            if hasattr(meta, key):
                setattr(meta, key, value)
        return meta


# ============================================================
# 文档对象
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
        if tag == "insert":
            added += j2 - j1
        elif tag == "delete":
            removed += i2 - i1
        elif tag == "replace":
            modified += max(i2 - i1, j2 - j1)

    return {
        "identical": text1 == text2,
        "line_count_1": len(lines1),
        "line_count_2": len(lines2),
        "added_lines": added,
        "removed_lines": removed,
        "modified_lines": modified,
        "similarity": differ.ratio(),
        "diff": list(
            difflib.unified_diff(
                lines1, lines2, fromfile=doc1.title, tofile=doc2.title, lineterm=""
            )
        ),
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

    with open(test_file, "w", encoding="utf-8") as f:
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
    with open(test_file, encoding="utf-8") as f:
        disk_content = f.read()
    print(f"磁盘包含 'extra line': {'extra line' in disk_content}")
    print()

    # 测试 provider 兼容性（关键修复）
    print("=== 测试 provider 兼容性 ===")
    print(f"provider 类型: {type(doc.provider).__name__}")
    print(f"check_external_change 存在: {hasattr(doc.provider, 'check_external_change')}")
    print(f"has_external_change: {doc.has_external_change()}")
    print()

    # 测试内存 provider 的兼容性
    mem_doc = Document()
    mem_doc.open_from_text("test content")
    print(f"内存文档 provider: {type(mem_doc.provider).__name__}")
    print(f"check_external_change 存在: {hasattr(mem_doc.provider, 'check_external_change')}")
    print(f"调用结果: {mem_doc.provider.check_external_change()}")
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
    with open(test_file2, "w", encoding="utf-8") as f:
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

__all__ = [n for n in dir() if not n.startswith("__")]

from typing import TYPE_CHECKING as _TYPE_CHECKING


if _TYPE_CHECKING:
    from core.document_core import Document  # noqa: F401
    from core.document_model import DocumentModel  # noqa: F401
