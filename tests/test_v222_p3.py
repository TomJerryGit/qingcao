# -*- coding: utf-8 -*-
"""v2.22 P3：mmap 埋点 target + 终端命令历史"""

import json
import os
import time

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest


def _pump(qapp, panel, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if panel._proc is None:
            return True
        time.sleep(0.02)
    return False


def test_mmap_records_target(tmp_path, monkeypatch):
    monkeypatch.setenv("QINGCAO_MMAP_SAVE", "1")
    monkeypatch.setenv("QINGCAO_MMAP_SAVE_MIN_MB", "0")
    eval_file = tmp_path / "eval.jsonl"
    monkeypatch.setenv("QINGCAO_MMAP_EVAL_FILE", str(eval_file))
    monkeypatch.setenv("QINGCAO_EDIT_JOURNAL_DIR", str(tmp_path / "j"))
    import core.mmap_save as m

    path = tmp_path / "a.txt"
    path.write_text("aaaa\n", encoding="utf-8")
    # 非等长 → ineligible，应记录 target
    m.maybe_incremental_save(str(path), b"short", None)
    rows = [json.loads(x) for x in eval_file.read_text(encoding="utf-8").splitlines()]
    assert rows and rows[-1]["event"] == "ineligible"
    assert rows[-1]["target"] == str(path)


def test_terminal_command_history(qapp):
    from ui.terminal_panel import TerminalPanel

    panel = TerminalPanel(None)
    try:
        panel.input.setText("echo hist-one")
        panel.run_command()
        assert _pump(qapp, panel)
        panel.input.setText("echo hist-two")
        panel.run_command()
        assert _pump(qapp, panel)
        QTest.keyClick(panel.input, Qt.Key_Up)
        assert panel.input.text() == "echo hist-two"
        QTest.keyClick(panel.input, Qt.Key_Up)
        assert panel.input.text() == "echo hist-one"
        QTest.keyClick(panel.input, Qt.Key_Down)
        assert panel.input.text() == "echo hist-two"
    finally:
        panel.close()


def test_mmap_decision_real_target():
    import importlib.util

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "qc_mmap_dec3", os.path.join(root, "tools", "mmap_data_decision.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    events = [
        {"event": "success", "target": "C:/Users/me/notes.txt"},
        {"event": "fallback", "target": "C:/Users/me/notes.txt"},
    ]
    stats = mod.summarize(events)
    assert stats["real"]["total"] == 2
    assert stats["real"]["eligible"] == 2
