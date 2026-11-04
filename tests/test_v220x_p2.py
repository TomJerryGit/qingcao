# -*- coding: utf-8 -*-
"""v2.20.x P2：mmap 跨行 / 评分导入导出 / flaky 报告"""

import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_mmap_cross_line_accept_and_reject():
    from core.mmap_save import plan_incremental_save

    old = b"aaa\nbbb\nccc\nddd\n"
    # 跨两行修改，等长且换行位置不变
    new = b"aaa\nBXB\nCXC\nddd\n"
    assert plan_incremental_save(old, new, 0) is not None
    # 换行位置改变 -> 拒绝
    bad = b"aaa\nbb\nbccc\nddd\n"
    assert plan_incremental_save(old, bad, 0) is None
    # 非等长 -> 拒绝
    assert plan_incremental_save(old, b"aaa\nbbb\nccc\ndd\n", 0) is None


def test_rating_export_import(tmp_path, monkeypatch):
    from ui.plugin_rating import LocalRatings

    a = LocalRatings(str(tmp_path / "a.json"))
    a.set_rating("p1", 5, "great")
    a.set_rating("p2", 3, "ok")
    path = str(tmp_path / "export.json")
    assert a.export_data(path) == 2

    b = LocalRatings(str(tmp_path / "b.json"))
    assert b.import_data(path, merge=True) == 2
    assert b.get("p1")["stars"] == 5
    c = LocalRatings(str(tmp_path / "c.json"))
    c.set_rating("old", 2)
    assert c.import_data(path, merge=False) == 2
    assert c.get("old") is None


def test_flaky_report(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "qc_flaky", os.path.join(ROOT, "tools", "ci_flaky_report.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    hist = tmp_path / "h.jsonl"
    hist.write_text(
        json.dumps({"ts": 1.0, "crash_codes": [3221225477], "files": 44}) + "\n", encoding="utf-8"
    )
    rows = mod.load_history(str(hist))
    assert len(rows) == 1
    report = mod.render(rows)
    assert "累计触发 fallback | 1" in report
    assert "决策建议" in report


def test_p2_docs_and_wiring():
    assert os.path.isfile(os.path.join(ROOT, "docs", "terminal_feature_proposal.md"))
    sr = open(os.path.join(ROOT, "tools", "run_tests_sharded.py"), encoding="utf-8").read()
    assert "ci_flaky_history" in sr
