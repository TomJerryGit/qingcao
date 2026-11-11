# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""图标缓存（v2.25 从 icon_manager 拆出）。"""

from infrastructure.icon_manager_common import *  # noqa: F401,F403


class IconCache:
    """
    图标缓存。

    线程安全的 LRU 缓存，支持过期清理。
    """

    def __init__(self, max_size: int = MAX_CACHE_SIZE, ttl: float = CACHE_TTL):
        self.max_size = max_size
        self.ttl = ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[QIcon]:
        """获取缓存图标"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            if entry.is_expired(self.ttl):
                del self._cache[key]
                return None

            entry.touch()
            return entry.icon

    def put(self, key: str, icon: QIcon):
        """写入缓存"""
        with self._lock:
            # 检查容量
            if len(self._cache) >= self.max_size:
                self._evict_lru()

            self._cache[key] = CacheEntry(icon)

    def _evict_lru(self):
        """淘汰最久未使用的条目"""
        if not self._cache:
            return

        # 找到最久未访问的
        lru_key = min(self._cache.keys(), key=lambda k: self._cache[k].last_access)
        del self._cache[lru_key]

    def invalidate(self, key: str):
        """使指定键失效"""
        with self._lock:
            self._cache.pop(key, None)

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()

    def cleanup(self):
        """清理过期条目"""
        with self._lock:
            expired = [k for k, v in self._cache.items() if v.is_expired(self.ttl)]
            for k in expired:
                del self._cache[k]

    def size(self) -> int:
        """当前缓存大小"""
        return len(self._cache)

    def stats(self) -> Dict[str, Any]:
        """缓存统计"""
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "ttl": self.ttl,
                "total_access": sum(e.access_count for e in self._cache.values()),
            }


# ============================================================
# 图标提供者基类
# ============================================================
