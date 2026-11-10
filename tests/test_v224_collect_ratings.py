# -*- coding: utf-8 -*-
"""v2.24 真实评分收集：多份用户导出合并 + 社区聚合"""

import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))


def _load(name):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        name, os.path.join(ROOT, "tools", "collect_ratings.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_merge_two_user_submissions(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps({"plugins": {"demo": {"stars": 5}}}), encoding="utf-8")
    b.write_text(
        json.dumps({"plugins": {"demo": {"stars": 3}, "x": {"average": 4, "count": 2}}}),
        encoding="utf-8",
    )
    mod = _load("qc_collect")
    plugins, sources = mod.merge([str(a), str(b)])
    assert sources == ["a.json", "b.json"]
    assert plugins["demo"]["average"] == 4.0 and plugins["demo"]["count"] == 2
    assert plugins["x"]["count"] == 2


def test_aggregate_includes_community(tmp_path, monkeypatch):
    import importlib.util

    community = tmp_path / "community.json"
    community.write_text(
        json.dumps({"plugins": {"demo": {"average": 4.5, "count": 2}}}), encoding="utf-8"
    )
    spec = importlib.util.spec_from_file_location(
        "qc_agg2", os.path.join(ROOT, "tools", "build_ratings_aggregate.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "COMMUNITY", str(community))
    monkeypatch.setattr(mod, "SRC", str(tmp_path / "missing.json"))
    data = mod.aggregate()
    assert data["source"] == "local+community"
    assert data["plugins"]["demo"]["average"] == 4.5
