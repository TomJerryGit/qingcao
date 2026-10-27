# -*- coding: utf-8 -*-
"""稳定性工具：分片划分逻辑"""
import importlib.util
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    path = os.path.join(ROOT, "tools", "run_tests_sharded.py")
    spec = importlib.util.spec_from_file_location("qc_sharded", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_make_shards_partitions_all_files(tmp_path):
    m = _load()
    files = ["a", "b", "c", "d", "e"]
    shards = m.make_shards(files, 2)
    assert len(shards) == 2
    flat = [f for s in shards for f in s]
    assert sorted(flat) == sorted(files)
    assert set(shards[0]).isdisjoint(shards[1])


def test_collect_test_files():
    m = _load()
    files = m.collect_test_files()
    assert files
    assert all(os.path.basename(f).startswith("test_") for f in files)


def test_cli_help():
    path = os.path.join(ROOT, "tools", "run_tests_sharded.py")
    out = subprocess.run([sys.executable, path, "--help"], cwd=ROOT,
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=60)
    assert out.returncode == 0
    assert "--localize" in out.stdout