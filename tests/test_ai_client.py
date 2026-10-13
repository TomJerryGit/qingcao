# -*- coding: utf-8 -*-
"""AI 客户端协议测试

这是 AI 模块**唯一**的自动化测试（此前 `core/ai_client.py` 在 `tests/`
下引用数为 0）。缺少测试直接导致了一个长期缺陷：`ClaudeClient` 没有
`chat_stream`，于是 Anthropic provider 静默退化为**非流式**，用户要盯着
空白对话框等到整段回复生成完毕。

本文件用**mock HTTP** 验证各家协议，不发真实网络请求：

  * OpenAI 兼容族（OpenAI / Ollama / DeepSeek / 通义 / Moonshot / 智谱）
      POST {base}/chat/completions
      行格式 ``data: {"choices":[{"delta":{"content":"..."}}]}``
      以 ``data: [DONE]`` 结束
  * Anthropic Claude
      POST {base}/messages
      头 ``x-api-key`` + ``anthropic-version``，``system`` 放在顶层
      行格式 ``event: xxx`` + ``data: {"type":"content_block_delta",
      "delta":{"type":"text_delta","text":"..."}}``

运行::

    python -m pytest tests/test_ai_client.py -v
"""
import json
import os
import sys

import pytest


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import ai_client as AI  # noqa: E402


# =========================================================
# 测试替身
# =========================================================

class FakeResponse:
    """最小化的 requests.Response 替身"""

    def __init__(self, lines=(), json_data=None, status_code=200):
        self._lines = list(lines)
        self._json = json_data if json_data is not None else {}
        self.status_code = status_code
        self.closed = False

    def iter_lines(self):
        return iter(self._lines)

    def json(self):
        return self._json

    def close(self):
        self.closed = True


class Recorder:
    """记录最后一次请求的细节

    注意：补丁必须是**普通函数**，不能用带 ``__call__`` 的实例。

    原因：把实例赋给类属性时，Python 会把它当**描述符**处理，实例方法
    语义导致 ``self`` 不被绑定 —— 第一个形参 ``client`` 会收到 ``url``
    字符串，所有参数整体错位一位。这里提供 :meth:`make` 返回一个
    闭包函数，由 fixture 负责挂载。
    """

    def __init__(self, response):
        self.response = response
        self.url = None
        self.headers = None
        self.payload = None
        self.stream = None
        self.calls = 0

    def make(self):
        """返回可安全 setattr 到类上的普通函数"""
        def _fake(self, url, headers, json_data=None,
                  stream=False, timeout=None):
            self_rec.calls += 1
            self_rec.url = url
            self_rec.headers = dict(headers or {})
            self_rec.payload = (dict(json_data)
                                if isinstance(json_data, dict) else json_data)
            self_rec.stream = stream
            return self_rec.response
        self_rec = self
        return _fake


@pytest.fixture
def patch_http(monkeypatch):
    """返回一个函数：安装 mock 并拿到 Recorder"""
    def _install(response):
        rec = Recorder(response)
        monkeypatch.setattr(AI.AIClient, '_make_request', rec.make())
        return rec
    return _install


def openai_sse(*texts):
    """构造 OpenAI 风格的 SSE 行"""
    lines = []
    for t in texts:
        lines.append(('data: ' + json.dumps(
            {"choices": [{"delta": {"content": t}}]})).encode())
    lines.append(b'data: [DONE]')
    return lines


def anthropic_sse(*texts):
    """构造 Anthropic 风格的 SSE 行"""
    lines = [
        b'event: message_start',
        b'data: {"type":"message_start","message":{"id":"msg_1"}}',
        b'',
    ]
    for t in texts:
        lines.append(b'event: content_block_delta')
        lines.append(('data: ' + json.dumps({
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": t},
        })).encode())
    lines.append(b'event: message_stop')
    lines.append(b'data: {"type":"message_stop"}')
    return lines


