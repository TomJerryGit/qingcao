# -*- coding: utf-8 -*-
"""v2.15.x P2：广播版本协商 + 性能门禁智能降级"""
import importlib.util
import json
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_broadcast_peer_version_negotiation(qapp):
    from infrastructure.instance_broadcast import PROTOCOL_VERSION, InstanceBroadcaster
    b = InstanceBroadcaster()
    seen = {}
    b.peer_versions_changed.connect(lambda d: seen.update(d))
    try:
        b._dispatch(json.dumps({"v": 2, "type": "hello", "pid": 999}))
        assert seen.get(999) == 2
        b._dispatch(json.dumps({"v": PROTOCOL_VERSION, "type": "hello",
                                "pid": 1001}))
        assert seen.get(1001) == PROTOCOL_VERSION
        b._dispatch(json.dumps({"v": 3, "type": "hello_ack",
                                "pid": 111, "peer_pid": 222}))
        assert b._peer_versions.get(222) == 3
        # 未知类型/未来版本不崩溃
        b._dispatch(json.dumps({"v": 9, "type": "future_event", "pid": 1}))
    finally:
        b.stop()


def test_main_window_compat_warning(qapp):
    from ui.main_window import MainWindow
    win = MainWindow()
    try:
        win._on_peer_versions_changed({999: 2})
        assert getattr(win, "_compat_warned", False) is True
        win._on_peer_versions_changed({999: 2})  # 只提示一次，不异常
    finally:
        try:
            sess = getattr(win, "session", None)
            if sess is not None and hasattr(sess, "save"):
                sess.save = lambda *a, **k: None
        except Exception:
            pass
        win.close()


def _load_bench():
    path = os.path.join(ROOT, "tools", "bench_optimization.py")
    spec = importlib.util.spec_from_file_location("qc_bench_auto", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_system_load_factor_range():
    mod = _load_bench()
    f = mod.system_load_factor()
    assert isinstance(f, float)
    assert 1.0 <= f <= 4.0


def test_auto_flag_exists():
    out = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools",
                                      "bench_optimization.py"), "--help"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120)
    assert out.returncode == 0
    assert "--auto" in out.stdout


def test_ci_performance_gate_uses_auto():
    yml = open(os.path.join(ROOT, ".github", "workflows", "test.yml"),
               encoding="utf-8").read()
    assert "bench_optimization.py --check --auto" in yml