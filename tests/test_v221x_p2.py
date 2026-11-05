# -*- coding: utf-8 -*-
"""v2.21.x P2：终端多标签/ANSI、日韩试点、mmap 数据决策、评分草案"""

import os
import time


def _pump(qapp, panel, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if panel._proc is None:
            return True
        time.sleep(0.02)
    return False


def test_ansi_to_html():
    from ui.terminal_panel import ansi_to_html

    h = ansi_to_html("\x1b[31mred\x1b[0m <plain>")
    assert "#e06c75" in h and "red" in h
    assert "&lt;plain&gt;" in h
    assert ansi_to_html("no codes") == "no codes"


def test_terminal_multi_tab(qapp):
    from ui.terminal_panel import TerminalPanel

    panel = TerminalPanel(None)
    try:
        assert panel.tabs.count() == 1
        panel.add_tab()
        assert panel.tabs.count() == 2
        panel.input.setText("echo qc-tab2-ok")
        panel.run_command()
        assert _pump(qapp, panel)
        assert "qc-tab2-ok" in panel.output.toPlainText()
        panel.close_tab(1)
        assert panel.tabs.count() == 1
    finally:
        panel.close()


def test_ja_ko_pilot(monkeypatch):
    import json

    from core.i18n_json import AVAILABLE, clear_cache, tr

    assert AVAILABLE.get("ja_JP") == "日本語"
    assert AVAILABLE.get("ko_KR") == "한국어"
    for lang in ("ja_JP", "ko_KR"):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "locale",
            lang,
            "strings.json",
        )
        assert os.path.isfile(path)
        assert len(json.load(open(path, encoding="utf-8"))) > 0
    monkeypatch.setenv("QINGCAO_LANG", "ja_JP")
    clear_cache()
    assert tr("文件") == "ファイル"
    monkeypatch.setenv("QINGCAO_LANG", "ko_KR")
    clear_cache()
    assert tr("保存") == "저장"
    assert tr("__missing__") == "__missing__"


def test_mmap_data_decision():
    import importlib.util

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "qc_mmap_dec", os.path.join(root, "tools", "mmap_data_decision.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    events = [
        {"event": "success", "size": 100},
        {"event": "fallback", "size": 100, "error": "patch fail"},
        {"event": "recovery", "target": "C:\\Temp\\pytest-1\\a.txt"},
    ]
    stats = mod.summarize(events)
    assert stats["real"]["total"] == 0
    assert stats["unknown"]["total"] == 2
    assert "数据不足" in mod.decide(stats)
    assert "未知" in mod.render(stats, mod.decide(stats))
    assert os.path.isfile(os.path.join(root, "docs", "mmap_data_decision.md"))


def test_rating_draft_doc():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.isfile(os.path.join(root, "docs", "plugin_rating_server_draft.md"))
