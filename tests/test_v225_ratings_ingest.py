# -*- coding: utf-8 -*-
"""v2.25 评分运营：Issue 收集/幂等/加权合并"""

import importlib.util
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BODY = "评分 JSON\n\n```json\n%2\n```"


def _load():
    spec = importlib.util.spec_from_file_location(
        "qc_issue_ingest", os.path.join(ROOT, "tools", "collect_issue_ratings.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parse_issue_body():
    mod = _load()
    body = '```json\n{"plugins": {"demo": {"stars": 5}}}\n```'
    data = mod.parse_issue_body(body)
    assert data["plugins"]["demo"]["stars"] == 5
    assert mod.parse_issue_body("no json") is None


def test_merge_submission_weighted():
    mod = _load()
    community = {
        "version": 1,
        "plugins": {"demo": {"average": 4.0, "count": 2, "sources": ["community"]}},
    }
    out = mod.merge_submission(community, {"plugins": {"demo": {"stars": 5}}}, 12)
    rec = out["plugins"]["demo"]
    assert rec["count"] == 3
    assert rec["average"] == 4.33
    assert "issue:12" in rec["sources"]


def test_run_idempotent(tmp_path, monkeypatch):
    mod = _load()
    community = tmp_path / "community_ratings.json"
    ingested = tmp_path / "ratings_ingested.json"
    community.write_text(json.dumps({"version": 1, "plugins": {}}), encoding="utf-8")
    monkeypatch.setattr(mod, "COMMUNITY", str(community))
    monkeypatch.setattr(mod, "INGESTED", str(ingested))
    issues = [{"number": 7, "body": '```json\n{"plugins": {"demo": {"stars": 5}}}\n```'}]
    monkeypatch.setattr(mod, "fetch_issues", lambda repo, token, label=None: issues)
    r1 = mod.run("o/r", "", dry_run=False)
    assert r1["added"] == 1
    r2 = mod.run("o/r", "", dry_run=False)
    assert r2["added"] == 0