# =========================================================
# OpenAI 兼容族
# =========================================================

class TestOpenAIStream:
    def test_stream_emits_incremental_chunks(self, patch_http):
        """必须逐段回调，而不是最后一整段"""
        rec = patch_http(FakeResponse(lines=openai_sse("Hello", ", ", "world")))
        c = AI.OpenAIClient(api_key="k", provider="openai")
        got = []
        text = c.chat_stream("hi", callback=got.append)
        assert text == "Hello, world"
        assert got == ["Hello", ", ", "world"], "必须增量回调"
        assert rec.stream is True

    def test_stream_url_and_bearer_header(self, patch_http):
        rec = patch_http(FakeResponse(lines=openai_sse("x")))
        AI.OpenAIClient(api_key="sk-123", provider="openai").chat_stream("hi")
        assert rec.url.endswith("/chat/completions")
        assert rec.headers.get("Authorization") == "Bearer sk-123"

    def test_stream_payload_shape(self, patch_http):
        rec = patch_http(FakeResponse(lines=openai_sse("x")))
        AI.OpenAIClient(api_key="k", provider="openai").chat_stream(
            "hi", system="sys")
        p = rec.payload
        assert p.get("stream") is True
        assert p["messages"][0] == {"role": "system", "content": "sys"}
        assert p["messages"][1] == {"role": "user", "content": "hi"}

    def test_stream_stops_on_done_sentinel(self, patch_http):
        """[DONE] 之后的行必须被忽略"""
        lines = openai_sse("a") + [b'data: {"choices":[{"delta":{"content":"b"}}]}']
        rec = patch_http(FakeResponse(lines=lines))
        c = AI.OpenAIClient(api_key="k", provider="openai")
        assert c.chat_stream("hi") == "a"

    def test_stream_ignores_non_data_lines(self, patch_http):
        lines = [b'', b': keep-alive', b'event: ping'] + openai_sse("ok")
        rec = patch_http(FakeResponse(lines=lines))
        c = AI.OpenAIClient(api_key="k", provider="openai")
        assert c.chat_stream("hi") == "ok"

    def test_stream_tolerates_malformed_json(self, patch_http):
        lines = [b'data: {not json'] + openai_sse("ok")
        rec = patch_http(FakeResponse(lines=lines))
        c = AI.OpenAIClient(api_key="k", provider="openai")
        assert c.chat_stream("hi") == "ok"

    def test_empty_choices_skipped(self, patch_http):
        lines = [b'data: {"choices":[]}'] + openai_sse("ok")
        rec = patch_http(FakeResponse(lines=lines))
        c = AI.OpenAIClient(api_key="k", provider="openai")
        assert c.chat_stream("hi") == "ok"

    def test_requires_api_key_unless_ollama(self, patch_http):
        patch_http(FakeResponse(lines=openai_sse("x")))
        with pytest.raises(AI.AIAuthError):
            AI.OpenAIClient(api_key="", provider="openai").chat_stream("hi")
        # ollama / custom 允许空 key
        AI.OpenAIClient(api_key="", provider="ollama").chat_stream("hi")
        AI.OpenAIClient(api_key="", provider="custom").chat_stream("hi")


# =========================================================
# Anthropic Claude
# =========================================================

