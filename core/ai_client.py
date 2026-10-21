#!usr/bin/env python
#-*- coding: utf-8 -*-
"""青草编辑器 AI 客户端（极简版）"""

import json
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, pyqtSignal


# 敏感信息安全存储（v2.1）
try:
    from core.secure_storage import delete_secret, get_secure_storage, load_secret, save_secret
    _SECURE_STORAGE_OK = True
except ImportError as e:
    print(f"[AI] SecureStorage 不可用: {e}")
    _SECURE_STORAGE_OK = False

    # 占位符，避免调用处崩溃
    def save_secret(k, v):
        return False

    def load_secret(k, d=""):
        return d

    def delete_secret(k):
        return False


DEFAULT_TIMEOUT = 60
DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.3
STREAM_TIMEOUT = 300

# 多轮历史保留的最大轮数（一轮 = user + assistant）。
# 历史会随请求一起发送，无上限会撑爆模型上下文窗口。
MAX_HISTORY_TURNS = 10

# 按任务类型分档的 max_tokens。
#
# 为什么需要分档：原先所有请求都用 DEFAULT_MAX_TOKENS=4096。
# 对"生成单元测试 / 重构"这类任务 4096 是合理的，但对
# "解释代码 / 代码摘要"这类只需要一两段文字的任务，模型可能一直
# 输出到上限，白白增加等待时间与 token 费用。
#
# 取值保守（宁大勿小），避免把输出截断：
#   tiny   —— 摘要、一行说明
#   short  —— 解释、加注释、Docstring
#   medium —— 重构、性能优化、Code Review
#   large  —— 生成测试、语言转换（可能整文件重写）
TOKEN_TIERS = {
    "tiny": 512,
    "short": 1024,
    "medium": 2048,
    "large": 4096,
}


def tokens_for(tier: str) -> int:
    """把档位名换成 max_tokens（未知档位回退到默认值）"""
    return TOKEN_TIERS.get(tier, DEFAULT_MAX_TOKENS)


class AIClientError(Exception):
    pass


class AIAuthError(AIClientError):
    pass


class AIConfigError(AIClientError):
    pass


class AICancelledError(AIClientError):
    pass


#!============================================================
#!提示词模板
#!============================================================
PROMPT_EXPLAIN = """请用中文解释以下代码的功能和逻辑。
分点说明，简明扼要。

代码：
```{lang}
{code}
```"""

PROMPT_REFACTOR = """请对以下代码进行重构，保持功能完全不变但提升可读性和性能。
只输出重构后的完整代码，不要解释。

代码：
```{lang}
{code}
```"""

PROMPT_FIX = """请找出以下代码中的 bug 并修复。
只输出修复后的完整代码。

代码：
```{lang}
{code}
```"""

PROMPT_COMMENT = """请为以下代码添加中文注释。
只输出加注释后的完整代码。

代码：
```{lang}
{code}
```"""

PROMPT_TESTS = """请为以下代码生成单元测试，使用 {framework} 框架。
只输出测试代码。

代码：
```{lang}
{code}
```"""

PROMPT_REVIEW = """请对以下代码进行 Code Review。
用中文，分点说明问题和改进建议。

代码：
```{lang}
{code}
```"""

PROMPT_SUMMARY = """请用中文总结以下代码的核心功能。不超过 3 句话。

代码：
```{lang}
{code}
```"""


