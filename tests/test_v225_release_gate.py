# -*- coding: utf-8 -*-
"""v2.25 CI：发布前置门禁"""

import importlib.util
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location(
        "qc_release_gate", os.path.join(ROOT, "tools", "ci_release_gate.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_evaluate_states():
    mod = _load()
    assert mod.evaluate(None)[0] is None
    assert mod.evaluate({"status": "queued"})[0] is None
    assert mod.evaluate({"status": "completed", "conclusion": "success"})[0] is True
    ok, state, _ = mod.evaluate({"status": "completed", "conclusion": "failure"})
    assert ok is False and state == "failure"


def test_wait_all_uses_latest(monkeypatch):
    mod = _load()
    runs = {
        "test.yml": {"status": "completed", "conclusion": "success", "id": 1},
        "security.yml": {"status": "completed", "conclusion": "success", "id": 2},
        "lint.yml": {"status": "completed", "conclusion": "failure", "id": 3},
    }
    monkeypatch.setattr(mod, "workflow_latest", lambda repo, wf, sha, token=None: runs[wf])
    assert mod.wait_all("o/r", "sha", None, 1, 0, tuple(runs)) is False
    runs["lint.yml"] = {"status": "completed", "conclusion": "success", "id": 4}
    assert mod.wait_all("o/r", "sha", None, 1, 0, tuple(runs)) is True


def test_release_workflow_has_gate():
    text = open(os.path.join(ROOT, ".github", "workflows", "release.yml"), encoding="utf-8").read()
    assert "ci_release_gate.py" in text
    assert "needs: gates" in text


def test_fallback_alternative_success(monkeypatch):
    mod = _load()
    runs = {
        "test.yml": {"status": "completed", "conclusion": "failure", "id": 1},
        "security.yml": {"status": "completed", "conclusion": "success", "id": 2},
        "lint.yml": {"status": "completed", "conclusion": "success", "id": 3},
        "test-fallback.yml": {"status": "completed", "conclusion": "success", "id": 4},
    }

    def fake_latest(repo, wf, sha, token=None):
        return runs.get(wf)

    monkeypatch.setattr(mod, "workflow_latest", fake_latest)
    assert (
        mod.wait_all(
            "o/r", "sha", None, 1, 0, ("test.yml", "security.yml", "lint.yml"), "test-fallback.yml"
        )
        is True
    )
