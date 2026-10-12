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
        self._history = []

    def chat(self, prompt="", system="", messages=None):
        """同步对话"""
        if messages is None:
            messages = []
            if prompt:
                messages.append({"role": "user", "content": prompt})
        if not self.api_key and self.provider not in ("ollama", "custom"):
            raise AIAuthError("未配置 API Key")
        try:
            result = self._chat(messages, system)
            self.response_ready.emit(result)
            return result
        except Exception as e:
            self.error_occurred.emit(str(e))
            raise AIClientError(str(e))

    def chat_async(self, prompt="", system="",
                   callback=None, error_callback=None):
        """异步对话"""
        self._cancel.clear()

        def worker():
            try:
                result = self.chat(prompt, system)
                if callback:
                    callback(result)
            except Exception as e:
                if error_callback:
                    error_callback(str(e))

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def cancel(self):
        self._cancel.set()

    def is_cancelled(self):
        return self._cancel.is_set()

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

    def chat_stream(self, prompt="", system="", callback=None):
        """流式对话"""
        if not self.api_key and self.provider not in ("ollama", "custom"):
            raise AIAuthError("未配置 API Key")

        messages = [{"role": "user", "content": prompt}]
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
        return "".join(full_text)


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
        api_key = ""
        if _SECURE_STORAGE_OK:
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

        # 检查配置完整性
        if not api_key and provider != "ollama":
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