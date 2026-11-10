# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405, UP006, UP045, UP035, UP007
"""文档模型/对比（v2.24 从 document.py 拆出）。"""

from __future__ import annotations

from core.document_common import *  # noqa: F401,F403,F405
from core.document_core import Document  # noqa: F401


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
            doc.modified_changed.connect(lambda m, p=filepath: self._on_doc_modified(p, m))

            self.document_opened.emit(filepath)
            return doc

        return None

    def create_document(self, text: str = "", title: str = "未命名") -> Document:
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
        if not getattr(document.meta, "modified", False):
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
            total_lines += stats["lines"]
            total_chars += stats["chars"]
            if doc.is_modified:
                modified_count += 1
            if doc.is_readonly:
                readonly_count += 1

        return {
            "document_count": self.count(),
            "named_count": len(self._documents),
            "untitled_count": len(self._untitled),
            "modified_count": modified_count,
            "readonly_count": readonly_count,
            "total_lines": total_lines,
            "total_chars": total_chars,
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
            modified = " *" if doc.is_modified else ""
            lines.append(f"  - {fp}{modified}")
        for doc in self._untitled:
            modified = " *" if doc.is_modified else ""
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
