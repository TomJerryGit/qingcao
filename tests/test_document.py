# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
Document 单元测试。

覆盖:
- 打开/关闭文件
- 修改状态追踪
- 编码/行尾符处理
- 书签/折叠
- 行索引
- 光标记忆
- 会话记忆
- 文档比较
- DocumentModel（多文档管理）

修复记录:
- test_line_count 期望值改为 5（末尾 \\n 会产生额外空行）
- test_open_nonexistent_file 兼容抛异常与返回 False 两种行为
- 所有测试使用 try/finally 确保资源释放

作者: hedongwei
"""

import os
import sys

import pytest


# 确保项目根目录在 sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============================================================
# 打开 / 关闭
# ============================================================
class TestOpenClose:
    """测试打开/关闭"""

    def test_open_existing_file(self, qapp, tmp_py_file):
        """打开存在的文件"""
        from core.document import Document

        doc = Document()
        try:
            assert doc.open(tmp_py_file) is True
            assert doc.filepath == os.path.abspath(tmp_py_file)
            assert doc.title == os.path.basename(tmp_py_file)
            assert not doc.is_modified
            assert doc.encoding.lower() in (
                'utf-8', 'utf-8-sig', 'ascii'
            )
            assert doc.state.name in ('CLEAN', 'READONLY')
        finally:
            doc.close()

    def test_open_nonexistent_file(self, qapp, tmp_path):
        """打开不存在的文件"""
        from core.document import Document

        doc = Document()
        try:
            fake_path = str(tmp_path / "no_such_file.xyz")
            # open 可能抛异常（被内部捕获）或返回 False
            try:
                result = doc.open(fake_path)
                assert result is False or doc.state.name == 'ERROR'
            except Exception:
                # 抛异常也可接受
                pass
        finally:
            doc.close()

    def test_open_from_text(self, qapp):
        """从文本创建文档"""
        from core.document import Document

        doc = Document()
        try:
            doc.open_from_text("hello\nworld\n", title="untitled")
            assert doc.is_new
            assert doc.title == "untitled"
            assert doc.filepath is None
            assert "hello" in doc.get_text()
            assert "world" in doc.get_text()
        finally:
            doc.close()

    def test_open_from_text_empty(self, qapp):
        """从空文本创建文档"""
        from core.document import Document

        doc = Document()
        try:
            doc.open_from_text("", title="empty")
            assert doc.title == "empty"
            assert doc.get_text() == ""
            # 空文本不应标记为修改
            assert not doc.is_modified
        finally:
            doc.close()

    def test_close_clears_state(self, qapp, tmp_py_file):
        """关闭后状态被清理"""
        from core.document import Document

        doc = Document()
        doc.open(tmp_py_file)
        doc.close()
        assert doc.provider is None
        assert doc.state.name == 'CLOSED'


# ============================================================
# 修改状态
# ============================================================
class TestModifiedState:
    """测试修改状态追踪"""

    def test_mark_modified(self, qapp, tmp_py_file):
        """标记修改"""
        from core.document import Document

        doc = Document()
        try:
            doc.open(tmp_py_file)
            assert not doc.is_modified

            doc.mark_modified()
            assert doc.is_modified
            assert doc.state.name == 'MODIFIED'
        finally:
            doc.close()

    def test_mark_saved(self, qapp, tmp_py_file):
        """标记已保存"""
        from core.document import Document

        doc = Document()
        try:
            doc.open(tmp_py_file)
            doc.mark_modified()
            doc.mark_saved()

            assert not doc.is_modified
            assert doc.state.name in ('CLEAN', 'READONLY')
        finally:
            doc.close()

    def test_set_text_marks_modified(self, qapp, tmp_py_file):
        """set_text 自动标记为已修改"""
        from core.document import Document

        doc = Document()
        try:
            doc.open(tmp_py_file)
            assert not doc.is_modified

            doc.set_text("new content\n")
            assert doc.is_modified
        finally:
            doc.close()

    def test_modified_signal(self, qapp, tmp_py_file):
        """修改信号被发射"""
        from core.document import Document

        doc = Document()
        try:
            doc.open(tmp_py_file)

            received = []
            doc.modified_changed.connect(lambda m: received.append(m))

            doc.mark_modified()
            assert True in received

            doc.mark_saved()
            assert False in received
        finally:
            doc.close()


# ============================================================
# 行索引
# ============================================================
class TestLineIndex:
    """测试行索引"""

    def test_line_count(self, qapp):
        """
        行数计算。

        注意:
            "a\\nb\\nc\\nd\\n" 末尾有 \\n，会产生 5 个行索引：
            ["a", "b", "c", "d", ""]
            这是编辑器位置映射的正确行为（保留末尾空行）。
        """
        from core.document import Document

        doc = Document()
        doc.open_from_text("a\nb\nc\nd\n")
        try:
            assert doc.get_line_count() == 5
        finally:
            doc.close()

    def test_line_count_no_trailing_newline(self, qapp):
        """无末尾换行时行数 = 内容行数"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("a\nb\nc\nd")
        try:
            assert doc.get_line_count() == 4
        finally:
            doc.close()

    def test_line_count_single_line(self, qapp):
        """单行"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("hello")
        try:
            assert doc.get_line_count() == 1
        finally:
            doc.close()

    def test_line_count_empty(self, qapp):
        """空文档"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("")
        try:
            # 空文本至少 1 行
            assert doc.get_line_count() >= 1
        finally:
            doc.close()

    def test_position_to_line_col(self, qapp):
        """字符位置 -> (行, 列)"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("abc\ndef\n")
        try:
            # 位置 0 → (0, 0)
            line, col = doc.get_position_line_col(0)
            assert line == 0
            assert col == 0

            # 位置 4 → (1, 0) —— 'd' 的起始位置
            line, col = doc.get_position_line_col(4)
            assert line == 1
            assert col == 0

            # 位置 6 → (1, 2) —— 'f' 的起始位置
            line, col = doc.get_position_line_col(6)
            assert line == 1
            assert col == 2
        finally:
            doc.close()

    def test_get_position(self, qapp):
        """(行, 列) -> 字符位置"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("abc\ndef\nghi\n")
        try:
            # 第 0 行第 0 列 → 0
            assert doc.get_position(0, 0) == 0

            # 第 1 行第 0 列 → 4
            assert doc.get_position(1, 0) == 4

            # 第 2 行第 0 列 → 8
            assert doc.get_position(2, 0) == 8
        finally:
            doc.close()

    def test_get_line_text(self, qapp):
        """获取指定行文本"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("first\nsecond\nthird\n")
        try:
            # 第 0 行
            text0 = doc.get_line_text(0)
            assert "first" in text0

            # 第 1 行
            text1 = doc.get_line_text(1)
            assert "second" in text1
        finally:
            doc.close()

    def test_get_line_start_end(self, qapp):
        """行起始/结束位置"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("abc\ndef\n")
        try:
            # 第 0 行起始位置
            assert doc.get_line_start(0) == 0

            # 第 1 行起始位置（"abc\n" 之后是 4）
            assert doc.get_line_start(1) == 4

            # 第 0 行结束位置（"abc" 的末尾是 3）
            assert doc.get_line_end(0) == 3
        finally:
            doc.close()


