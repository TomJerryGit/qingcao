# -*- coding: utf-8 -*-
"""v2.22 P2：体验冒烟工具与人工清单"""

import os


def _load():
    import importlib.util

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "qc_smoke", os.path.join(root, "tools", "smoke_check.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, root


def test_smoke_i18n_and_market():
    mod, _root = _load()
    mod.results.clear()
    mod.smoke_i18n()
    mod.smoke_market(offline=True)
    assert mod.results
    assert all(ok for _, ok, _ in mod.results), mod.results


def test_smoke_render():
    mod, _root = _load()
    mod.results.clear()
    mod.record("demo", True, "ok")
    text = mod.render()
    assert "demo" in text and "1/1 通过" in text


def test_smoke_docs_and_feedback_category():
    mod, root = _load()
    assert os.path.isfile(os.path.join(root, "docs", "smoke_checklist_v2.22.md"))
    assert os.path.isfile(os.path.join(root, "docs", "smoke_report_v2.22.md"))
    src = open(os.path.join(root, "ui", "feedback_dialog.py"), encoding="utf-8").read()
    assert "体验反馈" in src
