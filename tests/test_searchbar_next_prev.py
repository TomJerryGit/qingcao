"""SearchBar next/prev 逻辑测试（P0-C2）"""
import pytest


def _find_next(matches, pos):
    """从 pos 之后找第一个 match"""
    for m in matches:
        if m.start > pos:
            return m
    return None


def _find_prev(matches, pos):
    """从 pos 之前找最后一个 match"""
    for m in reversed(matches):
        if m.end <= pos:
            return m
    return None


class TestSearchNextPrev:
    def test_basic_next(self):
        try:
            from core.content_provider import MemoryProvider
            from core.search import SearchEngine, SearchOptions
        except ImportError:
            pytest.skip("search 不可用")

        provider = MemoryProvider()
        provider.open(initial_text="foo bar foo baz foo")
        options = SearchOptions(pattern="foo")
        engine = SearchEngine(provider, options)
        result = engine.search()

        assert result.count == 3

        # 从 0 位置找 next → 第一个（start=0）
        # 我们要找一个 start > 0 的
        m = _find_next(result.matches, 0)
        assert m is not None
        assert m.start == 8  # 第二个 foo

    def test_basic_prev(self):
        try:
            from core.content_provider import MemoryProvider
            from core.search import SearchEngine, SearchOptions
        except ImportError:
            pytest.skip("search 不可用")

        provider = MemoryProvider()
        provider.open(initial_text="foo bar foo baz foo")
        options = SearchOptions(pattern="foo")
        engine = SearchEngine(provider, options)
        result = engine.search()

        # 从末尾往前找
        m = _find_prev(result.matches, 9999)
        assert m is not None
        assert m.start == 16  # 最后一个 foo

    def test_wrap_around(self):
        """无匹配时循环到另一端"""
        try:
            from core.content_provider import MemoryProvider
            from core.search import SearchEngine, SearchOptions
        except ImportError:
            pytest.skip("search 不可用")

        provider = MemoryProvider()
        provider.open(initial_text="foo bar")
        options = SearchOptions(pattern="foo")
        engine = SearchEngine(provider, options)
        result = engine.search()

        # 从 pos=100 找 next → 无 → 循环到第一个
        m = _find_next(result.matches, 100)
        assert m is None  # 我们不用 wraps 的版本

        # 模拟 wrap
        wrapped = m or result.matches[0]
        assert wrapped.start == 0