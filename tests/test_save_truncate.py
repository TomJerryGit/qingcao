# -*- coding: utf-8 -*-
"""P0-1 回归测试：保存后必须截断，不能残留旧字节（数据损坏）

修复前 `LocalFileProvider._save_dirty_blocks` 只按块 seek+write，
从不 truncate。把 55 890 字节的文件删到 12 字节后保存，文件仍是
55 890 字节（新内容 + 旧尾部），重开编辑器会看到"删掉的内容又回来了"。
"""
import os

import pytest


@pytest.fixture()
def provider_cls():
    from core.content_provider import LocalFileProvider
    return LocalFileProvider


def _write(path, text, encoding='utf-8'):
    with open(path, 'w', encoding=encoding, newline='') as f:
        f.write(text)


def _read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


class TestSaveTruncates:
    """内容变短时文件必须被截断"""

    def test_shrink_through_document_save(self, qapp, tmp_path):
        """端到端：Document.set_text(短) + save() 后文件等于短内容"""
        from core.document import Document

        p = tmp_path / "demo.py"
        original = "".join("print('line %d')\n" % i for i in range(3000))
        _write(str(p), original)
        assert os.path.getsize(str(p)) == len(original.encode('utf-8'))

        doc = Document()
        try:
            assert doc.open(str(p))
            doc.set_text("print('hi')\n")
            assert doc.save() is True
        finally:
            doc.close()

        raw = _read_bytes(str(p))
        assert raw == b"print('hi')\n", (
            "保存后文件残留旧字节：实际 %d 字节" % len(raw)
        )

    def test_shrink_then_grow_then_shrink(self, qapp, tmp_path):
        """反复变短/变长都必须正确"""
        from core.document import Document

        p = tmp_path / "cycle.txt"
        _write(str(p), "A" * 50000)

        for text in ("short\n", "B" * 70000, "tiny\n"):
            doc = Document()
            try:
                assert doc.open(str(p))
                doc.set_text(text)
                assert doc.save() is True
            finally:
                doc.close()
            assert _read_bytes(str(p)) == text.encode('utf-8')

    def test_provider_save_truncates(self, provider_cls, tmp_path):
        """直接使用 provider：写短块后 save 必须截断"""
        p = tmp_path / "t.txt"
        _write(str(p), "A" * 100000)

        prov = provider_cls()
        try:
            prov.open(str(p))
            assert prov.size == 100000
            prov.write_block(0, b"BBBBBBBBBB")
            prov._total_blocks = 1
            prov._size = 10
            assert prov.save() is True
            assert os.path.getsize(str(p)) == 10
            assert _read_bytes(str(p)) == b"BBBBBBBBBB"
        finally:
            prov.close()

    def test_reopen_reads_short_content(self, qapp, tmp_path):
        """重开后读到的就是短内容，没有旧尾部"""
        from core.document import Document

        p = tmp_path / "reopen.py"
        _write(str(p), "old line\n" * 5000)

        doc = Document()
        try:
            doc.open(str(p))
            doc.set_text("new\n")
            doc.save()
        finally:
            doc.close()

        doc2 = Document()
        try:
            assert doc2.open(str(p))
            assert doc2.get_text() == "new\n"
        finally:
            doc2.close()

    def test_save_as_truncates(self, qapp, tmp_path):
        """另存为到已存在的长文件也必须被完全覆盖"""
        from core.document import Document

        src = tmp_path / "src.txt"
        dst = tmp_path / "dst.txt"
        _write(str(src), "x = 1\n")
        _write(str(dst), "OLDLONG" * 5000)

        doc = Document()
        try:
            doc.open(str(src))
            doc.set_text("short\n")
            assert doc.save(str(dst)) is True
        finally:
            doc.close()

        assert _read_bytes(str(dst)) == b"short\n"

    def test_empty_file_still_savable(self, provider_cls, tmp_path):
        """空文件写入内容后保存"""
        p = tmp_path / "empty.txt"
        p.write_bytes(b"")

        prov = provider_cls()
        try:
            prov.open(str(p))
            prov.write_block(0, b"new\n")
            assert prov.save() is True
            assert _read_bytes(str(p)) == b"new\n"
        finally:
            prov.close()