#!============================================================
#!AI 客户端基类
#!============================================================
class AIClient(QObject):
    response_ready = pyqtSignal(str)
    stream_chunk = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, provider="openai", api_key="", model="",
                 base_url="", timeout=DEFAULT_TIMEOUT,
                 max_tokens=DEFAULT_MAX_TOKENS,
                 temperature=DEFAULT_TEMPERATURE, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip('/') if base_url else ""
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._cancel = threading.Event()
        # 多轮对话历史（此前只声明、从未使用，见 chat(use_history=...)）
        self._history: List[Dict[str, str]] = []
        self.max_history_turns = MAX_HISTORY_TURNS

    # --------------------------------------------------------
    # 多轮对话历史
    # --------------------------------------------------------
    def reset_history(self):
        """清空对话历史（开始新话题时调用）"""
        self._history = []

    def get_history(self) -> List[Dict[str, str]]:
        """返回历史副本（勿直接改内部列表）"""
        return [dict(m) for m in self._history]

    def history_turns(self) -> int:
        """已记录的历史条数（user + assistant 各算一条）"""
        return len(self._history)

    def _trim_history(self):
        """只保留最近 N 轮（一轮 = user + assistant）。

        防止长会话把 token 撑爆 —— 历史会随每次请求一起发送，
        无上限增长会很快超出模型上下文窗口。
        """
        max_msgs = max(2, int(self.max_history_turns) * 2)
        if len(self._history) > max_msgs:
            self._history = self._history[-max_msgs:]

    def chat(self, prompt="", system="", messages=None,
             use_history=False):
        """同步对话

        参数:
            use_history: 为 True 时把本次对话并入多轮历史，
                并把历史一并发送给模型（实现"接着上文聊"）。
                流式接口 `chat_stream` 同样支持该参数。
        """
        if messages is None:
            messages = []
            if prompt:
                messages.append({"role": "user", "content": prompt})
        if not self.api_key and self.provider not in ("ollama", "custom"):
            raise AIAuthError("未配置 API Key")
        try:
            to_send = list(messages)
            if use_history:
                to_send = self._history + to_send
            result = self._chat(to_send, system)
            if use_history:
                self._history.extend(messages)
                self._history.append({"role": "assistant",
                                      "content": result or ""})
                self._trim_history()
            self.response_ready.emit(result)
            return result
        except Exception as e:
            self.error_occurred.emit(str(e))
            raise AIClientError(str(e))

    def chat_async(self, prompt="", system="",
                   callback=None, error_callback=None,
                   use_history=False):
        """异步对话（在后台线程执行 `chat`，通过回调返回结果）

        这是**编程式 API**，面向脚本或需要"发起即返回"的场景。
        UI（plugins/ai_assistant）不用它 —— 那里用 `AIWorker` +
        `chat_stream`，因为需要流式增量与可取消。

        注意：返回值是 `None`（不阻塞），结果通过 `callback` 交付；
        `error_callback` 收到错误字符串。取消请用 `cancel()`。
        """
        self._cancel.clear()

        def worker():
            try:
                result = self.chat(prompt, system, use_history=use_history)
                if callback:
                    callback(result)
            except Exception as e:
                if error_callback:
                    error_callback(str(e))

        t = threading.Thread(target=worker, daemon=True,
                             name="ai-chat-async")
        t.start()
        return t

    def cancel(self):
        self._cancel.set()

    def is_cancelled(self):
        return self._cancel.is_set()

    def chat_stream(self, prompt="", system="", callback=None,
                    use_history=False):
        """流式对话（基类默认实现：非流式 + 一次性回调）。

        子类应重写本方法以提供**真正的增量输出**：

          * `OpenAIClient`  —— OpenAI / Ollama / DeepSeek / 通义 / Kimi /
            智谱 的 SSE（`/chat/completions`，`choices[0].delta.content`）
          * `ClaudeClient`  —— Anthropic Messages SSE（`/messages`，
            `content_block_delta` → `delta.text`）

        为什么基类必须有这个方法：
            原先 `chat_stream` 只定义在 `OpenAIClient` 上，而
            `ClaudeClient` 继承的是 `AIClient` → 对 Claude 调用
            `hasattr(client, 'chat_stream')` 为假，导致：
              * 插件退化为**非流式**（用户盯着空白对话框直到全部生成完）；
              * 任何直接调用 `client.chat_stream(...)` 的代码
                抛 `AttributeError`。
            基类提供兜底后，至少保证"接口存在、结果正确"，只是没有增量。
        """
        # 尊重取消语义：先清标志，再发一次请求
        self._cancel.clear()
        messages = []
        if prompt:
            messages.append({"role": "user", "content": prompt})
        text = self.chat(messages=messages, system=system,
                         use_history=use_history)
        if callback and text:
            callback(text)
        return text

    def _chat(self, messages, system=""):
        raise NotImplementedError

    def _make_request(self, url, headers, json_data,
                      stream=False, timeout=None):
        """HTTP 请求"""
        try:
            import requests
        except ImportError:
            raise AIClientError("缺少 requests 库，请运行: pip install requests")

        timeout = timeout or self.timeout
        try:
            if stream:
                resp = requests.post(url, headers=headers, json=json_data,
                                     timeout=timeout, stream=True)
            else:
                resp = requests.post(url, headers=headers, json=json_data,
                                     timeout=timeout)
            if resp.status_code == 401:
                raise AIAuthError("API Key 无效")
            if resp.status_code >= 400:
                try:
                    detail = resp.json()
                except Exception:
                    detail = resp.text[:200]
                raise AIClientError("HTTP %d: %s" % (resp.status_code, detail))
            return resp
        except (AIAuthError, AIClientError):
            raise
        except Exception as e:
            raise AIClientError("请求失败: %s" % e)

    def get_info(self):
        return {
            'provider': self.provider,
            'model': self.model,
            'base_url': self.base_url,
            'has_api_key': bool(self.api_key),
        }

    def __repr__(self):
        return "<%s provider=%s model=%s>" % (
            self.__class__.__name__, self.provider, self.model
        )


