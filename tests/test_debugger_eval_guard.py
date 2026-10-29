# -*- coding: utf-8 -*-
"""v2.15：调试器受限表达式求值安全校验"""
import importlib.util
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    path = os.path.join(ROOT, "plugins", "python_debugger", "driver.py")
    spec = importlib.util.spec_from_file_location("qc_dbg_driver", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_normal_expression():
    m = _load()
    assert m._safe_eval("x + 1", {}, {"x": 41}) == 42
    assert m._safe_eval("'a' * 2", {}, {}) == "aa"


def test_blocks_dunder_and_dangerous():
    m = _load()
    for expr in ("__import__('os')", "open('/tmp/x')", "(1).__class__",
                 "eval('1')", "exec('x=1')"):
        out = m._safe_eval(expr, {}, {})
        assert isinstance(out, str) and out.startswith("<blocked"), (expr, out)


def test_syntax_error_text():
    m = _load()
    assert m._safe_eval("1 +", {}, {}).startswith("<syntax error")