# -*- coding: utf-8 -*-
"""v2.20 P1-2：mmap 埋点与默认开启评估"""

import io
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_telemetry_records(tmp_path, monkeypatch):
    monkeypatch.setenv("QINGCAO_MMAP_SAVE", "1")
    monkeypatch.setenv("QINGCAO_MMAP_SAVE_MIN_MB", "0")
    eval_file = tmp_path / "eval.jsonl"
    monkeypatch.setenv("QINGCAO_MMAP_EVAL_FILE", str(eval_file))
    monkeypatch.setenv("QINGCAO_EDIT_JOURNAL_DIR", str(tmp_path / "j"))
    import core.mmap_save as m

    path = tmp_path / "a.txt"
    path.write_text("aaaa\nbbbb\n", encoding="utf-8")
    old = path.read_bytes()
    new = old.replace(b"bbbb", b"BBBB")
    assert m.maybe_incremental_save(str(path), new, clear_dirty=lambda: None) is True
    events = [json.loads(x)["event"] for x in eval_file.read_text(encoding="utf-8").splitlines()]
    assert "success" in events


def test_report_generated_and_threshold(monkeypatch, tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "qc_mmap_eval", os.path.join(ROOT, "tools", "mmap_eval_report.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import core.mmap_save as _m

    _m._EVAL_FILE = None  # 清除跨测试缓存的埋点路径
    with __import__("tempfile").TemporaryDirectory() as tmp:
        scen = mod.run_scenarios(os.path.join(tmp, "e.jsonl"), os.path.join(tmp, "j"))
        agg = mod.aggregate(os.path.join(tmp, "e.jsonl"))
    assert scen["equal"][0] is True
    assert scen["fallback"] is None
    assert scen["recovery"] is True
    assert agg["fallback_rate"] < 5
    assert agg["success"] >= 1
    doc = os.path.join(ROOT, "docs", "mmap_default_evaluation.md")
    assert os.path.isfile(doc)
    text = io.open(doc, encoding="utf-8").read()
    assert "门槛判定" in text and "决策" in text


def test_settings_ui_wired():
    src = io.open(os.path.join(ROOT, "core", "mmap_save.py"), encoding="utf-8").read()
    assert "_record(" in src
    assert "QINGCAO_MMAP_EVAL_FILE" in src
