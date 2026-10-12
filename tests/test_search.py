# -*- coding: utf-8 -*-
"""搜索引擎测试"""
import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class TestSearchOptions(unittest.TestCase):
    def test_build_pattern_escape(self):
        from core.search import SearchOptions
        opts = SearchOptions(pattern="a.b", escape_pattern=True)
        self.assertIn(r'\.', opts.build_pattern())

    def test_build_pattern_whole_word(self):
        from core.search import SearchOptions
        opts = SearchOptions(pattern="test", whole_word=True)
        self.assertIn(r'\b', opts.build_pattern())


class TestSearchEngine(unittest.TestCase):
    def test_simple_search(self):
        from core.content_provider import MemoryProvider
        from core.search import SearchEngine, SearchOptions

        provider = MemoryProvider()
        provider.open(initial_text="hello world\nhello again\n")

        opts = SearchOptions(pattern="hello")
        engine = SearchEngine(provider, opts)
        result = engine.search()

        self.assertEqual(result.count, 2)


class TestQuickSearch(unittest.TestCase):
    def test_quick_search(self):
        from core.content_provider import MemoryProvider
        from core.search import quick_search

        provider = MemoryProvider()
        provider.open(initial_text="test test test")

        result = quick_search(provider, "test")
        self.assertGreaterEqual(result.count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)