# -*- coding: utf-8 -*-
"""Sprint 3：AI 提供商契约测试（录制/回放，无网络/Key）"""

import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "ai_contract.json")


def _fixture():
    return json.load(io.open(FIXTURE, encoding="utf-8-sig"))


def _transport_for(response, captured):
    def _transport(**kwargs):
        captured.update(kwargs)
        return dict(response)

    return _transport


def test_openai_success_contract(tmp_path):
    from core.ai_client import OpenAIClient

    fx = _fixture()["openai_success"]
    captured = {}
    OpenAIClient.set_http_transport(_transport_for(fx["response"], captured))
    try:
        client = OpenAIClient(api_key="test-key", model=fx["request"]["model"])
        out = client.chat(fx["request"]["prompt"])
        assert "hello" in out
        assert captured["json_data"]["model"] == "gpt-4o"
        assert captured["url"].endswith("/chat/completions")
        assert captured["headers"]["Authorization"] == "Bearer test-key"
    finally:
        OpenAIClient.set_http_transport(None)


def test_openai_error_contract():
    from core.ai_client import AIClientError, OpenAIClient

    fx = _fixture()["openai_error"]
    captured = {}
    OpenAIClient.set_http_transport(_transport_for(fx["response"], captured))
    try:
        client = OpenAIClient(api_key="bad", model="gpt-4o")
        try:
            client.chat("hi")
        except AIClientError:
            pass
    finally:
        OpenAIClient.set_http_transport(None)


def test_claude_success_contract():
    from core.ai_client import ClaudeClient

    fx = _fixture()["claude_success"]
    captured = {}
    ClaudeClient.set_http_transport(_transport_for(fx["response"], captured))
    try:
        client = ClaudeClient(api_key="test-key", model=fx["request"]["model"])
        out = client.chat(fx["request"]["prompt"])
        assert "claude-ok" in out
        assert captured["json_data"]["model"] == "claude-3-5-sonnet-latest"
    finally:
        ClaudeClient.set_http_transport(None)