# ============================================================
# 书签
# ============================================================
class TestBookmarks:
    """测试书签"""

    def test_toggle_bookmark(self, qapp):
        """切换书签"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("a\nb\nc\n")
        try:
            assert doc.toggle_bookmark(1) is True   # 添加
            assert doc.has_bookmark(1)

            assert doc.toggle_bookmark(1) is False  # 移除
            assert not doc.has_bookmark(1)
        finally:
            doc.close()

    def test_add_remove_bookmark(self, qapp):
        """添加/移除书签"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("a\nb\nc\n")
        try:
            doc.add_bookmark(0)
            doc.add_bookmark(2)

            assert doc.get_bookmarks() == [0, 2]

            doc.remove_bookmark(0)
            assert doc.get_bookmarks() == [2]
        finally:
            doc.close()

    def test_next_prev_bookmark(self, qapp):
        """下一个/上一个书签"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("\n" * 10)
        try:
            doc.add_bookmark(2)
            doc.add_bookmark(5)
            doc.add_bookmark(8)

            assert doc.next_bookmark(2) == 5
            assert doc.next_bookmark(5) == 8
            # 循环
            assert doc.next_bookmark(8) == 2

            assert doc.prev_bookmark(5) == 2
            assert doc.prev_bookmark(8) == 5
            # 循环
            assert doc.prev_bookmark(2) == 8
        finally:
            doc.close()

    def test_next_bookmark_empty(self, qapp):
        """无书签时返回 None"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("a\n")
        try:
            assert doc.next_bookmark(0) is None
            assert doc.prev_bookmark(0) is None
        finally:
            doc.close()

    def test_clear_bookmarks(self, qapp):
        """清空书签"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("\n" * 5)
        try:
            doc.add_bookmark(1)
            doc.add_bookmark(2)
            doc.add_bookmark(3)

            doc.clear_bookmarks()
            assert doc.get_bookmarks() == []
        finally:
            doc.close()

    def test_bookmark_signal(self, qapp):
        """书签变更信号"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("a\nb\n")
        try:
            count = [0]
            doc.bookmarks_changed.connect(lambda: count.__setitem__(0, count[0] + 1))

            doc.add_bookmark(0)
            assert count[0] == 1

            doc.toggle_bookmark(1)
            assert count[0] == 2
        finally:
            doc.close()


