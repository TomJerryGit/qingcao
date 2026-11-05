# -*- coding: utf-8 -*-
"""v2.22 P1：Qt 主线程异步更新检查 + 空闲延迟 + 网络审计"""

import os


def test_handle_data_no_update():
    from core.updater import UpdateChecker

    checker = UpdateChecker("9.9.9")
    got = []
    checker.no_update.connect(lambda v: got.append(v))
    checker._handle_data({"tag_name": "v0.0.1"})
    assert got == ["9.9.9"]


def test_handle_data_newer_windows_asset():
    from core.updater import UpdateChecker

    checker = UpdateChecker("1.0.0")
    got = []
    checker.check_completed.connect(lambda d: got.append(d))
    checker._handle_data(
        {
            "tag_name": "v99.9.9",
            "html_url": "https://example/html",
            "assets": [
                {
                    "name": "QingCaoEditor-v99.9.9-windows.zip",
                    "browser_download_url": "https://example/win.zip",
                }
            ],
        }
    )
    assert got and got[0]["latest_version"] == "99.9.9"
    assert got[0]["download_url"] == "https://example/win.zip"


def test_handle_data_invalid():
    from core.updater import UpdateChecker

    checker = UpdateChecker("1.0.0")
    fails = []
    checker.check_failed.connect(lambda m: fails.append(m))
    checker._handle_data({})
    assert fails == ["无效的版本信息"]


def test_check_async_qt_network_and_cancel():
    from core.updater import UpdateChecker

    class _FakeSignal:
        def connect(self, cb):
            pass

    class FakeReply:
        def __init__(self):
            self.aborted = False
            self.finished = _FakeSignal()

        def abort(self):
            self.aborted = True

        def deleteLater(self):
            pass

    class FakeManager:
        def __init__(self):
            self.called = []
            self.reply = FakeReply()

        def get(self, req):
            self.called.append(req)
            return self.reply

    checker = UpdateChecker("1.0.0")
    fake = FakeManager()
    checker._manager = fake
    checker.check_async()
    assert len(fake.called) == 1
    assert checker._reply is fake.reply
    checker.cancel()
    assert fake.reply.aborted is True
    if checker._timeout is not None:
        checker._timeout.stop()


def test_check_async_skips_when_cancelled():
    from core.updater import UpdateChecker

    class FakeManager:
        def __init__(self):
            self.called = []

        def get(self, req):
            self.called.append(req)
            return None

    checker = UpdateChecker("1.0.0")
    fake = FakeManager()
    checker._manager = fake
    checker.cancel()
    checker.check_async()
    assert fake.called == []


def test_check_when_idle_modal_guard(qapp, monkeypatch):
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication

    from core.updater import UpdateChecker

    scheduled = []
    monkeypatch.setattr(QTimer, "singleShot", staticmethod(lambda ms, cb: scheduled.append(cb)))
    modal = [True]
    monkeypatch.setattr(
        QApplication,
        "activeModalWidget",
        staticmethod(lambda self=None: object() if modal[0] else None),
    )
    checker = UpdateChecker("9.9.9")
    started = []
    monkeypatch.setattr(checker, "check_async", lambda: started.append(1))
    checker.check_when_idle(delay_ms=0)
    assert scheduled, "应安排延迟检查"
    scheduled.pop(0)()  # 有模态 → 重试
    assert not started
    assert scheduled
    modal[0] = False
    scheduled.pop(0)()  # 空闲 → 启动
    assert started == [1]


def test_network_audit_clean():
    import importlib.util

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        "qc_net_audit", os.path.join(root, "tools", "audit_network_threads.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.scan() == []
    assert os.path.isfile(os.path.join(root, "docs", "network_thread_audit.md"))


def test_crash_doc():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.isfile(os.path.join(root, "docs", "crash_root_cause_0x8001010d.md"))
