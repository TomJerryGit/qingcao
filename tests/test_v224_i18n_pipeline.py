# -*- coding: utf-8 -*-
"""v2.24.x i18n 工作清单/应用流水线"""

import importlib.util
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "tools", rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_worklist_prioritizes_frequent():
    mod = _load("qc_wl", "i18n_batch_worklist.py")
    rows, freq = mod.build(limit=5)
    assert len(rows) == 5
    vals = [freq.get(s, 0) for s in rows]
    assert vals == sorted(vals, reverse=True)


def test_apply_validates_and_writes(tmp_path):
    mod = _load("qc_ap", "i18n_apply_batch.py")
    (tmp_path / "ja_JP").mkdir()
    (tmp_path / "ko_KR").mkdir()
    tsv = tmp_path / "w.tsv"
    tsv.write_text(
        "zh\tja\tko\tfreq\n保存\t保存する\t저장\t5\n格式 %s\tフォーマット %d\t형식 %s\t1\n",
        encoding="utf-8",
    )
    assert mod.validate("保存", "保存する", "저장") == []
    assert mod.validate("格式 %s %s", "フォーマット %s", "형식 %s")
    import sys

    old = sys.argv
    sys.argv = ["apply", str(tsv), "--locale-dir", str(tmp_path)]
    try:
        assert mod.main() == 0
    finally:
        sys.argv = old
    ja = json.load(open(tmp_path / "ja_JP" / "strings.json", encoding="utf-8"))
    ko = json.load(open(tmp_path / "ko_KR" / "strings.json", encoding="utf-8"))
    assert ja["保存"] == "保存する" and ko["保存"] == "저장"
