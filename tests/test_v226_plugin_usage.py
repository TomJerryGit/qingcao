# -*- coding: utf-8 -*-
"""v2.26 P2：插件使用统计（隐私安全）"""

import importlib.util
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location(
        "qc_usage", os.path.join(ROOT, "tools", "plugin_usage_report.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_usage_record_and_report(tmp_path, monkeypatch):
    from core import plugin_usage

    plugin_usage.set_path(str(tmp_path / "u.json"))
    monkeypatch.setenv("QINGCAO_PLUGIN_USAGE", "1")
    assert plugin_usage.record("demo", "activate")
    assert plugin_usage.record("demo", "activate")
    snap = plugin_usage.snapshot()
    assert snap["demo"]["activations"] == 2
    # 不记录路径/文本
    raw = open(tmp_path / "u.json", encoding="utf-8").read()
    assert "README" not in raw and "content" not in raw
    out = tmp_path / "r.md"
    _load().render(snap, str(out))
    assert "| demo | 2 |" in out.read_text(encoding="utf-8")


def test_usage_opt_out(tmp_path, monkeypatch):
    from core import plugin_usage

    plugin_usage.set_path(str(tmp_path / "u2.json"))
    monkeypatch.setenv("QINGCAO_PLUGIN_USAGE", "0")
    assert plugin_usage.record("demo", "activate") is False
    assert plugin_usage.snapshot() == {}