class TestClaudeStream:
    """此前 Claude 没有 chat_stream，这里锁死该回归"""

    def test_claude_has_chat_stream(self):
        """回归防线：ClaudeClient 必须能流式（原先只能非流式）"""
        c = AI.ClaudeClient(api_key="k")
        assert hasattr(c, "chat_stream")
        assert callable(c.chat_stream)

    def test_claude_stream_emits_incremental_chunks(self, patch_http):
        rec = patch_http(FakeResponse(lines=anthropic_sse("Hello", ", world")))
        c = AI.ClaudeClient(api_key="k")
        got = []
        text = c.chat_stream("hi", callback=got.append)
        assert text == "Hello, world"
        assert got == ["Hello", ", world"], "Anthropic 必须增量回调"

    def test_claude_uses_messages_endpoint(self, patch_http):
        rec = patch_http(FakeResponse(lines=anthropic_sse("x")))
        AI.ClaudeClient(api_key="k").chat_stream("hi")
        assert rec.url.endswith("/messages"), (
            "Anthropic 端点是 /messages，不是 /chat/completions")
        assert "/chat/completions" not in rec.url

    def test_claude_uses_x_api_key_and_version(self, patch_http):
        rec = patch_http(FakeResponse(lines=anthropic_sse("x")))
        AI.ClaudeClient(api_key="sk-ant-1").chat_stream("hi")
        assert rec.headers.get("x-api-key") == "sk-ant-1"
        assert rec.headers.get("anthropic-version")
        assert "Authorization" not in rec.headers, (
            "Anthropic 不用 Bearer 头")

    def test_claude_system_is_top_level(self, patch_http):
        rec = patch_http(FakeResponse(lines=anthropic_sse("x")))
        AI.ClaudeClient(api_key="k").chat_stream("hi", system="你是助手")
        p = rec.payload
        assert p.get("system") == "你是助手", "system 必须是顶层字段"
        # messages 里不应再有 system 角色
        assert all(m.get("role") != "system" for m in p["messages"])

    def test_claude_ignores_non_text_events(self, patch_http):
        """ping / message_start 等事件不应产生内容"""
        lines = [
            b'event: ping', b'data: {"type":"ping"}',
            b'event: content_block_start',
            b'data: {"type":"content_block_start","content_block":{"type":"text"}}',
        ] + anthropic_sse("real")
        rec = patch_http(FakeResponse(lines=lines))
        assert AI.ClaudeClient(api_key="k").chat_stream("hi") == "real"

    def test_claude_raises_on_error_event(self, patch_http):
        lines = [('data: ' + json.dumps({
            "type": "error",
            "error": {"type": "overloaded_error", "message": "过载"},
        })).encode()]
        patch_http(FakeResponse(lines=lines))
        with pytest.raises(AI.AIClientError) as ei:
            AI.ClaudeClient(api_key="k").chat_stream("hi")
        assert "过载" in str(ei.value)

    def test_claude_ignores_non_text_delta(self, patch_http):
        """thinking 等非 text_delta 不应混入结果"""
        lines = [
            ('data: ' + json.dumps({"type": "content_block_delta",
                                    "delta": {"type": "thinking_delta",
                                              "thinking": "内部思考"}})).encode(),
        ] + anthropic_sse("answer")
        rec = patch_http(FakeResponse(lines=lines))
        assert AI.ClaudeClient(api_key="k").chat_stream("hi") == "answer"

    def test_claude_defaults(self):
        c = AI.ClaudeClient(api_key="k")
        assert c.base_url == "https://api.anthropic.com/v1"
        assert c.model

    def test_claude_non_stream_chat_parses_content_blocks(self, patch_http):
        resp = FakeResponse(json_data={"content": [
            {"type": "text", "text": "第一段"},
            {"type": "tool_use", "id": "x"},
            {"type": "text", "text": "第二段"},
        ]})
        rec = patch_http(resp)
        text = AI.ClaudeClient(api_key="k").chat("hi")
        assert text == "第一段第二段"
        assert rec.url.endswith("/messages")
        assert "stream" not in rec.payload


# =========================================================
# 基类兜底
# =========================================================

