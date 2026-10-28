# -*- coding: utf-8 -*-
"""插件分析/性能基准/UI 自适应接线测试"""
import json
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_analyze_plugins_runs():
    out = subprocess.run([sys.executable,
                          os.path.join(ROOT, "tools", "analyze_plugins.py")],
                         cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=180)
    assert out.returncode == 0, out.stderr
    data = json.load(open(os.path.join(ROOT, "data", "plugin_analysis.json"),
                          encoding="utf-8"))
    assert len(data) >= 10
    names = {r["name"] for r in data}
    assert "ai_assistant" in names and "spell_check" in names


def test_bench_plugins_runs_with_warmup():
    out = subprocess.run([sys.executable,
                          os.path.join(ROOT, "tools", "bench_plugins.py")],
                         cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=300)
    assert out.returncode == 0, out.stderr
    data = json.load(open(os.path.join(ROOT, "data", "plugin_bench.json"),
                          encoding="utf-8"))
    assert data and all("import_ms" in r for r in data)
    assert all(r.get("warmup") for r in data)


def test_startup_theme_adapts_plugin_widgets():
    src = open(os.path.join(ROOT, "ui", "mixins",
                            "capability_wiring_mixin.py"),
               encoding="utf-8").read()
    assert "adapt_widget_styles" in src
    report = os.path.join(ROOT, "docs", "plugin_analysis_v2.13.md")
    assert os.path.exists(report)

def test_requests_lazy_and_refresh_theme():
    import os
    src = open(os.path.join(ROOT, "plugins", "ai_assistant", "__init__.py"),
               encoding="utf-8").read()
    lines = src.split("\n")
    for i, line in enumerate(lines):
        if line.strip() == "import requests":
            assert line.startswith("    "), "requests 必须是函数内惰性导入"
    for name in ("wordcount", "todo_panel", "logtail",
                 "markdown_preview"):
        s = open(os.path.join(ROOT, "plugins", name, "__init__.py"),
                 encoding="utf-8").read()
        assert "def refresh_theme(self, theme)" in s, name
        assert "_base_qss" in s, name
