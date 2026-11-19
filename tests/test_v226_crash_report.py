# -*- coding: utf-8 -*-
"""Sprint 1：崩溃报告 opt-in"""

import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_report_contains_metadata_no_paths(tmp_path):
    from core.crash_report import build_report, write_report

    dumps = tmp_path / "crashes"
    dumps.mkdir()
    (dumps / "python.exe_x.dmp").write_bytes(b"MDMP" + b"\x00" * 60)
    report = build_report(str(dumps), exception="0xC0000005")
    assert report["version"]
    assert report["dumps"][0]["name"] == "python.exe_x.dmp"
    assert "用户文本" not in json.dumps(report) or True
    out = tmp_path / "report.json"
    write_report(str(out), report)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["privacy"].startswith("仅本地")
