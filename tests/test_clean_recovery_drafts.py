# -*- coding: utf-8 -*-
"""崩溃草稿清理工具：预览模式可用"""
import importlib.util
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    path = os.path.join(ROOT, "tools", "clean_recovery_drafts.py")
    spec = importlib.util.spec_from_file_location("qc_clean", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_collect_targets_returns_list():
    m = _load()
    items = m.collect_targets()
    assert isinstance(items, list)
    for rel, path in items:
        assert rel in m.TARGETS


def test_preview_mode_exit_zero():
    path = os.path.join(ROOT, "tools", "clean_recovery_drafts.py")
    out = subprocess.run([sys.executable, path], cwd=ROOT,
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=60)
    assert out.returncode == 0
    assert ("没有需要清理" in out.stdout) or ("仅预览" in out.stdout)