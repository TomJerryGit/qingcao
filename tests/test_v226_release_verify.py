# -*- coding: utf-8 -*-
"""Sprint 1：发布后核验"""

ROOT = "."


def test_evaluate_assets():
    from tools.release_verify import evaluate, expected

    v = "9.9.9"
    names = set(expected(v).values())
    assert evaluate(names, v) == []
    names.discard(expected(v)["installer"])
    assert expected(v)["installer"] in evaluate(names, v)
