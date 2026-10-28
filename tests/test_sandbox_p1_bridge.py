# -*- coding: utf-8 -*-
"""v2.12.0 P1：沙箱 spell 菜单/状态/配置广播"""
import os
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _FakeSandbox:
    def __init__(self):
        self.applied = []
        self.diag_calls = 0

    def config_schema(self):
        return {"enabled": {"type": "bool", "default": True}}

    def config_apply(self, values):
        self.applied.append(values)
        return True

    def diagnostics(self, text):
        self.diag_calls += 1
        return []

    def status_text(self):
        return "拼写: 0 条"

    def menu_items(self):
        return [{"id": "ignore_flagged", "label": "忽略本文件可疑词",
                 "path": "工具/拼写检查"}]

    def invoke_menu(self, mid):
        return mid == "ignore_flagged"


def _close(win):
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()


def test_spell_check_sandbox_protocol_static():
    import json
    manifest = json.load(open(os.path.join(
        ROOT, "plugins", "spell_check", "plugin.json"), encoding="utf-8"))
    assert manifest.get("sandbox") is True
    src = open(os.path.join(ROOT, "plugins", "spell_check", "__init__.py"),
               encoding="utf-8").read()
    assert "def menu_items(self)" in src
    assert "def invoke_menu(self, menu_id)" in src
    assert "def status_text(self)" in src


def test_config_changed_roundtrip(qapp):
    import time

    from infrastructure.instance_broadcast import InstanceBroadcaster
    name = "qingcao-test-%d-cc" % os.getpid()
    hub = InstanceBroadcaster(server_name=name)
    client = InstanceBroadcaster(server_name=name)
    got = []
    try:
        assert hub.start() is True
        assert client.start(force_client=True) is False
        client.config_changed.connect(lambda n: got.append(n))
        for _ in range(40):
            qapp.processEvents()
            time.sleep(0.02)
        hub.announce_config_changed("spell_check")
        for _ in range(80):
            qapp.processEvents()
            time.sleep(0.02)
            if got:
                break
        assert got == ["spell_check"]
    finally:
        client.stop()
        hub.stop()


def test_remote_config_handler(qapp, tmp_path):
    from ui.main_window import MainWindow
    win = MainWindow()
    fake = _FakeSandbox()
    try:
        f = tmp_path / "p1.txt"
        f.write_text("hello\n", encoding="utf-8")
        win.tabs.open_file(str(f))
        win._sandboxed_plugins = {"spell": fake}
        win._on_remote_config_changed("spell")
        assert fake.applied
        assert fake.diag_calls >= 1
    finally:
        _close(win)


def test_status_and_config_wired_static():
    src = open(os.path.join(ROOT, "ui", "main_window.py"),
               encoding="utf-8").read()
    assert "_refresh_sandbox_status" in src
    assert "_on_remote_config_changed" in src
    assert "notify_config_changed" in src