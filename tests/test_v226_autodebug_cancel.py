# -*- coding: utf-8 -*-
"""Sprint 3：自动调试取消/历史/回滚点"""

import os
import sys
import threading


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _bug(tmp_path, code="print(undefined_name)\n"):
    f = tmp_path / "bug.py"
    f.write_text(code, encoding="utf-8")
    return f


def test_cancel_before_start_restores(tmp_path):
    from core.ai_autodebug import auto_debug

    f = _bug(tmp_path)
    ev = threading.Event()
    ev.set()
    r = auto_debug(str(f), lambda p: "", cancel_event=ev)
    assert r["cancelled"] and not r["ok"]
    assert "undefined_name" in f.read_text(encoding="utf-8")


def test_history_and_backup(tmp_path):
    from core.ai_autodebug import auto_debug

    f = _bug(tmp_path)

    def ai(prompt):
        return "print('fixed')\n"

    r = auto_debug(str(f), ai, max_rounds=1, backup_dir=str(tmp_path / "baks"))
    assert r["ok"] and r["history"]
    assert any(
        "print('fixed')" in x.read_text(encoding="utf-8")
        for x in (tmp_path / "baks").glob("round_*.py.bak")
    )


def test_cancel_during_ai_call(tmp_path):
    from core.ai_autodebug import auto_debug

    f = _bug(tmp_path)
    ev = threading.Event()

    def ai(prompt):
        ev.set()
        return "print('fixed')\n"

    r = auto_debug(str(f), ai, cancel_event=ev)
    assert r["cancelled"] and not r["ok"]
    assert "undefined_name" in f.read_text(encoding="utf-8")
