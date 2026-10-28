# -*- coding: utf-8 -*-
"""v2.13.0 候选：配置同步反馈 / 上限可配置 / 高对比度工具"""
import importlib.util
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(rel, name):
    path = os.path.join(ROOT, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeSandbox:
    def __init__(self):
        self.applied = []

    def config_schema(self):
        return {"enabled": {"type": "bool", "default": True}}

    def config_apply(self, values):
        self.applied.append(values)
        return True

    def diagnostics(self, text):
        return []

    def status_text(self):
        return "拼写: 0 条"

    def menu_items(self):
        return []


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def test_max_instances_configurable(monkeypatch):
    main = _load("main.py", "qc_main_v213")
    monkeypatch.setenv("QINGCAO_MAX_INSTANCES", "5")
    assert main.get_max_new_window_instances() == 5
    monkeypatch.setenv("QINGCAO_MAX_INSTANCES", "99")
    assert main.get_max_new_window_instances() == 10
    monkeypatch.setenv("QINGCAO_MAX_INSTANCES", "0")
    assert main.get_max_new_window_instances() == 1
    monkeypatch.delenv("QINGCAO_MAX_INSTANCES")
    val = main.get_max_new_window_instances()
    assert 1 <= val <= 10


def test_config_sync_feedback(qapp):
    from ui.main_window import MainWindow
    win = MainWindow()
    fake = _FakeSandbox()
    try:
        win._sandboxed_plugins = {"spell": fake}
        win._on_remote_config_changed("spell")
        assert fake.applied
        assert win._last_synced_config[0] == "spell"
    finally:
        _close(win)


def test_high_contrast_tool_status():
    path = os.path.join(ROOT, "tools", "simulate_high_contrast.py")
    out = subprocess.run([sys.executable, path, "--status"], cwd=ROOT,
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=60)
    assert out.returncode == 0
    import json
    data = json.loads(out.stdout.strip().splitlines()[-1])
    assert "high_contrast" in data


def test_high_contrast_requires_confirm():
    path = os.path.join(ROOT, "tools", "simulate_high_contrast.py")
    out = subprocess.run([sys.executable, path, "--on"], cwd=ROOT,
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=60)
    assert out.returncode == 2