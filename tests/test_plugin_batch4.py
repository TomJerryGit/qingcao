# -*- coding: utf-8 -*-
"""Batch4：基准可靠性 / ai 主题刷新 / 市场元数据"""
import json
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_bench_realistic_and_ai_fast():
    out = subprocess.run([sys.executable,
                          os.path.join(ROOT, "tools", "bench_plugins.py")],
                         cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=300)
    assert out.returncode == 0, out.stderr
    data = json.load(open(os.path.join(ROOT, "data", "plugin_bench.json"),
                          encoding="utf-8"))
    ai = next(r for r in data if r["plugin"] == "ai_assistant")
    assert ai["import_ms"] < 150, ai
    assert all(r.get("warmup") for r in data)


def test_market_metadata_complete():
    out = subprocess.run([sys.executable,
                          os.path.join(ROOT, "tools",
                                       "check_plugin_market.py"),
                          "--strict"],
                         cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr


def test_ai_refresh_theme_present():
    src = open(os.path.join(ROOT, "plugins", "ai_assistant",
                            "__init__.py"), encoding="utf-8").read()
    assert "def refresh_theme(self, theme)" in src
    assert "_base_qss" in src