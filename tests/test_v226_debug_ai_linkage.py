# -*- coding: utf-8 -*-
"""Sprint 3：调试上下文实时联动 AI"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _API:
    def __init__(self):
        self.prompt = ""
        self.ctx = {
            "locals": {"x": 1},
            "stack": [{"name": "main"}],
            "breakpoint": {"line": 3},
            "status": "paused",
        }

    def debug_context(self):
        return dict(self.ctx)

    def ai_run(self, prompt, **k):
        self.prompt = prompt
        return {"ok": True, "text": "分析完成"}

    def show_text_dialog(self, *a, **k):
        pass

    def show_status(self, *a, **k):
        pass


def test_debug_context_uses_latest_snapshot():
    from plugins.ai_assistant import Plugin

    plugin = Plugin()
    api = _API()
    plugin.api = api
    plugin._on_debug_context_ai()
    assert '"x": 1' in api.prompt and "main" in api.prompt
    api.ctx["locals"] = {"y": 2}
    plugin._on_debug_context_ai()
    assert '"y": 2' in api.prompt
