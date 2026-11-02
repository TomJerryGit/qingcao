from ui_source_utils import read_main_ui_source


# -*- coding: utf-8 -*-
"""v2.17 大文件性能：模式/阈值/基准"""
import importlib.util
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(path, name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_large_file_thresholds(tmp_path):
    from core.large_file import (
        HUGE_FILE_THRESHOLD_BYTES,
        LARGE_FILE_THRESHOLD_BYTES,
        apply_large_file_mode,
        file_size,
        is_huge_file,
        is_large_file,
    )
    small = tmp_path / "small.txt"
    small.write_text("x", encoding="utf-8")
    assert file_size(str(small)) == 1
    assert is_large_file(str(small)) is False
    big = tmp_path / "big.txt"
    with open(big, "wb") as f:
        f.seek(LARGE_FILE_THRESHOLD_BYTES - 1)
        f.write(b"x")
    assert is_large_file(str(big)) is True
    assert is_huge_file(str(big)) is False
    huge = tmp_path / "huge.txt"
    with open(huge, "wb") as f:
        f.seek(HUGE_FILE_THRESHOLD_BYTES - 1)
        f.write(b"x")
    assert is_huge_file(str(huge)) is True


def test_live_diag_limit_configurable(monkeypatch):
    from core.large_file import live_diagnostics_limit_bytes
    monkeypatch.setenv("QINGCAO_LIVE_DIAGNOSTICS_MAX_MB", "8")
    assert live_diagnostics_limit_bytes() == 8 * 1024 * 1024
    monkeypatch.setenv("QINGCAO_LIVE_DIAGNOSTICS_MAX_MB", "1")
    assert live_diagnostics_limit_bytes() == 1 * 1024 * 1024


def test_apply_large_file_mode_real_widget(qapp):
    from PyQt5.Qsci import QsciScintilla

    from core.large_file import apply_large_file_mode
    sc = QsciScintilla()
    try:
        assert apply_large_file_mode(sc, huge=True) is True
        assert getattr(sc, "_qc_large_file", False) is True
        assert getattr(sc, "_qc_huge_file", False) is True
    finally:
        sc.deleteLater()


def test_wiring_and_bench():
    tabs = open(os.path.join(ROOT, "app", "tabs.py"),
                encoding="utf-8").read()
    assert "apply_large_file_mode" in tabs
    win = read_main_ui_source()
    assert "_live_diag_limit" in win
    bench = open(os.path.join(ROOT, "tools", "bench_optimization.py"),
                 encoding="utf-8").read()
    assert "open_50mb" in bench
    assert "_wait_loaded" in bench
    editor = open(os.path.join(ROOT, "core", "editor.py"),
                  encoding="utf-8").read()
    assert "_SYNC_LOAD_LIMIT = 64 * 1024 * 1024" in editor