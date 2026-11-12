# -*- coding: utf-8 -*-
"""v2.23 P1-2：评分静态聚合"""

import importlib.util
import json
import os


def _load():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "qc_ratings_agg", os.path.join(root, "tools", "build_ratings_aggregate.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, root


def test_aggregate(tmp_path):
    mod, _root = _load()
    src = tmp_path / "plugin_ratings.json"
    src.write_text(
        json.dumps(
            {
                "version": 1,
                "plugins": {
                    "demo": {"stars": 4, "comment": "good"},
                    "other": {"stars": 5},
                    "bad": {"stars": "x"},
                },
            }
        ),
        encoding="utf-8",
    )
    mod.COMMUNITY_TRACKED = str(tmp_path / "none.json")
    data = mod.aggregate(str(src))
    assert data["version"] == 1
    assert data["plugins"]["demo"]["average"] == 4.0
    assert data["plugins"]["demo"]["count"] == 1
    assert "bad" not in data["plugins"]


def test_docs():
    mod, root = _load()
    assert os.path.isfile(os.path.join(root, "docs", "plugin_ratings_aggregate.md"))
