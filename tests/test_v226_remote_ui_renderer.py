# -*- coding: utf-8 -*-
"""v2.26 阶段 C：远程控件渲染"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_renderer_builds_and_emits(qapp):
    from ui.remote_ui_renderer import RemoteUIRenderer

    r = RemoteUIRenderer()
    events = []
    r.event.connect(lambda i, e, v: events.append((i, e, v)))
    r.update_tree(
        {
            "controls": [
                {"id": "title", "kind": "label", "text": "AI 输出"},
                {"id": "send", "kind": "button", "text": "发送"},
                {"id": "input", "kind": "line_edit", "value": "hi"},
            ]
        }
    )
    assert r.widget_for("title") is not None
    r.widget_for("send").click()
    r.widget_for("input").setText("next")
    assert ("send", "click", "") in events
    assert ("input", "text_changed", "next") in events
    r.close()
