# -*- coding: utf-8 -*-
"""v2.26 Sprint1：运行器网络/内存/CPU 限制"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _py(tmp_path, name, code):
    f = tmp_path / name
    f.write_text(code, encoding="utf-8")
    return str(f)


def test_network_blocked_by_default(tmp_path):
    from core.ai_runner import run_python_file

    f = _py(tmp_path, "net.py", "import socket\nsocket.socket()\nprint('ok')")
    r = run_python_file(f)
    assert not r["ok"]
    assert "network disabled" in (r["stderr"] or "")


def test_network_allowed(tmp_path):
    from core.ai_runner import run_python_file

    f = _py(tmp_path, "net2.py", "import socket\nsocket.socket()\nprint('ok')")
    r = run_python_file(f, allow_network=True)
    assert r["ok"] and "ok" in r["stdout"]


def test_memory_limit(tmp_path):
    import pytest

    pytest.importorskip("psutil")
    from core.ai_runner import run_python_file

    f = _py(tmp_path, "mem.py", "x = bytearray(200 * 1024 * 1024)\nimport time\ntime.sleep(2)\n")
    r = run_python_file(f, max_memory_mb=32, timeout=10)
    assert r["memory_exceeded"] and not r["ok"]


def test_cpu_timeout(tmp_path):
    from core.ai_runner import run_python_file

    f = _py(tmp_path, "slow.py", "import time\ntime.sleep(5)\n")
    r = run_python_file(f, timeout=1)
    assert r["timed_out"] and not r["ok"]
