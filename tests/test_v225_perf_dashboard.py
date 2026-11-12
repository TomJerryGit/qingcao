# -*- coding: utf-8 -*-
"""v2.25 性能看板生成"""

import importlib.util
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location(
        "qc_perf_dashboard", os.path.join(ROOT, "tools", "perf_dashboard.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_html_with_samples():
    mod = _load()
    rows = [
        {
            "ts": "2026-11-01T00:00:00",
            "results": {
                "mainwindow": 0.5,
                "plugin_ready_after": 1.2,
                "open_50mb": 3.0,
                "theme_reapply": 0.0,
            },
        },
        {
            "ts": "2026-11-02T00:00:00",
            "results": {
                "mainwindow": 0.4,
                "plugin_ready_after": 0.9,
                "open_50mb": 2.5,
                "theme_reapply": 0.0,
            },
        },
    ]
    out = mod.build_html(rows)
    assert "<svg" in out and "启动 MainWindow" in out
    assert "0.4" in out and "2 条" in out


def test_empty_history():
    mod = _load()
    out = mod.build_html([])
    assert "暂无性能历史数据" in out


def test_load_history_jsonl(tmp_path):
    mod = _load()
    p = tmp_path / "h.jsonl"
    p.write_text(
        json.dumps({"ts": "x", "results": {"mainwindow": 1}}) + "\nbad\n", encoding="utf-8"
    )
    rows = mod.load_history(str(p))
    assert len(rows) == 1
