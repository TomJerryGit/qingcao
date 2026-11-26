# -*- coding: utf-8 -*-
"""受限数学表达式求值"""

import pytest


def test_basic_and_exponent():
    from core.safe_expr import evaluate

    assert evaluate("1+2*3") == 7
    assert evaluate("2^3") == 8
    assert evaluate("-(4/2)") == -2


def test_rejects_code():
    from core.safe_expr import SafeExprError, evaluate

    for expr in ("__import__('os')", "open('x')", "a+b", "2**999"):
        with pytest.raises(SafeExprError):
            evaluate(expr)
