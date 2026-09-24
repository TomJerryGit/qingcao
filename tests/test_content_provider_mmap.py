"""content_provider._save_dirty_blocks mmap 释放测试（P1-A4）"""
import os
import pytest


class TestSaveDirtyBlocksReleasesMmap:
    def test_mmap_closed_before_write(self, tmp_path):
        """写脏块前应释放 mmap"""
        try:
            from core.content_provider import LocalFileProvider
        except ImportError:
            pytest.skip("LocalFileProvider 不可用")

        # 创建测试文件
        path = tmp_path / "test.txt"
        path.write_text("hello world\n" * 100, encoding='utf-8')

        provider = LocalFileProvider()
        try:
            provider.open(str(path))
            # 修改块 0
            new_data = b"MODIFIED\n"
            provider.write_block(0, new_data)

            # 保存
            ok = provider.save()
            assert ok is True

            # 验证磁盘内容
            with open(str(path), 'rb') as f:
                content = f.read()
            assert content.startswith(b"MODIFIED")

        finally:
            provider.close()

    def test_reopen_mmap_after_save(self, tmp_path):
        """保存后应重建 mmap，provider 仍可读"""
        try:
            from core.content_provider import LocalFileProvider
        except ImportError:
            pytest.skip("LocalFileProvider 不可用")

        path = tmp_path / "test.txt"
        path.write_text("line1\nline2\nline3\n", encoding='utf-8')

        provider = LocalFileProvider()
        try:
            provider.open(str(path))
            provider.write_block(0, b"changed\n")
            provider.save()

            # 保存后仍可读
            data = provider.read_block(0)
            assert b"changed" in data

        finally:
            provider.close()

    def test_save_when_mmap_disabled(self, tmp_path):
        """无 mmap 时也能保存"""
        try:
            from core.content_provider import LocalFileProvider
        except ImportError:
            pytest.skip("LocalFileProvider 不可用")

        path = tmp_path / "empty.txt"
        path.write_bytes(b"")

        provider = LocalFileProvider()
        try:
            provider.open(str(path))
            provider.write_block(0, b"new\n")
            assert provider.save() is True
        finally:
            provider.close()