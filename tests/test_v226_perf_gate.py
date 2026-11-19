# -*- coding: utf-8 -*-
"""Sprint 4：性能门禁"""

import json


def _write(tmp_path, values):
    p = tmp_path / "perf.jsonl"
    lines = [
        json.dumps({"results": {"mainwindow": v, "plugins_fully_ready": v, "open_50mb": v}})
        for v in values
    ]
    p.write_text("\n".join(lines), encoding="utf-8")
    return str(p)


def test_gate_pass_and_fail(tmp_path):
    from tools.perf_gate import evaluate

    ok = _write(tmp_path, [0.3, 0.4, 0.5])
    report, failed = evaluate(ok)
    assert not failed
    bad = _write(tmp_path, [2.0])
    report, failed = evaluate(bad)
    assert "mainwindow" in failed