class TestBaseClassFallback:
    """基类也必须提供 chat_stream，否则子类会 AttributeError"""

    def test_base_has_chat_stream(self):
        assert hasattr(AI.AIClient, 'chat_stream')

    def test_base_fallback_is_non_streaming_but_correct(self, patch_http):
        class Dummy(AI.AIClient):
            def _chat(self, messages, system=""):
                return "完整回复"

        rec = patch_http(FakeResponse(json_data={}))
        d = Dummy(api_key="k", provider="openai")
        got = []
        text = d.chat_stream("hi", callback=got.append)
        assert text == "完整回复"
        # 兜底实现只能一次性回调（没有增量）
        assert got == ["完整回复"]
        # 注意：chat() 调 _make_request 时不传 stream，故为 None（等价于非流式）
        assert rec.stream is None, "基类兜底不走流式"

    def test_all_registered_clients_have_chat_stream(self):
        """工厂注册的每个 provider 都必须能流式"""
        for provider in AI.AIClientFactory.list_providers():
            key = provider[0] if isinstance(provider, (tuple, list)) else provider
            c = AI.AIClientFactory.create(provider=key, api_key="k")
            assert hasattr(c, "chat_stream"), (
                "provider %s 的客户端缺少 chat_stream" % key)


# =========================================================
# 取消语义
# =========================================================

class TestCancellation:
    def test_cancel_stops_openai_stream(self, patch_http):
        lines = openai_sse("a", "b", "c")
        rec = patch_http(FakeResponse(lines=lines))
        c = AI.OpenAIClient(api_key="k", provider="openai")
        got = []

        def on_chunk(t):
            got.append(t)
            c.cancel()          # 收到第一段就取消

        text = c.chat_stream("hi", callback=on_chunk)
        assert got == ["a"], "取消后不应继续收片段"
        assert text == "a", "取消时应返回已收到的部分"

    def test_cancel_stops_claude_stream(self, patch_http):
        rec = patch_http(FakeResponse(lines=anthropic_sse("a", "b", "c")))
        c = AI.ClaudeClient(api_key="k")
        got = []

        def on_chunk(t):
            got.append(t)
            c.cancel()

        text = c.chat_stream("hi", callback=on_chunk)
        assert got == ["a"]
        assert text == "a"

    def test_chat_stream_clears_previous_cancel(self, patch_http):
        """上一次取消不应影响下一次请求"""
        patch_http(FakeResponse(lines=openai_sse("ok")))
        c = AI.OpenAIClient(api_key="k", provider="openai")
        c.cancel()
        assert c.is_cancelled() is True
        assert c.chat_stream("hi") == "ok"
        assert c.is_cancelled() is False, "新请求必须清除取消标志"


# =========================================================
# 工厂
# =========================================================

class TestFactory:
    def test_all_providers_instantiable(self):
        for key in ("openai", "ollama", "deepseek", "qwen", "moonshot",
                    "zhipu", "claude", "anthropic"):
            c = AI.AIClientFactory.create(provider=key, api_key="k")
            assert isinstance(c, AI.AIClient), key

    def test_claude_and_anthropic_map_to_claude_client(self):
        for key in ("claude", "anthropic"):
            c = AI.AIClientFactory.create(provider=key, api_key="k")
            assert isinstance(c, AI.ClaudeClient), key

    def test_other_providers_map_to_openai_client(self):
        for key in ("openai", "ollama", "deepseek", "qwen", "moonshot",
                    "zhipu"):
            c = AI.AIClientFactory.create(provider=key, api_key="k")
            assert isinstance(c, AI.OpenAIClient), key

    def test_unknown_provider_raises_config_error(self):
        """未知 provider 按设计抛 AIConfigError（而非静默回退）"""
        with pytest.raises(AI.AIConfigError):
            AI.AIClientFactory.create(provider="nope", api_key="k")

    def test_default_models_per_provider(self):
        for key in ("openai", "ollama", "deepseek", "qwen", "moonshot",
                    "zhipu", "claude"):
            models = AI.AIClientFactory.get_default_models(key)
            assert models, "provider %s 缺少默认模型" % key

    def test_default_base_urls(self):
        expect = {
            "openai": "https://api.openai.com/v1",
            "ollama": "http://localhost:11434/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "moonshot": "https://api.moonshot.cn/v1",
        }
        for prov, url in expect.items():
            c = AI.AIClientFactory.create(provider=prov, api_key="k")
            assert c.base_url == url, prov

    def test_claude_default_base_url(self):
        c = AI.AIClientFactory.create(provider="claude", api_key="k")
        assert c.base_url == "https://api.anthropic.com/v1"


