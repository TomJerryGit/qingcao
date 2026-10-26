# -*- coding: utf-8 -*-
"""P0：多实例保存广播（hub/client 中继）"""
import os
import time


def test_hub_client_broadcast(qapp):
    from infrastructure.instance_broadcast import InstanceBroadcaster
    name = "qingcao-test-%d-bc" % os.getpid()
    hub = InstanceBroadcaster(server_name=name)
    client = InstanceBroadcaster(server_name=name)
    received = []
    try:
        assert hub.start() is True
        assert client.start(force_client=True) is False
        client.file_saved.connect(
            lambda p, m, pid: received.append((p, m, pid)))
        for _ in range(40):
            qapp.processEvents()
            time.sleep(0.02)
        hub.announce("/tmp/instance_test.txt", 123.0)
        for _ in range(80):
            qapp.processEvents()
            time.sleep(0.02)
            if received:
                break
        assert received, "client 未收到广播"
        assert received[0][0] == "/tmp/instance_test.txt"
        assert abs(received[0][1] - 123.0) < 1e-6
    finally:
        client.stop()
        hub.stop()


def test_notify_file_saved_safe_without_start():
    from infrastructure.instance_broadcast import notify_file_saved
    notify_file_saved("")
    notify_file_saved("/tmp/nonexistent_qc_file.txt")


def test_hook_wired_in_editor():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "core", "editor.py"),
               encoding="utf-8").read()
    assert "notify_file_saved" in src


def test_protocol_version_payload():
    from infrastructure.instance_broadcast import PROTOCOL_VERSION, make_payload
    obj = make_payload("file_saved", "/tmp/x.txt", 1.5, 7)
    assert PROTOCOL_VERSION == 1
    assert obj["v"] == 1
    assert obj["type"] == "file_saved"
    assert obj["path"] == "/tmp/x.txt"
    assert obj["mtime"] == 1.5 and obj["pid"] == 7


def test_open_close_events(qapp):
    import os

    from infrastructure.instance_broadcast import InstanceBroadcaster
    name = "qingcao-test-%d-oc" % os.getpid()
    hub = InstanceBroadcaster(server_name=name)
    client = InstanceBroadcaster(server_name=name)
    opened, closed = [], []
    try:
        assert hub.start() is True
        assert client.start(force_client=True) is False
        client.file_opened.connect(lambda p, m, pid: opened.append(p))
        client.file_closed.connect(lambda p, m, pid: closed.append(p))
        for _ in range(50):
            qapp.processEvents()
            time.sleep(0.02)
        hub.announce_event("file_opened", "/tmp/o.txt")
        for _ in range(100):
            qapp.processEvents()
            time.sleep(0.02)
            if opened:
                break
        assert opened and opened[0] == "/tmp/o.txt"
        hub.announce_event("file_closed", "/tmp/o.txt")
        for _ in range(100):
            qapp.processEvents()
            time.sleep(0.02)
            if closed:
                break
        assert closed and closed[0] == "/tmp/o.txt"
    finally:
        client.stop()
        hub.stop()


def test_notify_file_event_safe():
    from infrastructure.instance_broadcast import notify_file_event
    notify_file_event("file_opened", "")
    notify_file_event("file_closed", "/tmp/nonexistent_qc.txt")


def test_tab_hooks_wired():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "ui", "main_window.py"),
               encoding="utf-8").read()
    assert "notify_file_event" in src
    assert "_on_remote_file_closed" in src
    assert "_on_local_tab_opened" in src
    assert "_on_local_tab_closed" in src