#!============================================================
#!OpenAI 兼容客户端
#!============================================================
class OpenAIClient(AIClient):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.model:
            self.model = self._default_model()
        if not self.base_url:
            self.base_url = self._default_base_url()

    def _default_model(self):
        if self.provider == "ollama":
            return "llama3.2"
        if self.provider == "deepseek":
            return "deepseek-chat"
        if self.provider == "qwen":
            return "qwen-plus"
        if self.provider == "moonshot":
            return "moonshot-v1-8k"
        if self.provider == "zhipu":
            return "glm-4"
        return "gpt-4o-mini"

    def _default_base_url(self):
        urls = {
            "openai": "https://api.openai.com/v1",
            "ollama": "http://localhost:11434/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "moonshot": "https://api.moonshot.cn/v1",
            "zhipu": "https://open.bigmodel.cn/api/paas/v4",
        }
        return urls.get(self.provider, "https://api.openai.com/v1")

    def _chat(self, messages, system=""):
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key

        payload = {
            "model": self.model,
            "messages": full_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        url = self.base_url + "/chat/completions"
        resp = self._make_request(url, headers, payload)

        data = resp.json()
        if "error" in data:
            raise AIClientError("API 错误: %s" % data["error"].get("message", ""))
        choices = data.get("choices", [])
        if not choices:
            raise AIClientError("API 返回空结果")
        return choices[0].get("message", {}).get("content", "")

    def chat_stream(self, prompt="", system="", callback=None,
                    use_history=False, max_tokens=None):
        """流式对话（OpenAI 兼容族：OpenAI / Ollama / DeepSeek / 通义 /
        Moonshot / 智谱）。

        协议：``POST {base}/chat/completions`` + SSE，每行
        ``data: {"choices":[{"delta":{"content":"..."}}]}``，以
        ``data: [DONE]`` 结束。

        参数:
            use_history: 并入并发送多轮历史（实现"接着上文聊"）
            max_tokens:  覆盖本次请求的 token 上限（按任务分档用，
                         默认沿用实例的 max_tokens）
        """
        if not self.api_key and self.provider not in ("ollama", "custom"):
            raise AIAuthError("未配置 API Key")

        # 清除上一次的取消标志 —— 否则用户取消一次后，**后续请求会
        # 立刻在第一行就 break，表现为"AI 永久无响应"**。
        # （基类兜底实现有这一步，此处原先遗漏。）
        self._cancel.clear()

        user_msg = {"role": "user", "content": prompt}
        messages = self._history + [user_msg] if use_history else [user_msg]
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key

        payload = {
            "model": self.model,
            "messages": full_messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
            "stream": True,
        }

        url = self.base_url + "/chat/completions"
        resp = self._make_request(url, headers, payload,
                                  stream=True, timeout=STREAM_TIMEOUT)

        full_text = []
        for line in resp.iter_lines():
            if self.is_cancelled():
                break
            if not line:
                continue
            line = line.decode('utf-8', errors='replace').strip()
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                content = choices[0].get("delta", {}).get("content", "")
                if content:
                    full_text.append(content)
                    if callback:
                        callback(content)
            except json.JSONDecodeError:
                continue
        resp.close()
        text = "".join(full_text)
        if use_history:
            # 只记录**已完成**的轮次；被取消时也记录已收到的部分，
            # 这样用户"接着上文"时上下文与所见内容一致。
            self._history.append(user_msg)
            self._history.append({"role": "assistant", "content": text})
            self._trim_history()
        return text


#!============================================================
#!Claude 客户端
#!============================================================
class ClaudeClient(AIClient):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.model:
            self.model = "claude-3-5-sonnet-20241022"
        if not self.base_url:
            self.base_url = "https://api.anthropic.com/v1"

    def _chat(self, messages, system=""):
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
            "temperature": self.temperature,
        }
        if system:
            payload["system"] = system

        url = self.base_url + "/messages"
        resp = self._make_request(url, headers, payload)
        data = resp.json()
        if "error" in data:
            raise AIClientError("API 错误: %s" % data["error"].get("message", ""))
        content = data.get("content", [])
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        return "".join(text_parts)

    def chat_stream(self, prompt="", system="", callback=None,
                    use_history=False, max_tokens=None):
        """Anthropic Messages API 的**真正流式**实现（SSE）。

        与 OpenAI 的区别：
          * 端点      `/messages`（而非 `/chat/completions`）
          * 鉴权头    `x-api-key` + `anthropic-version`（而非 Bearer）
          * system    是**顶层字段**，不放在 messages 数组里
          * 事件格式  每行 `event: xxx` + `data: {...}`，
            `data` 里没有 `choices`，而是按 `type` 区分的对象：

              {"type":"content_block_delta",
               "delta":{"type":"text_delta","text":"片段"}}

        因此**不能**复用 OpenAI 的解析逻辑（那正是原先的缺陷：
        `ClaudeClient` 没有 `chat_stream`，于是退化为非流式）。
        """
        if not self.api_key:
            raise AIAuthError("未配置 API Key")

        self._cancel.clear()

        user_msg = {"role": "user", "content": prompt}
        convo = self._history + [user_msg] if use_history else [user_msg]

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Accept": "text/event-stream",
        }
        payload = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": convo,
            "temperature": self.temperature,
            "stream": True,
        }
        if system:
            payload["system"] = system

        url = self.base_url + "/messages"
        resp = self._make_request(url, headers, payload, stream=True,
                                  timeout=STREAM_TIMEOUT)

        full_text = []
        try:
            for line in resp.iter_lines():
                if self.is_cancelled():
                    break
                if not line:
                    continue
                line = line.decode("utf-8", errors="replace").strip()
                # 只关心 data 行；event: 行本身不含内容
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                ctype = chunk.get("type")
                if ctype == "content_block_delta":
                    delta = chunk.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        text = delta.get("text") or ""
                        if text:
                            full_text.append(text)
                            if callback:
                                callback(text)
                elif ctype == "error":
                    err = chunk.get("error") or {}
                    raise AIClientError(
                        "API 错误: %s" % err.get("message", "未知错误"))
                # 其它事件（message_start / content_block_start /
                # ping / message_delta / message_stop）无需处理
        finally:
            try:
                resp.close()
            except Exception:
                pass

        text = "".join(full_text)
        if use_history:
            self._history.append(user_msg)
            self._history.append({"role": "assistant", "content": text})
            self._trim_history()
        return text


