# -*- coding: utf-8 -*-
"""v2.20 i18n QA：术语一致性"""

import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_qa_no_violations():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "qc_i18n_qa", os.path.join(ROOT, "tools", "i18n_qa.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    en = json.load(open(os.path.join(ROOT, "locale", "en_US", "strings.json"), encoding="utf-8"))
    assert mod.check(en) == []
    assert os.path.isfile(os.path.join(ROOT, "docs", "i18n_qa_report.md"))
