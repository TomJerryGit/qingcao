# -*- coding: utf-8 -*-
"""v2.26 P2：AI 流式输出 + 选区优先上下文"""

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class _FakeClient:
    provider = "fake"
    base_url = ""

    def __init__(self):
        self.chunks = []

    def chat_stream(self, prompt="", system="", callback=None, **kwargs):
        for part in ("Hello", " world"):
            self.chunks.append(part)
            if callback:
                callback(part)
        return "".join(self.chunks)


class _FakeSC:
    def __init__(self, selected, full):
        self._sel = selected
        self._full = full

    def selectedText(self):
        return self._sel

    def text(self):
        return self._full


class _FakeDoc:
    filepath = ""


class _FakeEditor:
    def __init__(self, selected="", full=""):
        self.sc = _FakeSC(selected, full)
        self.document = _FakeDoc()


class _FakeAPI:
    def __init__(self, editor):
        self._editor = editor

    def current_editor(self):
        return self._editor

    def log(self, *a, **k):
        pass


def test_worker_streams_chunks():
    from plugins.ai_assistant.ai_worker import AIWorker

    worker = AIWorker(_FakeClient(), "hi")
    chunks = []
    done = []
    worker.chunk_received.connect(chunks.append)
    worker.finished_ok.connect(done.append)
    worker.run()  # 同步执行，避免线程时序
    assert chunks == ["Hello", " world"]
    assert done == ["Hello world"]


def test_worker_cancel_after_stream():
    from plugins.ai_assistant.ai_worker import AIWorker

    worker = AIWorker(_FakeClient(), "hi")
    errors = []
    worker.finished_err.connect(errors.append)
    worker._cancelled = True
    worker.run()
    assert errors and "取消" in errors[0]


def test_context_prefers_selection():
    from plugins.ai_assistant import Plugin

    plugin = Plugin()
    plugin.api = _FakeAPI(_FakeEditor(selected="selected-code", full="full-text"))
    code, _lang, _fp = plugin._get_context()
    assert code == "selected-code"


def test_context_falls_back_to_full_text():
    from plugins.ai_assistant import Plugin

    plugin = Plugin()
    plugin.api = _FakeAPI(_FakeEditor(selected="", full="full-text"))
    code, _lang, _fp = plugin._get_context()
    assert code == "full-text"
