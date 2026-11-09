# -*- coding: utf-8 -*-
"""v2.24 W3：视口优先加载原型 + 性能门禁收紧"""

import importlib.util
import os
import time

import pytest
from PyQt5.Qsci import QsciScintilla


def _load_bench():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "qc_bench_gate", os.path.join(root, "tools", "bench_optimization.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_effective_factor_capped():
    mod = _load_bench()
    assert mod.effective_factor(3.0, 1.0) == 3.0
    assert mod.effective_factor(0.0, 1.0) == 2.0
    assert mod.effective_factor(10.0, 4.0) == 4.0
    assert mod.effective_factor(1.0, 1.5) == 3.0


def test_hard_limits():
    mod = _load_bench()
    probs = mod.evaluate_results({"open_50mb": 9.0}, 4.0)
    assert any(p[0] == "open_50mb" and p[3] == "hard" for p in probs)
    ok = mod.evaluate_results({"open_50mb": 5.0, "mainwindow": 0.2, "session_save": 0.1}, 4.0)
    assert ok == []


def test_viewport_progressive(qapp, tmp_path, monkeypatch):
    from core.document import Document
    from core.editor import EditorProxy

    monkeypatch.setenv("QINGCAO_VIEWPORT_LOAD", "1")
    monkeypatch.setenv("QINGCAO_VIEWPORT_THRESHOLD_MB", "1")
    monkeypatch.setenv("QINGCAO_VIEWPORT_PREFIX_MB", "1")
    path = tmp_path / "huge.txt"
    lines = ["line %06d abcdefghij" % i for i in range(120_000)]
    text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")
    sc = QsciScintilla()
    doc = Document()
    proxy = EditorProxy(sc, doc)
    try:
        assert proxy.open_file(str(path)) is True
        assert getattr(proxy, "_viewport_ready", False) is True
        assert getattr(proxy, "_deferred_loading", False) is True
        assert proxy._load_cursor < proxy._load_total
        deadline = time.time() + 30
        while time.time() < deadline and getattr(proxy, "_deferred_loading", False):
            qapp.processEvents()
            time.sleep(0.01)
        assert getattr(proxy, "_deferred_loading", False) is False
        assert sc.lines() == len(lines) + 1
        assert sc.isModified() is False
    finally:
        try:
            proxy.close()
        except Exception:
            pass