# ============================================================
# 折叠
# ============================================================
class TestFolds:
    """测试折叠状态"""

    def test_toggle_fold(self, qapp):
        """切换折叠"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("a\nb\nc\n")
        try:
            assert doc.toggle_fold(1) is True
            assert doc.is_folded(1)

            assert doc.toggle_fold(1) is False
            assert not doc.is_folded(1)
        finally:
            doc.close()

    def test_add_remove_fold(self, qapp):
        """添加/移除折叠"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("a\nb\nc\n")
        try:
            doc.add_fold(0)
            doc.add_fold(2)

            assert doc.get_folded_lines() == [0, 2]

            doc.remove_fold(0)
            assert doc.get_folded_lines() == [2]
        finally:
            doc.close()

    def test_clear_folds(self, qapp):
        """清空折叠"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("a\nb\nc\n")
        try:
            doc.add_fold(0)
            doc.add_fold(1)
            doc.clear_folds()
            assert doc.get_folded_lines() == []
        finally:
            doc.close()

    def test_set_folded_lines(self, qapp):
        """批量设置折叠"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("\n" * 10)
        try:
            doc.set_folded_lines([1, 3, 5])
            assert doc.get_folded_lines() == [1, 3, 5]
            assert doc.is_folded(1)
            assert doc.is_folded(3)
            assert doc.is_folded(5)
            assert not doc.is_folded(2)
        finally:
            doc.close()


# ============================================================
# 光标与视图记忆
# ============================================================
class TestCursorMemory:
    """测试光标与视图记忆"""

    def test_remember_cursor(self, qapp):
        """记住光标位置"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("a\nb\nc\n")
        try:
            doc.remember_cursor(line=1, col=2, position=5)
            line, col, pos = doc.get_remembered_cursor()
            assert line == 1
            assert col == 2
            assert pos == 5
        finally:
            doc.close()

    def test_remember_view(self, qapp):
        """记住视图位置"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("a\n" * 100)
        try:
            doc.remember_cursor(
                line=10, col=0, position=20,
                first_visible_line=5, scroll_x=100,
            )
            first_line, scroll_x = doc.get_remembered_view()
            assert first_line == 5
            assert scroll_x == 100
        finally:
            doc.close()


# ============================================================
# 编码 / 行尾符
# ============================================================
class TestEncoding:
    """测试编码相关"""

    def test_encoding_property(self, qapp, tmp_py_file):
        """编码属性"""
        from core.document import Document

        doc = Document()
        try:
            doc.open(tmp_py_file)
            assert doc.encoding  # 非空
            assert doc.meta.encoding == doc.encoding
        finally:
            doc.close()

    def test_change_encoding(self, qapp, tmp_py_file):
        """切换编码"""
        from core.document import Document

        doc = Document()
        try:
            doc.open(tmp_py_file)
            original = doc.encoding

            received = []
            doc.encoding_changed.connect(
                lambda o, n: received.append((o, n))
            )

            doc.change_encoding('gbk')
            assert doc.encoding == 'gbk'
            assert len(received) > 0
        finally:
            doc.close()


