# -*- coding: utf-8 -*-
"""SymbolParser._compute_end_lines 边界测试（P1-B2）

注意：_compute_end_lines 是 SymbolParser 的方法，不是
OutlinePanel 的。OutlinePanel 内部通过
self.parser._build_hierarchy() → self._compute_end_lines()
间接使用它。
"""
import pytest


def _make_parser():
    try:
        from ui.outline_panel import SymbolParser
    except ImportError:
        pytest.skip("SymbolParser 不可用")
    return SymbolParser()


def _make_node(name, type_, line, indent):
    try:
        from ui.outline_panel import SymbolNode
    except ImportError:
        pytest.skip("SymbolNode 不可用")
    return SymbolNode(name=name, type=type_, line=line, indent=indent)


class TestComputeEndLines:

    def test_simple_sequence(self):
        parser = _make_parser()
        symbols = [
            _make_node("a", "function", 0, 0),
            _make_node("b", "function", 10, 0),
            _make_node("c", "function", 20, 0),
        ]
        parser._compute_end_lines(symbols)
        assert symbols[0].end_line == 9
        assert symbols[1].end_line == 19
        assert symbols[2].end_line == 20

    def test_nested(self):
        parser = _make_parser()
        symbols = [
            _make_node("cls", "class", 0, 0),
            _make_node("m1", "method", 5, 4),
            _make_node("m2", "method", 10, 4),
            _make_node("func", "function", 20, 0),
        ]
        parser._compute_end_lines(symbols)
        assert symbols[0].end_line == 19
        assert symbols[1].end_line == 9
        assert symbols[2].end_line == 19
        assert symbols[3].end_line == 20

    def test_empty(self):
        parser = _make_parser()
        parser._compute_end_lines([])   # 不崩即可

    def test_single(self):
        parser = _make_parser()
        symbols = [_make_node("only", "function", 5, 0)]
        parser._compute_end_lines(symbols)
        assert symbols[0].end_line == 5
