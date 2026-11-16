# -*- coding: utf-8 -*-
"""v2.26 P4：插件目录 + 性能趋势"""

import importlib.util
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "tools", fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_plugin_catalog_collect_and_render(tmp_path):
    mod = _load("qc_catalog", "plugin_catalog.py")
    a = tmp_path / "a"
    a.mkdir()
    (a / "plugin.json").write_text(
        json.dumps(
            {
                "name": "a",
                "display_name": "A",
                "version": "1.0",
                "category": "tool",
                "permissions": ["editor_read"],
            }
        ),
        encoding="utf-8",
    )
    rows = mod.collect(str(tmp_path))
    assert len(rows) == 1 and rows[0]["name"] == "a"
    out = tmp_path / "c.md"
    total, sandbox = mod.render(rows, str(out))
    assert total == 1 and sandbox == 0
    assert "| `a` |" in out.read_text(encoding="utf-8")


def test_perf_trend_summary(tmp_path):
    mod = _load("qc_trend", "perf_trend.py")
    rows = []
    for i in range(40):
        rows.append(
            {
                "ts": "2026-11-01T00:%02d:00" % i,
                "results": {
                    "mainwindow": 0.3 if i >= 20 else 0.4,
                    "plugin_ready_after": 0.5,
                    "open_50mb": 1.0,
                    "theme_reapply": 0.01,
                },
            }
        )
    stats = mod.summarize(rows)
    by = {s["key"]: s for s in stats}
    assert by["mainwindow"]["current"] == 0.3
    assert by["mainwindow"]["previous"] == 0.4
    assert by["mainwindow"]["delta_pct"] < 0


def test_perf_trend_workflow_static():
    src = open(
        os.path.join(ROOT, ".github", "workflows", "perf-trend.yml"), encoding="utf-8"
    ).read()
    assert "perf_trend.py" in src and "upload-artifact" in src
