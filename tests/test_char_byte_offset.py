# -*- coding: utf-8 -*-
"""
P1-1 字符/字节偏移测试
====================================
验证:
    - 纯 ASCII：字符偏移 == 字节偏移
    - 含中文：字节偏移 > 字符偏移，且位置精确
    - 中英混合：双写偏移都正确
    - 搜索 + 替换：替换结果正确
"""
import pytest


def _make_provider(text):
    from core.content_provider import MemoryProvider
    p = MemoryProvider()
    p.open(initial_text=text)
    return p


class TestAsciiOffsets:
    """纯 ASCII：字符偏移 = 字节偏移"""

    def test_equal_offsets(self):
        from core.search import SearchEngine, SearchOptions
        provider = _make_provider("hello world hello again")
        engine = SearchEngine(
            provider, SearchOptions(pattern="hello")
        )
        result = engine.search()
        assert result.count == 2
        for m in result.matches:
            assert m.start == m.char_start
            assert m.end == m.char_end

    def test_position_values(self):
        from core.search import SearchEngine, SearchOptions
        provider = _make_provider("hello world hello")
        engine = SearchEngine(
            provider, SearchOptions(pattern="hello")
        )
        result = engine.search()
        m0 = result.matches[0]
        assert m0.start == 0
        assert m0.end == 5
        assert m0.char_start == 0
        assert m0.char_end == 5

        m1 = result.matches[1]
        assert m1.start == 12
        assert m1.end == 17
        assert m1.char_start == 12
        assert m1.char_end == 17


class TestChineseOffsets:
    """含中文：字节偏移 > 字符偏移"""

    def test_chinese_only(self):
        from core.search import SearchEngine, SearchOptions
        # "中文测试中文测试中文"
        # 字符: 中 文 测 试 中 文 测 试 中 文 = 10 字符
        # 字节: 每个中文字符 3 字节 = 30 字节
        provider = _make_provider("中文测试中文测试中文")
        engine = SearchEngine(
            provider, SearchOptions(pattern="中文")
        )
        result = engine.search()
        assert result.count == 3

        # 第一个：字符 0-2，字节 0-6
        m0 = result.matches[0]
        assert m0.char_start == 0
        assert m0.char_end == 2
        assert m0.start == 0
        assert m0.end == 6

        # 第二个：字符 4-6，字节 12-18
        m1 = result.matches[1]
        assert m1.char_start == 4
        assert m1.char_end == 6
        assert m1.start == 12
        assert m1.end == 18

        # 第三个：字符 8-10，字节 24-30
        m2 = result.matches[2]
        assert m2.char_start == 8
        assert m2.char_end == 10
        assert m2.start == 24
        assert m2.end == 30

    def test_mixed_chinese_ascii(self):
        from core.search import SearchEngine, SearchOptions
        # "ab中文cd中文"
        # 字符: a b 中 文 c d 中 文 = 8 字符
        # 字节: 1+1 + 3+3 + 1+1 + 3+3 = 16 字节
        provider = _make_provider("ab中文cd中文")
        engine = SearchEngine(
            provider, SearchOptions(pattern="中文")
        )
        result = engine.search()
        assert result.count == 2

        # 第一个：字符 2-4，字节 2-8
        m0 = result.matches[0]
        assert m0.char_start == 2
        assert m0.char_end == 4
        assert m0.start == 2
        assert m0.end == 8

        # 第二个：字符 6-8，字节 10-16
        m1 = result.matches[1]
        assert m1.char_start == 6
        assert m1.char_end == 8
        assert m1.start == 10
        assert m1.end == 16


class TestReplace:
    """替换场景"""

    def test_replace_chinese(self):
        from core.search import SearchEngine, SearchOptions, ReplaceEngine
        provider = _make_provider("你好世界你好")
        options = SearchOptions(pattern="你好")
        engine = SearchEngine(provider, options)
        result = engine.search()
        assert result.count == 2

        # 全部替换
        replace_engine = ReplaceEngine(provider)
        count = replace_engine.replace_all(result, "HI")
        assert count == 2

        # 验证内容
        new_text = provider.read_text()
        assert new_text == "HI世界HI"

    def test_replace_mixed(self):
        from core.search import SearchEngine, SearchOptions, ReplaceEngine
        provider = _make_provider("a中文b中文c")
        options = SearchOptions(pattern="中文")
        engine = SearchEngine(provider, options)
        result = engine.search()
        assert result.count == 2

        replace_engine = ReplaceEngine(provider)
        count = replace_engine.replace_all(result, "XX")
        assert count == 2

        new_text = provider.read_text()
        assert new_text == "aXXbXXc"


class TestHighlightText:
    """highlight_matches_in_text 用字符偏移"""

    def test_highlight_chinese(self):
        from core.search import (
            SearchEngine, SearchOptions, highlight_matches_in_text
        )
        provider = _make_provider("前缀中文后缀")
        engine = SearchEngine(
            provider, SearchOptions(pattern="中文")
        )
        result = engine.search()
        assert result.count == 1

        marked = highlight_matches_in_text(
            "前缀中文后缀", result.matches, "[", "]"
        )
        assert marked == "前缀[中文]后缀"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])