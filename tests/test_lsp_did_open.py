# -*- coding: utf-8 -*-
"""P0-2 回归测试：LSP did_open 参数顺序与文档同步

修复前 core/editor.py 调用：
    self.lsp_client.did_open(uri, self.sc.text())
而签名是 did_open(uri, language_id, text, version=1)，导致
language_id 收到整份文件文本、text 缺失、version=None，
随后 did_change 里 `version += 1` 抛 TypeError，LSP 静默失效。
"""
import pytest


class TestDidOpenSignature:
    """参数必须按签名传递"""

    def test_correct_order_records_state(self, qapp):
        from core.lsp_client import LspClient

        client = LspClient()
        uri = "file:///d:/demo.py"
        client.did_open(uri, "python", "print('hi')\n")

        assert client._doc_versions[uri] == 1
        assert client._open_documents[uri] == "python"

    def test_did_change_after_did_open_does_not_raise(self, qapp):
        from core.lsp_client import LspClient

        client = LspClient()
        uri = "file:///d:/demo.py"
        client.did_open(uri, "python", "print('hi')\n")
        client.did_change(uri, "print('bye')\n")   # 修复前会 TypeError
        assert client._doc_versions[uri] == 2

    def test_missing_text_argument_still_detected(self, qapp):
        """旧调用形态仍应被签名拦住（防止回归）"""
        from core.lsp_client import LspClient

        client = LspClient()
        with pytest.raises(TypeError):
            client.did_open("file:///d:/demo.py", "print('hi')\n")

    def test_none_text_is_tolerated(self, qapp):
        """防御：text 为 None 时按空文档处理，不抛异常"""
        from core.lsp_client import LspClient

        client = LspClient()
        uri = "file:///d:/a.py"
        client.did_open(uri, "python", None)
        assert client._doc_versions[uri] == 1
        client.did_change(uri, "x = 1\n")
        assert client._doc_versions[uri] == 2

    def test_bad_version_is_coerced(self, qapp):
        """防御：version 传字符串/None 时强制转 int"""
        from core.lsp_client import LspClient

        client = LspClient()
        uri = "file:///d:/b.py"
        client.did_open(uri, "python", "x\n", version="7")
        assert client._doc_versions[uri] == 7

        uri2 = "file:///d:/c.py"
        client.did_open(uri2, "python", "x\n", version=None)
        assert client._doc_versions[uri2] == 1

    def test_language_id_looks_like_file_content(self, qapp):
        """防御：language_id 疑似整份文件时回退 plaintext"""
        from core.lsp_client import LspClient

        client = LspClient()
        uri = "file:///d:/d.py"
        client.did_open(uri, "print('a')\nprint('b')\n", "x\n")
        assert client._open_documents[uri] == "plaintext"


class TestUriAndLanguage:
    """URI 生成与 languageId 推断"""

    def test_path_to_uri_windows_shape(self):
        from core.lsp_client import LspClient

        uri = LspClient.path_to_uri(r"D:\proj\a.py")
        assert uri.startswith("file:///")
        assert "a.py" in uri
        # 不应出现四斜杠
        assert "file:////" not in uri

    def test_editor_language_id_mapping(self, qapp):
        from core.editor import LSP_LANGUAGE_BY_EXT

        assert LSP_LANGUAGE_BY_EXT['.py'] == 'python'
        assert LSP_LANGUAGE_BY_EXT['.rs'] == 'rust'
        assert LSP_LANGUAGE_BY_EXT['.go'] == 'go'
        assert LSP_LANGUAGE_BY_EXT['.ts'] == 'typescript'


class TestMergedChannelsFixed:
    """stderr 不得并入 LSP 协议流"""

    def test_uses_separate_channels(self, qapp):
        from PyQt5.QtCore import QProcess

        from core.lsp_client import LspClient

        client = LspClient()
        # 不真正启动进程，只验证通道模式取值
        proc = QProcess()
        proc.setProcessChannelMode(QProcess.SeparateChannels)
        assert proc.processChannelMode() == QProcess.SeparateChannels

        # 源码级断言：启动路径必须设置 SeparateChannels，
        # 且不得**调用** setProcessChannelMode(MergedChannels)
        # （注释里提到历史实现是允许的）
        import inspect
        import re
        src = inspect.getsource(LspClient.start)
        assert "setProcessChannelMode(QProcess.SeparateChannels)" in src
        assert not re.search(
            r"setProcessChannelMode\(\s*QProcess\.MergedChannels",
            src,
        )


class TestFrameParserSkipsNoise:
    """帧解析器遇到噪声后仍能解析合法消息"""

    def test_noise_before_valid_frame(self, qapp):
        import json

        from core.lsp_client import LspClient

        client = LspClient()
        received = []
        client._handle_message = lambda m: received.append(m)

        body = json.dumps({"jsonrpc": "2.0", "method": "x", "params": {}})
        body_bytes = body.encode('utf-8')
        frame = (
            b"Content-Length: " + str(len(body_bytes)).encode() +
            b"\r\n\r\n" + body_bytes
        )

        # 前面塞入非协议噪声（模拟旧版 MergedChannels 下的 stderr 日志）
        client._buffer = b"[info] server starting\n" + frame
        client._process_buffer()

        assert len(received) == 1
        assert received[0]["method"] == "x"
