# -*- coding: utf-8 -*-
"""v2.25 崩溃聚合：faulthandler 分组 + flaky 历史"""

import importlib.util
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMP = """Windows fatal exception: access violation

Thread 0x0000 (most recent call first):
  File "D:/QingCaoEditor/ui/main_window.py", line 42 in paintEvent
  File "D:/QingCaoEditor/ui/editor_view.py", line 10 in update
"""


def _load():
    spec = importlib.util.spec_from_file_location(
        "qc_crash_triage", os.path.join(ROOT, "tools", "crash_triage.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parse_dump_extracts_exception_and_top_frame():
    mod = _load()
    exc, top, _ = mod.parse_dump(DUMP)
    assert "access violation" in exc
    assert top == "main_window.py:paintEvent"


def test_aggregate_groups(tmp_path, monkeypatch):
    mod = _load()
    dump_dir = tmp_path / "dumps"
    dump_dir.mkdir()
    (dump_dir / "a.log").write_text(DUMP, encoding="utf-8")
    (dump_dir / "b.log").write_text(DUMP, encoding="utf-8")
    hist = tmp_path / "hist.jsonl"
    hist.write_text(json.dumps({"file": "tests/test_x.py"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        mod, "collect_dumps", lambda extra: [str(dump_dir / "a.log"), str(dump_dir / "b.log")]
    )
    _orig_flaky = mod.collect_flaky
    monkeypatch.setattr(mod, "collect_flaky", lambda path=None: _orig_flaky(str(hist)))
    data = mod.aggregate()
    # 两条相同 dump 合为一组 count=2；flaky 单列
    sig = [k for k in data["groups"] if "access violation" in k]
    assert sig and data["groups"][sig[0]]["count"] == 2
    assert any("CI flaky" in k for k in data["groups"])
    md = mod.render_markdown(data)
    assert "崩溃聚合报告" in md and "access violation" in md


def test_empty_and_frames_only(tmp_path, monkeypatch):
    mod = _load()
    (tmp_path / "empty.log").write_text("", encoding="utf-8")
    (tmp_path / "frames.log").write_text(
        'Thread 0x1 (most recent call first):\n  File "D:/QingCaoEditor/ui/x.py", line 9 in boom\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        mod,
        "collect_dumps",
        lambda extra: [str(tmp_path / "empty.log"), str(tmp_path / "frames.log")],
    )
    monkeypatch.setattr(mod, "collect_minidumps", lambda extra=None: [])
    monkeypatch.setattr(mod, "collect_flaky", lambda path=None: [])
    data = mod.aggregate()
    assert data["empty_files"] == 1
    assert any(k.startswith("uncaught |") for k in data["groups"])
