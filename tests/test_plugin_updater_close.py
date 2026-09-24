"""plugin_updater 取消下载后连接关闭（P1-A3）"""
import pytest
from unittest.mock import MagicMock, patch


class TestDownloadClose:
    def test_cancel_closes_connection(self, qapp):
        """取消下载后应关闭 resp"""
        try:
            from infrastructure.plugin_updater import PluginUpdater
        except ImportError:
            pytest.skip("plugin_updater 不可用")

        updater = PluginUpdater()

        # 构造一个 fake response
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.headers = {'content-length': '1000000'}

        def fake_iter_content(chunk_size):
            # 模拟分块流：每次调用返回一批
            for i in range(100):
                yield b"x" * chunk_size

        fake_resp.iter_content = fake_iter_content

        # patch requests.get
        with patch('requests.get', return_value=fake_resp):
            # 立刻设置取消标志
            updater._cancelled = True

            # 调下载
            result = updater._download_update(
                "http://example.com/fake.zip", "test"
            )

            # 应返回 None（因为取消）
            assert result is None
            # resp.close 应被调用
            fake_resp.close.assert_called_once()

    def test_normal_download_closes(self, qapp):
        """正常下载完成后也应 close"""
        try:
            from infrastructure.plugin_updater import PluginUpdater
        except ImportError:
            pytest.skip("plugin_updater 不可用")

        updater = PluginUpdater()
        updater._cancelled = False

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.headers = {'content-length': '10'}
        fake_resp.iter_content = lambda chunk_size: iter([b"hello"])

        with patch('requests.get', return_value=fake_resp):
            result = updater._download_update(
                "http://example.com/fake.zip", "test"
            )
            assert result == b"hello"
            fake_resp.close.assert_called_once()