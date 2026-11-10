import sys

import pytest


# -*- coding: utf-8 -*-
"""v2.17.x P2：崩溃转储 / 大文件搜索跳过 / 批量更新 / NVDA 清单"""
import importlib.util
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 注册表/WER 专用")
def test_crash_dump_tool():
    mod = _load(os.path.join("tools", "enable_crash_dumps.py"), "qc_crash")
    vals = mod.build_values(os.path.join(ROOT, "tmp_crash"))
    assert vals["DumpType"] == 1
    assert "DumpFolder" in vals
    assert isinstance(mod.dump_folder(""), str)
    report = mod.check_dump_config()
    assert set(report) == {"python.exe", "QingCaoEditor.exe"}


def test_search_skips_large_files(tmp_path):
    from core.search import FileSearcher, SearchOptions

    small = tmp_path / "small.txt"
    small.write_text("needle here\n", encoding="utf-8")
    big = tmp_path / "big.txt"
    with open(big, "wb") as f:
        f.seek(11 * 1024 * 1024)
        f.write(b"needle\n")
    searcher = FileSearcher()
    result = searcher.search_sync(
        str(tmp_path), SearchOptions(pattern="needle"), file_filter="*.txt"
    )
    assert getattr(result, "skipped_large", 0) >= 1
    assert str(small) in result.file_results


def test_static_wiring_and_docs():
    main = "".join(
        open(os.path.join(ROOT, _p), encoding="utf-8").read()
        for _p in ("main.py", "app/main_common.py", "app/main_helpers.py", "app/main_run.py")
    )
    assert "faulthandler" in main
    panel = open(os.path.join(ROOT, "ui", "global_search_panel.py"), encoding="utf-8").read()
    assert "skipped_large" in panel
    store = open(os.path.join(ROOT, "ui", "plugin_store.py"), encoding="utf-8").read()
    assert "_update_all" in store and "_check_updates" in store
    yml = open(os.path.join(ROOT, ".github", "workflows", "test.yml"), encoding="utf-8").read()
    assert "enable_crash_dumps.py" in yml
    assert os.path.exists(os.path.join(ROOT, "docs", "ci_qt_crash_playbook.md"))
    assert os.path.exists(os.path.join(ROOT, "docs", "manual_validation_v2.17_nvda.md"))