# =========================================================
# 非流式 chat 的协议细节
# =========================================================

class TestChatNonStream:
    def test_openai_chat_returns_message_content(self, patch_http):
        rec = patch_http(FakeResponse(json_data={
            "choices": [{"message": {"content": "答案"}}]}))
        assert AI.OpenAIClient(api_key="k", provider="openai").chat("q") == "答案"
        assert rec.url.endswith("/chat/completions")
        assert rec.payload.get("stream") is None

    def test_openai_chat_raises_on_error_object(self, patch_http):
        patch_http(FakeResponse(json_data={
            "error": {"message": "额度不足"}}))
        with pytest.raises(AI.AIClientError) as ei:
            AI.OpenAIClient(api_key="k", provider="openai").chat("q")
        assert "额度不足" in str(ei.value)

    def test_openai_chat_raises_on_empty_choices(self, patch_http):
        patch_http(FakeResponse(json_data={"choices": []}))
        with pytest.raises(AI.AIClientError):
            AI.OpenAIClient(api_key="k", provider="openai").chat("q")

    def test_requires_key_message(self, patch_http):
        patch_http(FakeResponse(json_data={}))
        with pytest.raises(AI.AIAuthError) as ei:
            AI.OpenAIClient(api_key="", provider="openai").chat("q")
        assert "API Key" in str(ei.value)


# =========================================================
# 多轮对话历史（此前 _history 只声明、从未使用）
# =========================================================

class TestChatHistory:
    def _client(self):
        c = AI.OpenAIClient(api_key="k", provider="openai")
        c.timeout = 1
        return c

    def test_history_empty_by_default(self):
        c = self._client()
        assert c.get_history() == []
        assert c.history_turns() == 0

    def test_no_history_recorded_when_disabled(self, patch_http):
        patch_http(FakeResponse(json_data={
            "choices": [{"message": {"content": "答案"}}]}))
        c = self._client()
        c.chat("问题")
        assert c.get_history() == [], "默认不应记录历史"

    def test_history_recorded_when_enabled(self, patch_http):
        patch_http(FakeResponse(json_data={
            "choices": [{"message": {"content": "答案"}}]}))
        c = self._client()
        c.chat("问题", use_history=True)
        h = c.get_history()
        assert len(h) == 2
        assert h[0] == {"role": "user", "content": "问题"}
        assert h[1] == {"role": "assistant", "content": "答案"}
        assert c.history_turns() == 2

    def test_second_turn_sends_previous_context(self, patch_http):
        """第二轮必须把第一轮带上去 —— 这是'多轮'的本质"""
        rec = patch_http(FakeResponse(json_data={
            "choices": [{"message": {"content": "A1"}}]}))
        c = self._client()
        c.chat("Q1", use_history=True)
        c.chat("Q2", use_history=True)
        sent = rec.payload["messages"]
        roles = [(m["role"], m["content"]) for m in sent]
        assert roles == [("user", "Q1"), ("assistant", "A1"),
                         ("user", "Q2")], roles

    def test_system_not_duplicated_into_history(self, patch_http):
        rec = patch_http(FakeResponse(json_data={
            "choices": [{"message": {"content": "A"}}]}))
        c = self._client()
        c.chat("Q", system="SYS", use_history=True)
        # system 每次作为独立首条发送，不进入 history 本体
        assert rec.payload["messages"][0] == {"role": "system", "content": "SYS"}
        assert all(m["role"] != "system" for m in c.get_history())

    def test_history_is_trimmed(self, patch_http):
        patch_http(FakeResponse(json_data={
            "choices": [{"message": {"content": "A"}}]}))
        c = self._client()
        c.max_history_turns = 2          # 上限 2 轮 = 4 条
        for i in range(6):
            c.chat("Q%d" % i, use_history=True)
        assert c.history_turns() <= 4, c.get_history()
        # 保留的必须是最新的
        assert c.get_history()[-1]["content"] == "A"

    def test_reset_history(self, patch_http):
        patch_http(FakeResponse(json_data={
            "choices": [{"message": {"content": "A"}}]}))
        c = self._client()
        c.chat("Q", use_history=True)
        assert c.history_turns() == 2
        c.reset_history()
        assert c.history_turns() == 0

    def test_get_history_returns_copy(self, patch_http):
        patch_http(FakeResponse(json_data={
            "choices": [{"message": {"content": "A"}}]}))
        c = self._client()
        c.chat("Q", use_history=True)
        h = c.get_history()
        h.append({"role": "user", "content": "篡改"})
        assert c.history_turns() == 2, "外部修改不应影响内部历史"

    def test_stream_history_recorded(self, patch_http):
        patch_http(FakeResponse(lines=openai_sse("Hello", "!")))
        c = self._client()
        c.chat_stream("Q", use_history=True)
        h = c.get_history()
        assert len(h) == 2
        assert h[1] == {"role": "assistant", "content": "Hello!"}

    def test_stream_second_turn_includes_context(self, patch_http):
        rec = patch_http(FakeResponse(lines=openai_sse("A1")))
        c = self._client()
        c.chat_stream("Q1", use_history=True)
        c.chat_stream("Q2", use_history=True)
        roles = [(m["role"], m["content"]) for m in rec.payload["messages"]]
        assert roles == [("user", "Q1"), ("assistant", "A1"), ("user", "Q2")]

    def test_claude_stream_history(self, patch_http):
        patch_http(FakeResponse(lines=anthropic_sse("你好")))
        c = AI.ClaudeClient(api_key="k")
        c.chat_stream("Q", use_history=True)
        assert c.get_history()[-1]["content"] == "你好"