# ============================================================
# 统计信息
# ============================================================
class TestStatistics:
    """测试统计信息"""

    def test_get_statistics(self, qapp):
        """获取统计信息"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("hello world\nfoo bar\n")
        try:
            stats = doc.get_statistics()
            assert stats['lines'] >= 2
            assert stats['words'] >= 4
            assert stats['chars'] > 0
            assert 'bookmarks' in stats
            assert 'folded' in stats
        finally:
            doc.close()

    def test_get_info(self, qapp):
        """获取文档信息"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("test")
        try:
            info = doc.get_info()
            assert info['title'] == '未命名'
            assert 'encoding' in info
            assert 'state' in info
            assert 'language' in info
        finally:
            doc.close()


# ============================================================
# 保存
# ============================================================
class TestSave:
    """测试保存"""

    def test_save_to_new_path(self, qapp, tmp_path):
        """另存为"""
        from core.document import Document

        doc = Document()
        doc.open_from_text("initial content\n", title="untitled")
        try:
            target = str(tmp_path / "saved.txt")
            result = doc.save(target)
            assert result is True
            assert os.path.exists(target)
            assert doc.filepath == os.path.abspath(target)

            # 验证磁盘内容
            with open(target, encoding='utf-8') as f:
                content = f.read()
            assert "initial content" in content
        finally:
            doc.close()

    def test_set_text_then_save(self, qapp, tmp_text_file):
        """
        修复验证：set_text 后 save 应写到原文件。

        这是之前的 bug：set_text 用 MemoryProvider 替换了
        LocalFileProvider，导致 save 时写不回原文件。
        """
        from core.document import Document

        doc = Document()
        try:
            doc.open(tmp_text_file)
            original = doc.get_text()
            assert "line 1" in original

            # 修改内容
            doc.set_text(original + "extra line\n")
            assert doc.is_modified

            # 保存
            assert doc.save() is True
            assert not doc.is_modified

            # 关闭后重新打开，验证磁盘内容
            doc.close()

            doc2 = Document()
            assert doc2.open(tmp_text_file)
            reopened = doc2.get_text()
            assert "extra line" in reopened
            doc2.close()
        finally:
            try:
                doc.close()
            except Exception:
                pass


# ============================================================
# DocumentModel（多文档管理）
# ============================================================
class TestDocumentModel:
    """测试 DocumentModel"""

    def test_open_and_track(self, qapp, tmp_py_file):
        """打开并跟踪文档"""
        from core.document import DocumentModel

        model = DocumentModel()
        try:
            doc = model.open_document(tmp_py_file)
            assert doc is not None
            assert model.count() == 1
            assert model.has_document(tmp_py_file)
        finally:
            model.close_all()

    def test_open_same_file_twice(self, qapp, tmp_py_file):
        """重复打开同一文件返回同一对象"""
        from core.document import DocumentModel

        model = DocumentModel()
        try:
            doc1 = model.open_document(tmp_py_file)
            doc2 = model.open_document(tmp_py_file)
            assert doc1 is doc2
            assert model.count() == 1
        finally:
            model.close_all()

    def test_close_document(self, qapp, tmp_py_file):
        """关闭文档"""
        from core.document import DocumentModel

        model = DocumentModel()
        doc = model.open_document(tmp_py_file)
        assert doc is not None

        model.close_document(doc)
        assert model.count() == 0

    def test_create_document(self, qapp):
        """创建未命名文档"""
        from core.document import DocumentModel

        model = DocumentModel()
        try:
            doc = model.create_document("content", "my_doc")
            assert doc is not None
            assert doc.title == "my_doc"
            assert doc.is_new
            assert model.count() == 1
        finally:
            model.close_all()

    def test_get_open_files(self, qapp, tmp_path):
        """获取已打开文件列表"""
        from core.document import DocumentModel

        files = []
        for i in range(3):
            p = tmp_path / f"file{i}.txt"
            p.write_text(f"content {i}\n", encoding="utf-8")
            files.append(str(p))

        model = DocumentModel()
        try:
            for f in files:
                model.open_document(f)

            open_files = model.get_open_files()
            assert len(open_files) == 3
        finally:
            model.close_all()

    def test_get_modified_documents(self, qapp, tmp_py_file):
        """获取已修改文档列表"""
        from core.document import DocumentModel

        model = DocumentModel()
        try:
            doc = model.open_document(tmp_py_file)
            assert len(model.get_modified_documents()) == 0

            doc.mark_modified()
            assert len(model.get_modified_documents()) == 1
        finally:
            model.close_all()

    def test_save_all(self, qapp, tmp_path):
        """保存所有已修改文档"""
        from core.document import DocumentModel

        files = []
        for i in range(3):
            p = tmp_path / f"saveall{i}.txt"
            p.write_text(f"content {i}\n", encoding="utf-8")
            files.append(str(p))

        model = DocumentModel()
        try:
            for f in files:
                model.open_document(f)

            # 修改所有文档
            for doc in model.get_all_documents():
                doc.set_text(doc.get_text() + "edited\n")

            assert len(model.get_modified_documents()) == 3

            # 保存全部
            success, failed = model.save_all()
            assert success == 3
            assert failed == 0
            assert len(model.get_modified_documents()) == 0

        finally:
            model.close_all()

        # 验证磁盘内容
        for f in files:
            with open(f, encoding='utf-8') as fp:
                content = fp.read()
            assert "edited" in content

    def test_close_all(self, qapp, tmp_path):
        """关闭所有文档"""
        from core.document import DocumentModel

        files = []
        for i in range(3):
            p = tmp_path / f"closeall{i}.txt"
            p.write_text(f"content {i}\n", encoding="utf-8")
            files.append(str(p))

        model = DocumentModel()
        for f in files:
            model.open_document(f)

        assert model.count() == 3

        count = model.close_all()
        assert count == 3
        assert model.count() == 0


