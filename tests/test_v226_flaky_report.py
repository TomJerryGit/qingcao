# -*- coding: utf-8 -*-
"""v2.26：flaky 报告"""

import importlib.util
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location(
        "qc_flaky", os.path.join(ROOT, "tools", "flaky_report.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_summarize_counts_codes_and_pass():
    mod = _load()
    rows = [
        {
            "crash_codes": [3221225477],
            "result": "pass_after_localize",
            "localized": [],
            "iso": "2026-11-16 17:00",
        },
        {"crash_codes": [3221225477, 1], "result": "fail"},
    ]
    s = mod.summarize(rows)
    assert s["events"] == 2
    assert s["crash_codes"]["3221225477"] == 2
    assert s["pass_after_localize"] == 1
    assert s["last"] == "2026-11-16 17:00"


def test_render_writes_report(tmp_path):
    mod = _load()
    out = tmp_path / "f.md"
    mod.render(mod.summarize([]), str(out))
    text = out.read_text(encoding="utf-8")
    assert "Flaky" in text and "事件数：0" in text
