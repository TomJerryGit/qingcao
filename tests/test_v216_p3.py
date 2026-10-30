# -*- coding: utf-8 -*-
"""v2.16 P3：多主题 E2E 截图基线 + 插件来源过滤"""
import os
import subprocess
import sys

from PyQt5.QtCore import QSettings  # noqa: F401


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_theme_e2e_screenshots_generated():
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    out = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools",
                                      "theme_e2e_screenshots.py")],
        cwd=ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300)
    assert out.returncode == 0, out.stdout + out.stderr
    baseline = os.path.join(ROOT, "docs", "theme_baseline")
    files = [f for f in os.listdir(baseline) if f.endswith(".png")]
    assert len(files) >= 8, files
    for theme in ("dark_night", "light_clean", "eye_protect",
                  "high_contrast"):
        assert "window_%s.png" % theme in files
        assert "panel_%s.png" % theme in files


def test_problems_panel_plugin_source_filter(qapp):
    from core.problems import Problem, get_problem_manager
    from ui.main_window import MainWindow
    from ui.problems_panel import ProblemsPanel
    manager = get_problem_manager()
    manager.clear()
    fp = os.path.join(ROOT, "tests", "fixture_p3.py")
    manager.set_file_problems(fp, [
        Problem(filepath=fp, line=0, col=0, severity="info",
                message="a-msg", source="sandbox:alpha"),
        Problem(filepath=fp, line=1, col=0, severity="info",
                message="b-msg", source="sandbox:beta"),
    ])
    win = MainWindow()
    panel = ProblemsPanel(main_window=win)
    try:
        panel.refresh()
        datas = [panel.filter_combo.itemData(i)
                 for i in range(panel.filter_combo.count())]
        assert "plugin:sandbox:alpha" in datas
        idx = datas.index("plugin:sandbox:alpha")
        panel.filter_combo.setCurrentIndex(idx)
        panel.refresh()
        top = panel.tree.topLevelItem(0)
        assert top is not None
        assert top.childCount() == 1
        assert top.child(0).text(4) == "sandbox:alpha"
    finally:
        manager.clear()
        panel.close()
        try:
            sess = getattr(win, "session", None)
            if sess is not None and hasattr(sess, "save"):
                sess.save = lambda *a, **k: None
        except Exception:
            pass
        win.close()


def test_roadmap_and_docs_present():
    assert os.path.exists(os.path.join(
        ROOT, "docs", "manual_validation_v2.16_multimonitor.md"))
    assert os.path.exists(os.path.join(ROOT, "docs", "roadmap_v2.16.0.md"))