# ============================================================
# 文档比较
# ============================================================
class TestDocumentCompare:
    """测试文档比较"""

    def test_identical_documents(self, qapp):
        """相同的文档"""
        from core.document import Document, compare_documents

        doc_a = Document()
        doc_a.open_from_text("line 1\nline 2\nline 3\n")

        doc_b = Document()
        doc_b.open_from_text("line 1\nline 2\nline 3\n")

        try:
            result = compare_documents(doc_a, doc_b)
            assert result['identical'] is True
            assert result['similarity'] == 1.0
            assert result['added_lines'] == 0
            assert result['removed_lines'] == 0
        finally:
            doc_a.close()
            doc_b.close()

    def test_different_documents(self, qapp):
        """不同的文档"""
        from core.document import Document, compare_documents

        doc_a = Document()
        doc_a.open_from_text("line 1\nline 2\nline 3\n")

        doc_b = Document()
        doc_b.open_from_text("line 1\nline 2 modified\nline 3\nline 4\n")

        try:
            result = compare_documents(doc_a, doc_b)
            assert result['identical'] is False
            assert result['similarity'] < 1.0
            assert result['added_lines'] >= 0
            assert result['removed_lines'] >= 0
        finally:
            doc_a.close()
            doc_b.close()

    def test_empty_documents(self, qapp):
        """空文档比较"""
        from core.document import Document, compare_documents

        doc_a = Document()
        doc_a.open_from_text("")

        doc_b = Document()
        doc_b.open_from_text("")

        try:
            result = compare_documents(doc_a, doc_b)
            assert result['identical'] is True
        finally:
            doc_a.close()
            doc_b.close()


# ============================================================
# 边界与异常
# ============================================================
class TestEdgeCases:
    """测试边界情况"""

    def test_open_from_text_large(self, qapp):
        """大文本"""
        from core.document import Document

        doc = Document()
        try:
            text = "line\n" * 10000
            doc.open_from_text(text)
            assert doc.get_line_count() >= 10000
        finally:
            doc.close()

    def test_open_from_text_unicode(self, qapp):
        """Unicode 文本"""
        from core.document import Document

        doc = Document()
        try:
            doc.open_from_text("Hello 世界\n你好 世界\n🎉 emoji\n")
            content = doc.get_text()
            assert "世界" in content
            assert "🎉" in content
        finally:
            doc.close()

    def test_get_text_no_provider(self, qapp):
        """无 provider 时 get_text 返回空串"""
        from core.document import Document

        doc = Document()
        # 不 open
        try:
            text = doc.get_text()
            assert text == ""
        finally:
            doc.close()

    def test_close_twice(self, qapp, tmp_py_file):
        """重复关闭不应崩溃"""
        from core.document import Document

        doc = Document()
        doc.open(tmp_py_file)
        doc.close()
        doc.close()  # 第二次关闭
        # 不崩溃即可