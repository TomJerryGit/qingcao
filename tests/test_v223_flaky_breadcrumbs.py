# -*- coding: utf-8 -*-
"""v2.23 D5：flaky 面包屑 + 报告门禁"""

import json
import os
import time


def _load():
    import importlib.util

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "qc_flaky2", os.path.join(root, "tools", "ci_flaky_report.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, root


def test_breadcrumb_roundtrip(tmp_path):
    import importlib.util

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "qc_shard_runner", os.path.join(root, "tools", "run_tests_sharded.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    path = str(tmp_path / "last_stage.json")
    mod.write_breadcrumb("localize", path=path, file="test_x.py")
    rec = mod.read_breadcrumb(path)
    assert rec["stage"] == "localize"
    assert rec["file"] == "test_x.py"


def test_gate_and_render(tmp_path):
    mod, _root = _load()
    now = time.time()
    rows = [
        {"ts": now - i * 60, "crash_codes": [3221225477], "files": 40, "localized": ["test_a.py"]}
        for i in range(4)
    ]
    assert mod.count_recent(rows, 7, now) == 4
    assert mod.should_fail(rows, 3, now) is True
    assert mod.should_fail(rows[:2], 3, now) is False
    crumb = {"iso": "2026-11-09 10:00", "stage": "flaky_pass", "crash_codes": [3221225477]}
    text = mod.render(rows, crumb, now)
    assert "最近阶段面包屑" in text and "flaky_pass" in text
    assert "test_a.py" in text
    assert "决策建议" in text


def test_docs_and_ci_wired():
    mod, root = _load()
    assert os.path.isfile(os.path.join(root, "docs", "ci_flaky_breadcrumbs.md"))
    runner = open(os.path.join(root, "tools", "run_tests_sharded.py"), encoding="utf-8").read()
    assert "write_breadcrumb" in runner and "last_stage.json" in runner
    yml = open(os.path.join(root, ".github", "workflows", "test.yml"), encoding="utf-8").read()
    assert "ci_flaky_report.py --check" in yml
    rows = mod.load_history(os.path.join(root, "data", "ci_flaky_history.jsonl"))
    assert isinstance(rows, list)