# =========================================================
# token 分档
# =========================================================

class TestTokenTiers:
    def test_tiers_are_ordered(self):
        vals = [AI.TOKEN_TIERS[t] for t in ("tiny", "short", "medium", "large")]
        assert vals == sorted(vals), "档位应递增"
        assert len(set(vals)) == len(vals)

    def test_tokens_for_known_and_unknown(self):
        assert AI.tokens_for("tiny") == AI.TOKEN_TIERS["tiny"]
        assert AI.tokens_for("large") == AI.TOKEN_TIERS["large"]
        # 未知档位回退到默认值，而不是抛异常
        assert AI.tokens_for("nope") == AI.DEFAULT_MAX_TOKENS

    def test_stream_respects_max_tokens_override(self, patch_http):
        rec = patch_http(FakeResponse(lines=openai_sse("x")))
        c = AI.OpenAIClient(api_key="k", provider="openai", max_tokens=4096)
        c.chat_stream("q", max_tokens=AI.tokens_for("tiny"))
        assert rec.payload["max_tokens"] == AI.TOKEN_TIERS["tiny"]

    def test_stream_uses_instance_default_when_not_overridden(self, patch_http):
        rec = patch_http(FakeResponse(lines=openai_sse("x")))
        c = AI.OpenAIClient(api_key="k", provider="openai", max_tokens=1234)
        c.chat_stream("q")
        assert rec.payload["max_tokens"] == 1234

    def test_claude_stream_respects_override(self, patch_http):
        rec = patch_http(FakeResponse(lines=anthropic_sse("x")))
        c = AI.ClaudeClient(api_key="k", max_tokens=4096)
        c.chat_stream("q", max_tokens=AI.tokens_for("short"))
        assert rec.payload["max_tokens"] == AI.TOKEN_TIERS["short"]
