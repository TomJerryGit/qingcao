# -*- coding: utf-8 -*-
"""AI 结果缓存

为什么需要
----------
编辑器里的 AI 动作（解释代码 / 加注释 / Review …）常常被**重复请求**：
用户切换标签再切回来、误关对话框后重开、同一段代码反复让 AI "再解释一次"。
每次都是一次真实的 HTTP 请求 —— 有延迟，也消耗 token / 费用。

本模块提供一个内存 LRU 缓存，键由「请求的全部可影响输出的参数」组成：

    provider · model · base_url · temperature · max_tokens
    · system 提示词 · 用户提示词全文

只要这些都相同，模型的输出在**默认 temperature 下**就是可复现的
（严格说 LLM 采样仍有随机性，但同一请求的重复结果通常足够接近，
用户在 UI 上可以勾选"忽略缓存"来强制重新生成）。

设计要点
--------
* **纯内存**：不写盘。AI 结果可能包含敏感代码，落盘会带来隐私与
  清理负担；进程退出即失效，语义简单。
* **必须显式开启使用**：`get()` 只在调用方传入 `use_cache=True` 时
  被查询 —— 多轮对话**不能**用缓存（上下文不同）。
* **容量与大小双限**：既限制条数也限制单条长度，避免长回答把
  内存吃光。
"""
import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple


# 默认最多缓存条数（LRU 淘汰）
DEFAULT_MAX_ENTRIES = 50

# 单条结果超过这个长度就不缓存（通常是语言转换/生成测试这类长输出，
# 缓存它们的收益低而内存代价高）
DEFAULT_MAX_ENTRY_CHARS = 20000


class AIResultCache:
    """线程安全的 LRU 结果缓存（进程内）

    用法::

        cache = AIResultCache()
        key = AIResultCache.make_key(client, prompt, system, max_tokens)
        cached = cache.get(key)              # None 表示未命中
        if cached is None:
            text = client.chat_stream(...)
            cache.put(key, text)
    """

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES,
                 max_entry_chars: int = DEFAULT_MAX_ENTRY_CHARS):
        self._lock = threading.Lock()
        self._data: OrderedDict[str, Tuple[str, float]] = OrderedDict()
        self.max_entries = max(1, int(max_entries))
        self.max_entry_chars = max(1, int(max_entry_chars))
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    # --------------------------------------------------------
    # 键构造
    # --------------------------------------------------------
    @staticmethod
    def make_key(client, prompt: str, system: str = "",
                 max_tokens: Optional[int] = None) -> str:
        """由请求参数构造稳定键

        把**所有会影响输出的参数**都纳入，避免"换了模型却命中旧结果"
        这类串味问题。
        """
        parts: Dict[str, Any] = {
            "provider": getattr(client, "provider", "") or "",
            "model": getattr(client, "model", "") or "",
            "base_url": getattr(client, "base_url", "") or "",
            "temperature": getattr(client, "temperature", None),
            "max_tokens": (max_tokens if max_tokens is not None
                           else getattr(client, "max_tokens", None)),
            "system": system or "",
            "prompt": prompt or "",
        }
        blob = json.dumps(parts, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # --------------------------------------------------------
    # 读写
    # --------------------------------------------------------
    def get(self, key: str) -> Optional[str]:
        """取缓存；命中会刷新 LRU 位置"""
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return item[0]

    def put(self, key: str, value: str) -> bool:
        """写缓存；返回是否真的写入"""
        if not value:
            return False
        if len(value) > self.max_entry_chars:
            return False
        with self._lock:
            self._data[key] = (value, time.time())
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)
                self.evictions += 1
        return True

    def clear(self):
        with self._lock:
            self._data.clear()

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._data),
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
            }

    def stats_text(self) -> str:
        s = self.stats()
        total = s["hits"] + s["misses"]
        rate = (s["hits"] / total * 100.0) if total else 0.0
        return ("缓存 %d 条 · 命中 %d / 未命中 %d（%.0f%%）· 淘汰 %d"
                % (s["entries"], s["hits"], s["misses"], rate,
                   s["evictions"]))


# 进程级共享实例：插件与脚本都从这里取，避免各自为政
_shared: Optional[AIResultCache] = None
_shared_lock = threading.Lock()


def get_result_cache() -> AIResultCache:
    """获取进程级共享缓存"""
    global _shared
    if _shared is None:
        with _shared_lock:
            if _shared is None:
                _shared = AIResultCache()
    return _shared