#!============================================================
#!客户端工厂
#!============================================================
class AIClientFactory:

    _registry = {
        "openai": OpenAIClient,
        "ollama": OpenAIClient,
        "deepseek": OpenAIClient,
        "qwen": OpenAIClient,
        "moonshot": OpenAIClient,
        "zhipu": OpenAIClient,
        "claude": ClaudeClient,
        "anthropic": ClaudeClient,
    }

    DISPLAY_NAMES = {
        "openai": "OpenAI",
        "ollama": "Ollama (本地)",
        "deepseek": "DeepSeek",
        "qwen": "通义千问",
        "moonshot": "Moonshot",
        "zhipu": "智谱 GLM",
        "claude": "Anthropic Claude",
    }

    DEFAULT_MODELS = {
        "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "ollama": ["llama3.2", "llama3.1", "qwen2.5", "gemma2"],
        "deepseek": ["deepseek-chat", "deepseek-coder"],
        "qwen": ["qwen-plus", "qwen-turbo", "qwen-max"],
        "moonshot": ["moonshot-v1-8k", "moonshot-v1-32k"],
        "zhipu": ["glm-4", "glm-4-plus", "glm-4-flash"],
        "claude": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"],
    }

    @classmethod
    def create(cls, provider="openai", api_key="", model="",
               base_url="", **kwargs):
        provider = provider.lower()
        client_class = cls._registry.get(provider)
        if not client_class:
            raise AIConfigError("未知的 AI 提供商: %s" % provider)
        return client_class(
            provider=provider, api_key=api_key, model=model,
            base_url=base_url, **kwargs
        )

    @classmethod
    def register(cls, provider, client_class, display_name=""):
        cls._registry[provider.lower()] = client_class
        if display_name:
            cls.DISPLAY_NAMES[provider.lower()] = display_name

    @classmethod
    def list_providers(cls):
        result = []
        for p, d in cls.DISPLAY_NAMES.items():
            if p in cls._registry:
                result.append((p, d))
        return result

    @classmethod
    def get_default_models(cls, provider):
        return cls.DEFAULT_MODELS.get(provider.lower(), [])


