# -*- coding: utf-8 -*-
"""v2.24.x：视口加载默认开启回归（完整性/脏标记/撤销/搜索）"""

import time

from PyQt5.Qsci import QsciScintilla


def _make(path, lines=120_000):
    rows = ["line %06d abcdefghij" % i for i in range(lines)]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return len(rows) + 1


def _load(qapp, path):
    from core.document import Document
    from core.editor import EditorProxy

    sc = QsciScintilla()
    doc = Document()
    proxy = EditorProxy(sc, doc)
    return sc, proxy


def test_default_auto_viewport_semantics(qapp, tmp_path, monkeypatch):
    monkeypatch.delenv("QINGCAO_VIEWPORT_LOAD", raising=False)
    monkeypatch.setenv("QINGCAO_VIEWPORT_THRESHOLD_MB", "1")
    monkeypatch.setenv("QINGCAO_VIEWPORT_PREFIX_MB", "1")
    path = tmp_path / "big.txt"
    expected = _make(path)
    sc, proxy = _load(qapp, path)
    try:
        assert proxy.open_file(str(path)) is True
        # 默认自动启用：渐进加载
        assert getattr(proxy, "_viewport_ready", False) is True
        deadline = time.time() + 30
        while time.time() < deadline and getattr(proxy, "_deferred_loading", False):
            qapp.processEvents()
            time.sleep(0.01)
        assert getattr(proxy, "_deferred_loading", False) is False
        assert sc.lines() == expected
        # 脏标记：加载完成不应把文档标记为已修改
        assert proxy.is_modified is False
        # 撤销栈：加载本身不入栈（加载后无可撤销编辑）
        assert proxy.can_undo() is False
        # 搜索：全文完整后可命中末尾内容
        assert sc.findFirst("line 011999", False, False, False, True) is True
        # 编辑 -> 撤销回原内容
        sc.insertAt("X", 0, 0)
        assert proxy.is_modified is True
        assert proxy.can_undo() is True
        proxy.undo()
        assert sc.text().startswith("line 000000")
    finally:
        try:
            proxy.close()
        except Exception:
            pass


def test_disable_via_env(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("QINGCAO_VIEWPORT_LOAD", "0")
    monkeypatch.setenv("QINGCAO_VIEWPORT_THRESHOLD_MB", "1")
    path = tmp_path / "big2.txt"
    expected = _make(path, 50_000)
    sc, proxy = _load(qapp, path)
    try:
        assert proxy.open_file(str(path)) is True
        assert proxy._load_cursor == proxy._load_total
        assert sc.lines() == expected
    finally:
        try:
            proxy.close()
        except Exception:
            pass
