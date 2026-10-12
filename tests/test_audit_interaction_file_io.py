# -*- coding: utf-8 -*-
"""
交互审计：编码 / 行尾 / 保存 × LSP 文件操作
=========================================

覆盖的交互：
    1. 行尾符 × 保存     —— 切换 EOL 只改元数据，写盘不转换
    2. 编码 × 保存       —— 切换编码只重载 provider，编辑器不刷新，
                            随后保存会把乱码按新编码写回磁盘
    3. 另存为 × LSP      —— document.filepath 变了，_lsp_uri 没变
    4. 诊断 × URI        —— _on_lsp_diagnostics 忽略 uri 参数

断言不变式：
    INV-E1  切换 EOL 后保存，磁盘上的行尾必须变成目标样式。
    INV-E2  切换编码后，编辑器可见文本必须与 provider 解码结果一致；
            保存写回的字节必须等于该文本按新编码的编码结果。
    INV-L1  另存为后，LSP 的文档 URI 必须指向新路径。
    INV-L2  诊断只允许绘制到其 uri 对应的编辑器上。

运行方式：
    python -m pytest tests/test_audit_interaction_file_io.py -v
"""

import pytest


def _make_editor(qapp, path):
    from PyQt5.Qsci import QsciScintilla

    from core.document import Document
    from core.editor import EditorProxy

    sc = QsciScintilla()
    sc.setUtf8(True)
    proxy = EditorProxy(sc, Document())
    assert proxy.open_file(str(path)) is True
    return sc, proxy


# ============================================================
# 1. 行尾符 × 保存
# ============================================================
class TestEolVsSave:

    @pytest.mark.audit_expected_fail
    def test_eol_switch_is_written_to_disk(self, qapp, tmp_path):
        """ui/mixins/status_bar_mixin.py:191-205 -> Document.set_eol
        (core/document.py:620-623) 只设置 meta.eol + mark_modified()；
        core/content_provider.py:306-311 encode() 不做任何行尾转换；
        Document.convert_eol (core/document.py:632) 在生产代码中
        从未被调用（全仓 grep 只有定义处）。
        """
        p = tmp_path / "eol.txt"
        p.write_bytes(b"a\nb\n")

        sc, proxy = _make_editor(qapp, p)

        # 状态栏切换 LF -> CRLF
        proxy.document.set_eol("\r\n")
        assert proxy.document.meta.eol == "\r\n"

        assert proxy.save_file() is True

        data = p.read_bytes()
        assert data == b"a\r\nb\r\n", (
            "INV-E1 违反：切换行尾符后保存，磁盘上仍是 LF。"
            f" 实际字节={data!r}"
        )

    @pytest.mark.audit_expected_fail
    def test_eol_roundtrip_after_reopen(self, qapp, tmp_path):
        """再打开应保持新行尾。"""
        p = tmp_path / "eol2.txt"
        p.write_bytes(b"a\nb\n")

        sc, proxy = _make_editor(qapp, p)
        proxy.document.set_eol("\r\n")
        proxy.save_file()

        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy

        sc2 = QsciScintilla()
        sc2.setUtf8(True)
        proxy2 = EditorProxy(sc2, Document())
        assert proxy2.open_file(str(p)) is True

        assert proxy2.document.meta.eol == "\r\n", (
            "重新打开后行尾显示为 "
            f"{proxy2.document.meta.eol!r}，切换结果未持久化。"
        )


# ============================================================
# 2. 编码 × 保存
# ============================================================
class TestEncodingVsEditor:

    @pytest.mark.audit_expected_fail
    def test_encoding_switch_refreshes_editor_text(self, qapp, tmp_path):
        """ui/mixins/status_bar_mixin.py:177-188 -> Document.change_encoding
        (core/document.py:593-615) 重载了 provider，但没有任何代码
        把新解码结果写回 EditorProxy.sc。于是编辑器继续显示旧编码
        解出的乱码，provider 却已是正确文本。
        """
        p = tmp_path / "enc.txt"
        p.write_bytes("中文内容\n".encode("utf-8"))

        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy

        sc = QsciScintilla()
        sc.setUtf8(True)
        proxy = EditorProxy(sc, Document())

        # 以错误的编码打开（用户手动指定 GBK）
        assert proxy.document.open(str(p), encoding="gbk") is True
        assert proxy.open_file() is True

        garbled = sc.text()
        assert garbled != "中文内容\n", "前置条件：应先是乱码"

        # 状态栏切换编码到 utf-8
        proxy.document.change_encoding("utf-8")

        assert sc.text() == proxy.document.get_text(), (
            "INV-E2 违反：切换编码只重载了 provider，编辑器未刷新。"
            f" 编辑器={sc.text()!r} provider={proxy.document.get_text()!r}"
        )
        assert sc.text() == "中文内容\n", (
            f"切换编码后编辑器应为正确文本，实际 {sc.text()!r}"
        )

    @pytest.mark.audit_expected_fail
    def test_encoding_switch_then_save_does_not_corrupt(self, qapp, tmp_path):
        """切换编码后保存，磁盘字节必须等于正确文本按新编码的结果。"""
        p = tmp_path / "enc2.txt"
        correct = "中文内容\n"
        p.write_bytes(correct.encode("utf-8"))

        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy

        sc = QsciScintilla()
        sc.setUtf8(True)
        proxy = EditorProxy(sc, Document())
        assert proxy.document.open(str(p), encoding="gbk") is True
        assert proxy.open_file() is True

        proxy.document.change_encoding("utf-8")
        assert proxy.save_file() is True

        data = p.read_bytes()
        assert data == correct.encode("utf-8"), (
            "INV-E2 违反：先以 GBK 读入、再切到 UTF-8 保存，"
            "写回磁盘的是'乱码文本按 UTF-8 重编码'的字节，"
            "文件被永久破坏（无法再通过切换编码恢复）。"
            f" 实际={data!r}"
        )


