# -*- coding: utf-8 -*-
"""v2.22 P1 稳定性：更新检查线程/空闲延迟/网络超时审计"""

import os


def test_updater_timeout_and_no_update(monkeypatch):
    import requests

    from core.updater import UpdateChecker

    called = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"tag_name": "v0.0.1", "assets": []}

    def fake_get(url, **kw):
        called["url"] = url
        called["timeout"] = kw.get("timeout")
        return _Resp()

    monkeypatch.setattr(requests, "get", fake_get)
    checker = UpdateChecker("9.9.9")
    got = []
    checker.no_update.connect(lambda v: got.append(v))
    checker._check()
    assert called["timeout"] == (3.05, 10)
    assert got == ["9.9.9"]


def test_updater_cancel(monkeypatch):
    import requests

    from core.updater import UpdateChecker

    def boom(*a, **k):
        raise AssertionError("取消后不应发起网络请求")

    monkeypatch.setattr(requests, "get", boom)
    checker = UpdateChecker("9.9.9")
    checker.cancel()
    checker._check()  # 不应抛异常


def test_updater_check_when_idle_modal_guard(qapp, monkeypatch):
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
    scheduled.pop(0)()  # 第一次：有模态框 → 重试
    assert not started
    assert scheduled, "应安排重试"
    modal[0] = False
    scheduled.pop(0)()  # 第二次：空闲 → 启动
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
