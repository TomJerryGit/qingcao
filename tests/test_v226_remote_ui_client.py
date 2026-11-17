# -*- coding: utf-8 -*-
"""v2.26 阶段 C：子进程远程 UI 客户端"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _API:
    def __init__(self):
        self.pushed = []
        self.events = []

    def update_remote_controls(self, pid, controls):
        self.pushed.append((pid, controls))
        return True

    def poll_remote_ui_events(self):
        out = self.events
        self.events = []
        return out


def test_client_push_update_and_poll():
    from core.remote_ui_client import RemoteUIClient

    api = _API()
    c = RemoteUIClient(api, 7)
    c.add("out", "text_view", value="hello")
    c.add("send", "button", "发送")
    assert api.pushed[-1][0] == 7
    assert [x["id"] for x in api.pushed[-1][1]["controls"]] == ["out", "send"]
    seen = []
    c.on("send", lambda event, value: seen.append((event, value)))
    api.events = [
        {"panel_id": 7, "id": "send", "event": "click", "value": ""},
        {"panel_id": 8, "id": "send", "event": "click", "value": ""},
    ]
    assert c.poll() == 1
    assert seen == [("click", "")]
    assert c.update("out", value="next")
    assert api.pushed[-1][1]["controls"][0]["value"] == "next"


def test_client_unknown_update():
    from core.remote_ui_client import RemoteUIClient

    c = RemoteUIClient(_API(), 1)
    assert c.update("missing", text="x") is False
