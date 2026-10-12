# -*- coding: utf-8 -*-
"""plugin_updater 取消下载后连接关闭（P1-A3 / F1）

注意：
    _download_update 在 for attempt 循环开头有：

        if self._cancelled:
            return None

    所以不能一开始就把 _cancelled = True，否则 requests.get
    根本不会被调用。测试改为在 iter_content 中途触发 cancel。
"""
from unittest.mock import MagicMock, patch

import pytest


class TestDownloadClose:

    def _make_updater(self):
        try:
            from infrastructure.plugin_updater import PluginUpdater
        except ImportError:
            pytest.skip("plugin_updater 不可用")
        return PluginUpdater()

    def test_cancel_closes_connection(self, qapp):
        """下载中途取消 → resp 应被关闭"""
        updater = self._make_updater()
        updater._cancelled = False

        # iter_content 第一次 yield 后触发 cancel
        def iter_content_side(chunk_size):
            yield b"x" * chunk_size
            updater._cancelled = True   # 中途取消
            yield b"y" * chunk_size     # 应该被 for 循环检测到而返回

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.headers = {'content-length': '10000'}
        fake_resp.iter_content = iter_content_side

        with patch('requests.get', return_value=fake_resp):
            result = updater._download_update(
                "http://example.com/fake.zip", "test"
            )

        assert result is None
        assert fake_resp.close.called, "取消后 resp.close() 未被调用"

    def test_normal_download_closes(self, qapp):
        """正常下载完成后 resp 应被关闭"""
        updater = self._make_updater()
        updater._cancelled = False

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.headers = {'content-length': '5'}
        fake_resp.iter_content = lambda chunk_size: iter([b"hello"])

        with patch('requests.get', return_value=fake_resp):
            result = updater._download_update(
                "http://example.com/fake.zip", "test"
            )

        assert result == b"hello"
        assert fake_resp.close.called
