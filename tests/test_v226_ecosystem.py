# -*- coding: utf-8 -*-
"""v2.26 P4：评分报告与插件脚手架采用"""

import importlib.util
import json
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location(
        "qc_ratings", os.path.join(ROOT, "tools", "ratings_report.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ratings_report_rows():
    mod = _load()
    rows = mod.build_rows(
        {"demo": {"stars": 5}, "wordcount": {"stars": 4}},
        {"demo": {"count": 3, "average": 4.67}},
    )
    by = {r["plugin"]: r for r in rows}
    assert by["demo"]["local_stars"] == 5
    assert by["demo"]["community_count"] == 3
    assert by["wordcount"]["community_count"] == 0


def test_plugin_scaffold_generates_importable_plugin(tmp_path):
    out = tmp_path / "plugins"
    name = "sample_tool"
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    subprocess.run(
        [
            sys.executable,
            os.path.join(ROOT, "tools", "new_plugin.py"),
            "--name",
            name,
            "--display-name",
            "Sample",
            "--output",
            str(out),
        ],
        check=True,
        capture_output=True,
        env=env,
    )
    plugin_dir = out / name
    assert (plugin_dir / "plugin.json").is_file()
    assert (plugin_dir / "__init__.py").is_file()
    manifest = json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == name
    assert "Plugin" in (plugin_dir / "__init__.py").read_text(encoding="utf-8")


def test_seed_marking():
    mod = _load()
    rows = mod.build_rows(
        {
            "demo": {"stars": 5, "comment": "维护者种子评分（非社区真实用户）"},
            "wordcount": {"stars": 5, "comment": "真实用户"},
        },
        {},
    )
    by = {r["plugin"]: r for r in rows}
    assert by["demo"]["seed"] is True
    assert by["wordcount"]["seed"] is False
    by2 = {r["plugin"]: r for r in mod.build_rows({"legacy": {"stars": 5, "comment": ""}}, {})}
    assert by2["legacy"]["seed"] is True