#!============================================================
#!全局单例
#!============================================================
_global_client = None


def get_ai_client():
    return _global_client


def set_ai_client(client):
    global _global_client
    _global_client = client


def load_ai_client_from_settings():
    """
    从 QSettings 加载 AI 客户端。

    修复说明（v2.1）:
        - API Key 从 QSettings 明文改为 SecureStorage 加密读取
        - 首次调用会自动触发从旧 QSettings 的迁移
        - 迁移失败时降级读取 QSettings（并打印警告）
    """
    try:
        from PyQt5.QtCore import QSettings
        settings = QSettings("QingCao", "AI")

        provider = settings.value("provider", "openai", type=str)
        model = settings.value("model", "", type=str)
        base_url = settings.value("base_url", "", type=str)

        # ---- API Key：优先从安全存储读取 ----
        #
        # ★ 性能修复（启动阻塞实测，cProfile）：
        #   Ollama 本地服务**不需要 API Key**，但原实现无条件调用
        #   `get_secure_storage()` → `SecureStorage._detect_backend()`；
        #   后者会对 Windows 凭据管理器做一次 set/get/delete 往返，
        #   实测 **0.37 秒**，且发生在 AI 插件激活路径（即启动路径）上。
        #   现在 provider 为本地服务（ollama 等）时直接跳过安全存储。
        api_key = ""
        _provider = (provider or "").strip().lower()
        _needs_secret = _provider not in ("ollama", "local", "lmstudio")
        if _SECURE_STORAGE_OK and _needs_secret:
            # 触发一次迁移（幂等）
            try:
                storage = get_secure_storage()
                storage.migrate_from_settings(
                    settings, "api_key", "QingCao", "AI"
                )
            except Exception as e:
                print(f"[AI] API Key 迁移失败: {e}")

            api_key = load_secret("ai_api_key", "")

        # 兜底：如果安全存储为空，再尝试旧 QSettings（兼容旧版）
        if not api_key:
            legacy_key = settings.value("api_key", "", type=str)
            if legacy_key:
                print("[AI] 警告：从明文 QSettings 读取 API Key（建议升级）")
                api_key = legacy_key

        # 检查配置完整性（本地服务不需要 key）
        if not api_key and _needs_secret:
            return None

        client = AIClientFactory.create(
            provider=provider, api_key=api_key,
            model=model, base_url=base_url,
        )
        set_ai_client(client)
        return client

    except Exception as e:
        print("[AI] 加载客户端失败: %s" % e)
        return None


