# -*- coding: utf-8 -*-
"""v2.26 阶段 A：AI 安全运行器"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_run_ok_and_error(tmp_path):
    from core.ai_runner import run_python_file

    ok = tmp_path / "ok.py"
    ok.write_text("print('hello')", encoding="utf-8")
    r = run_python_file(str(ok))
    assert r["ok"] and r["exit_code"] == 0 and "hello" in r["stdout"]

    bad = tmp_path / "bad.py"
    bad.write_text("raise SystemExit(2)", encoding="utf-8")
    r = run_python_file(str(bad))
    assert not r["ok"] and r["exit_code"] == 2


def test_run_timeout(tmp_path):
    from core.ai_runner import run_python_file

    slow = tmp_path / "slow.py"
    slow.write_text("import time; time.sleep(30)", encoding="utf-8")
    r = run_python_file(str(slow), timeout=1)
    assert r["timed_out"] and not r["ok"]


def test_rejects_non_py(tmp_path):
    from core.ai_runner import run_python_file

    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    assert not run_python_file(str(f))["ok"]
