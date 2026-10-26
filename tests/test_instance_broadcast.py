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