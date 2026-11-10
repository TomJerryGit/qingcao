# -*- coding: utf-8 -*-
"""v2.23 P1-1 批次 3：日韩 key 驱动长尾"""

import json
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_ja_ko_batch3_counts_and_coverage():
    corpus = json.load(
        open(os.path.join(ROOT, "locale", "zh_CN", "translatable.json"), encoding="utf-8")
    )
    for lang in ("ja_JP", "ko_KR"):
        d = json.load(open(os.path.join(ROOT, "locale", lang, "strings.json"), encoding="utf-8"))
        assert len(d) >= 180, (lang, len(d))
        hit = sum(1 for s in corpus if s in d)
        ratio = hit / len(corpus) * 100
        assert ratio >= 15.0, (lang, ratio)


def test_ci_gate_current():
    yml = open(os.path.join(ROOT, ".github", "workflows", "test.yml"), encoding="utf-8").read()
    assert "--min-corpus 50 --lang ja_JP" in yml
    assert "--min-corpus 50 --lang ko_KR" in yml
