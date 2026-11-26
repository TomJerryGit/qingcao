# -*- coding: utf-8 -*-
"""插件 Python 代码隔离子进程执行"""


def test_run_python_code_isolated():
    from core.python_exec import run_python_code

    out = run_python_code("print(1 + 2)")
    assert "3" in out
    out = run_python_code("raise SystemExit(7)")
    assert "错误" in out or "7" in out