# ============================================================
# 3. 另存为 × LSP
# ============================================================
class TestSaveAsVsLsp:

    @pytest.mark.audit_expected_fail
    def test_save_as_updates_lsp_uri(self, qapp, tmp_path):
        """ui/mixins/file_ops_mixin.py:230 走 Document.save(path)，
        它更新了 document.filepath（core/document.py:403-407），
        但 EditorProxy._lsp_uri 保持旧值（core/editor.py:218,1895）。
        之后 _sync_lsp_document 会把新内容发给旧 URI。
        """
        from core.lsp_client import LspClient

        src = tmp_path / "a.py"
        src.write_text("x = 1\n", encoding="utf-8")

        sc, proxy = _make_editor(qapp, src)

        # 模拟已启用 LSP（不需要真实服务器）
        proxy.lsp_active = True
        proxy._lsp_uri = LspClient.path_to_uri(proxy.document.filepath)

        dst = tmp_path / "b.py"
        assert proxy.document.save(str(dst)) is True
        assert proxy.document.filepath == str(dst)

        assert proxy._lsp_uri == LspClient.path_to_uri(str(dst)), (
            "INV-L1 违反：另存为后 LSP 文档 URI 仍指向旧路径 "
            f"{proxy._lsp_uri!r}，而文件已是 {proxy.document.filepath!r}。"
            " 后果：didChange 发给旧文档、服务器对旧路径诊断、"
            "request_completion 用新路径服务器不认识 -> 补全失效。"
        )

    @pytest.mark.audit_expected_fail
    def test_lsp_did_save_uses_stale_uri_after_save_as(
            self, qapp, tmp_path):
        """另存为后 _notify_lsp_saved 仍用旧 URI
        （core/editor.py:770-780 里 `self._lsp_uri or ...` 优先取旧值）。
        """
        from core.lsp_client import LspClient

        src = tmp_path / "a.py"
        src.write_text("x = 1\n", encoding="utf-8")
        sc, proxy = _make_editor(qapp, src)

        old_uri = LspClient.path_to_uri(proxy.document.filepath)

        sent = {}

        class _FakeLsp:
            def did_save(self, uri, text=None):
                sent['did_save'] = uri

            def did_change(self, uri, text):
                sent['did_change'] = uri

            def did_close(self, uri):
                sent['did_close'] = uri

        proxy.lsp_active = True
        proxy.lsp_client = _FakeLsp()
        proxy._lsp_uri = old_uri

        dst = tmp_path / "b.py"
        assert proxy.document.save(str(dst)) is True
        proxy._notify_lsp_saved()

        assert sent.get('did_save') == LspClient.path_to_uri(str(dst)), (
            "另存为后 didSave 仍发往旧 URI "
            f"{sent.get('did_save')!r}，实际文件已是 "
            f"{proxy.document.filepath!r}"
        )


# ============================================================
# 4. 诊断 × URI（跨标签状态泄漏）
# ============================================================
class TestDiagnosticsUriIsolation:

    @pytest.mark.audit_expected_fail
    def test_diagnostics_for_foreign_uri_are_ignored(self, qapp, tmp_path):
        """core/editor.py:1951 的 _on_lsp_diagnostics(uri, diagnostics)
        完全没有比较 uri 与 self._lsp_uri，任何来源的诊断都会被画到
        当前编辑器上 —— 这是"标签 A 的诊断出现在标签 B"的通道。
        """
        p = tmp_path / "a.py"
        p.write_text("x = 1\n", encoding="utf-8")
        sc, proxy = _make_editor(qapp, p)

        from core.lsp_client import LspClient
        proxy._lsp_uri = LspClient.path_to_uri(proxy.document.filepath)
        proxy.lsp_active = True

        foreign_uri = LspClient.path_to_uri(str(tmp_path / "other.py"))
        assert foreign_uri != proxy._lsp_uri, "前置条件：URI 应不同"

        diag = [{
            "range": {"start": {"line": 0, "character": 0},
                      "end": {"line": 0, "character": 1}},
            "message": "foreign", "severity": 1,
        }]
        proxy._on_lsp_diagnostics(foreign_uri, diag)

        # INDICATOR_LSP_ERROR == 2；SCI_INDICATORVALUEAT = 2082
        indic_value_at = getattr(sc, "SCI_INDICATORVALUEAT", 2082)
        value = sc.SendScintilla(indic_value_at, 2, 0)

        assert value == 0, (
            "INV-L2 违反：属于其它 URI 的诊断被绘制到了当前编辑器，"
            "造成跨标签/跨文件的状态泄漏。"
            f" indicator_value_at(pos=0)={value}"
        )


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-v"]))
