# -*- coding: utf-8 -*-
"""v2.18 P2：崩溃历史分析 / 性能趋势 / NVDA 描述批次"""

import io
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(path, name):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_crash_analysis_scans_fake_logs(tmp_path):
    mod = _load(os.path.join("tools", "analyze_crash_dumps.py"), "qc_crash_an")
    diag = tmp_path / "_diag"
    diag.mkdir()
    (diag / "Worker_20261102-010101-utc.log").write_text(
        "Step result: Failed\nrc=3221225477\n", encoding="utf-8"
    )
    (diag / "Worker_20261103-010101-utc.log").write_text(
        "Job completed\nStep result: Succeeded\n", encoding="utf-8"
    )
    stats = mod.scan_runner_logs(str(diag))
    assert stats["jobs_failed"] >= 1
    assert stats["crash_jobs"] >= 1
    assert stats["crash_dates"]["20261102"] == 1


def test_perf_trend_record_and_report(tmp_path, monkeypatch):
    mod = _load(os.path.join("tools", "perf_trend_report.py"), "qc_perf_trend")
    latest = tmp_path / "latest.json"
    latest.write_text(
        json.dumps({"results": {"open_1mb": 0.5, "open_50mb": 1.5}}), encoding="utf-8"
    )
    hist = tmp_path / "history.jsonl"
    monkeypatch.setenv("QINGCAO_PERF_HISTORY", str(hist))
    ok, msg = mod.record(str(latest))
    assert ok is True, msg
    rows = mod.load_history()
    assert len(rows) == 1
    report = mod.render(rows, {"open_1mb": 1.2})
    assert "open_1mb" in report and "阈值" in report


def test_accessibility_descriptions(qapp):
    from PyQt5.QtWidgets import QLineEdit, QWidget

    from ui.accessibility import apply_accessible_descriptions

    root = QWidget()
    edit = QLineEdit(root)
    edit.setPlaceholderText("搜索插件")
    n = apply_accessible_descriptions(root)
    assert n >= 1
    assert edit.accessibleDescription()
    root.close()


def test_ci_and_docs_wiring():
    yml = open(os.path.join(ROOT, ".github", "workflows", "test.yml"), encoding="utf-8").read()
    assert "perf_trend_report.py --record --report" in yml
    assert "analyze_crash_dumps.py" in yml
    assert os.path.exists(os.path.join(ROOT, "docs", "perf_trend_report.md"))
    assert os.path.exists(os.path.join(ROOT, "docs", "crash_analysis_v2.18.md"))
    main = "".join(
        open(os.path.join(ROOT, _p), encoding="utf-8").read()
        for _p in ("main.py", "app/main_helpers.py", "app/main_run.py")
    )
    assert "apply_accessible_descriptions" in main