def save_ai_client_to_settings(client):
    """
    保存 AI 客户端配置。

    修复说明（v2.1）:
        - API Key 加密写入 SecureStorage
        - 非敏感信息（provider / model / base_url）继续走 QSettings
        - 保存成功后清理旧 QSettings 中的明文 api_key
    """
    try:
        from PyQt5.QtCore import QSettings
        settings = QSettings("QingCao", "AI")

        # ---- 非敏感信息：QSettings ----
        settings.setValue("provider", client.provider)
        settings.setValue("model", client.model)
        settings.setValue("base_url", client.base_url)

        # ---- 敏感信息：SecureStorage ----
        if _SECURE_STORAGE_OK:
            if client.api_key:
                ok = save_secret("ai_api_key", client.api_key)
                if not ok:
                    print("[AI] 警告：API Key 加密保存失败，降级为明文")
                    settings.setValue("api_key", client.api_key)
                else:
                    # 加密成功 → 清理旧明文
                    settings.remove("api_key")
            else:
                delete_secret("ai_api_key")
                settings.remove("api_key")
        else:
            # 安全存储不可用 → 明文存储（附警告）
            print("[AI] 警告：SecureStorage 不可用，API Key 将以明文存储")
            settings.setValue("api_key", client.api_key)

        settings.sync()

    except Exception as e:
        print("[AI] 保存客户端失败: %s" % e)


#!============================================================
#!便捷函数
#!
#!定位说明（避免误当成死代码删掉）：
#!    这里的 quick_* 与 chat_async 是**编程式公开 API**，面向脚本、
#!    插件内部或未来的批处理场景，提供"一句话拿结果"的同步/异步入口。
#!
#!    编辑器 UI（plugins/ai_assistant）走的是**另一条路径**：
#!    `AIWorker` + `chat_stream`，因为它需要流式增量输出、
#!    可取消、以及按任务分档的 token 预算。两条路径共用同一套
#!    PROMPT_* 模板与客户端，因此不会出现提示词不一致。
#!
#!    两者都不要删：
#!      * 删 quick_*    → 失去无 UI 场景的调用方式
#!      * 删 UI 路径    → 失去流式体验
#!    新增提示词时请同时评估两边是否需要接入。
#!============================================================
def quick_chat(prompt, system=""):
    client = get_ai_client()
    if not client:
        raise AIConfigError("未配置 AI 客户端")
    return client.chat(prompt=prompt, system=system)


def quick_explain(code, lang="python"):
    client = get_ai_client()
    if not client:
        raise AIConfigError("未配置 AI 客户端")
    return client.chat(
        prompt=PROMPT_EXPLAIN.format(code=code, lang=lang),
        system="你是资深开发者，用中文解释代码。"
    )


def quick_refactor(code, lang="python"):
    client = get_ai_client()
    if not client:
        raise AIConfigError("未配置 AI 客户端")
    return client.chat(
        prompt=PROMPT_REFACTOR.format(code=code, lang=lang),
        system="你是重构专家。"
    )


def quick_tests(code, lang="python", framework="pytest"):
    client = get_ai_client()
    if not client:
        raise AIConfigError("未配置 AI 客户端")
    return client.chat(
        prompt=PROMPT_TESTS.format(code=code, lang=lang,
                                   framework=framework),
        system="你是测试工程师。"
    )


def quick_review(code, lang="python"):
    client = get_ai_client()
    if not client:
        raise AIConfigError("未配置 AI 客户端")
    return client.chat(
        prompt=PROMPT_REVIEW.format(code=code, lang=lang),
        system="你是资深开发者。"
    )


def quick_summary(code, lang="python"):
    client = get_ai_client()
    if not client:
        raise AIConfigError("未配置 AI 客户端")
    return client.chat(
        prompt=PROMPT_SUMMARY.format(code=code, lang=lang),
        system="用中文总结代码。"
    )