# -*- coding: utf-8 -*-
"""v2.20 i18n 英文正式版：术语表 / 100% 门禁 / 词典质量"""

import io
import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_glossary_and_readme():
    assert os.path.isfile(os.path.join(ROOT, "docs", "i18n_glossary.md"))
    readme = io.open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    assert "English UI" in readme


def test_ci_gate_wired():
    yml = io.open(os.path.join(ROOT, ".github", "workflows", "test.yml"), encoding="utf-8").read()
    assert "i18n_coverage.py --check" in yml


def test_dict_no_chinese_residue():
    en = json.load(io.open(os.path.join(ROOT, "locale", "en_US", "strings.json"), encoding="utf-8"))
    bad = []
    for k, v in en.items():
        if not isinstance(v, str):
            continue
        if any("\u4e00" <= c <= "\u9fff" for c in v) and v != "简体中文":
            bad.append((k, v))
    assert not bad, bad[:10]


def test_coverage_check_passes(monkeypatch, tmp_path):
    monkeypatch.setenv("QINGCAO_LANG", "zh_CN")
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "qc_cov_check", os.path.join(ROOT, "tools", "i18n_coverage.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = tmp_path / "cov.md"
    old = sys.argv
    sys.argv = ["i18n_coverage.py", "--check", "--min-corpus", "100", "--out", str(out)]
    try:
        assert mod.main() == 0
    finally:
        sys.argv = old
