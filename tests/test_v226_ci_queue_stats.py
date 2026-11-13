# -*- coding: utf-8 -*-
"""v2.26 R3：CI job 队列统计"""

import importlib.util
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location(
        "qc_ci_queue", os.path.join(ROOT, "tools", "ci_queue_stats.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_job_percentile_and_summary():
    mod = _load()
    assert mod.percentile([], 95) == 0.0
    assert mod.percentile([1, 2, 3, 4], 50) in (2, 3)
    jobs = [
        {
            "workflow_name": "Test",
            "created_at": "2026-11-01T00:00:00Z",
            "started_at": "2026-11-01T00:05:00Z",
            "completed_at": "2026-11-01T00:25:00Z",
        },
        {
            "workflow_name": "Test",
            "created_at": "2026-11-02T00:00:00Z",
            "started_at": "2026-11-02T00:02:00Z",
            "completed_at": "2026-11-02T00:12:00Z",
        },
    ]
    rows = mod.summarize_jobs(jobs)
    assert rows[0]["workflow"] == "Test" and rows[0]["jobs"] == 2
    assert rows[0]["queue_p95"] == 300.0
