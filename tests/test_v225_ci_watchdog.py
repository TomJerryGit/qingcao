# -*- coding: utf-8 -*-
"""v2.25 CI 可靠性：watchdog + 超时配置"""

import os
from datetime import datetime, timedelta, timezone


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "qc_ci_watchdog", os.path.join(ROOT, "tools", "ci_watchdog.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_stale_runs_filtering():
    mod = _load()
    now = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
    runs = [
        {"id": 1, "created_at": (now - timedelta(minutes=180)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"id": 2, "created_at": (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"id": 3, "created_at": "bad"},
    ]
    stale = mod.stale_runs(runs, 120, now=now)
    assert [r["id"] for r in stale] == [1]


def test_cancel_uses_post(monkeypatch):
    mod = _load()
    calls = []

    def fake_req(url, method="GET", token=None):
        calls.append((url, method, token))
        return {}

    monkeypatch.setattr(mod, "_req", fake_req)
    mod.cancel_run("o/r", 42, "tk")
    assert calls and calls[0][1] == "POST" and "42" in calls[0][0]
    assert calls[0][2] == "tk"


def test_fallback_dedupe_and_dispatch(monkeypatch):
    mod = _load()
    calls = []

    def fake_req(url, method="GET", token=None, data=None):
        calls.append((url, method, data))
        if "dispatches" in url:
            return {}
        return {
            "workflow_runs": [
                {"status": "queued", "conclusion": None},
            ]
        }

    monkeypatch.setattr(mod, "_req", fake_req)
    assert mod.has_fallback_run("o/r", "test-fallback.yml", "abc", "tk") is True
    mod.dispatch_fallback("o/r", "test-fallback.yml", "main", "tk")
    assert calls[-1][1] == "POST" and calls[-1][2] == {"ref": "main"}


def test_workflows_have_timeouts_and_watchdog():
    wf = os.path.join(ROOT, ".github", "workflows")
    for name in (
        "test.yml",
        "release.yml",
        "security.yml",
        "lint.yml",
        "linux-build.yml",
        "publish_registry.yml",
    ):
        text = open(os.path.join(wf, name), encoding="utf-8").read()
        assert "timeout-minutes:" in text, name
    dog = open(os.path.join(wf, "ci-watchdog.yml"), encoding="utf-8").read()
    assert "actions: write" in dog and "--cancel" in dog
    assert "--fallback-workflow" in dog
    fb = open(os.path.join(wf, "test-fallback.yml"), encoding="utf-8").read()
    assert "windows-latest" in fb and "run_tests_sharded.py" in fb
