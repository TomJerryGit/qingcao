# -*- coding: utf-8 -*-
"""v2.26 阶段 C：远程控件协议"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_tree_serialize_and_dispatch():
    from core.remote_ui import RemoteControlTree

    tree = RemoteControlTree()
    tree.add("title", "label", "AI 输出")
    tree.add("answer", "text_view", value="hello")
    tree.add("send", "button", "发送")
    data = tree.to_dict()
    assert [c["id"] for c in data["controls"]] == ["title", "answer", "send"]
    event = tree.dispatch("answer", "text_changed", "next")
    assert event["value"] == "next"
    assert tree.to_dict()["controls"][1]["value"] == "next"


def test_rejects_invalid_controls():
    from core.remote_ui import RemoteControlTree

    tree = RemoteControlTree()
    for cid, kind in (("", "label"), ("x", "script")):
        try:
            tree.add(cid, kind)
        except ValueError:
            pass
        else:
            raise AssertionError("应拒绝 %r/%r" % (cid, kind))
    assert tree.dispatch("missing", "click") is None
    assert tree.dispatch("x", "click") is None


def test_event_rules():
    from core.remote_ui import RemoteControlTree

    tree = RemoteControlTree()
    tree.add("btn", "button", "ok")
    assert tree.dispatch("btn", "click")["event"] == "click"
    assert tree.dispatch("btn", "text_changed", "x") is None
