"""outline_panel._compute_end_lines 边界测试（P1-B2）"""
import pytest


class TestComputeEndLines:
    def _make_panel(self):
        """构造一个未初始化的 OutlinePanel 实例"""
        try:
            from ui.outline_panel import OutlinePanel
        except ImportError:
            pytest.skip("outline_panel 不可用")

        # __new__ 绕过 __init__，避免构造整个控件树
        return OutlinePanel.__new__(OutlinePanel)

    def test_simple_sequence(self):
        """无嵌套：每个符号 end_line = 下一行 - 1"""
        try:
            from ui.outline_panel import SymbolNode
        except ImportError:
            pytest.skip("SymbolNode 不可用")

        panel = self._make_panel()
        symbols = [
            SymbolNode(name="a", type="function", line=0, indent=0),
            SymbolNode(name="b", type="function", line=10, indent=0),
            SymbolNode(name="c", type="function", line=20, indent=0),
        ]
        panel._compute_end_lines(symbols)

        assert symbols[0].end_line == 9
        assert symbols[1].end_line == 19
        assert symbols[2].end_line == 20  # 最后一个：max_line

    def test_nested(self):
        """有嵌套：父节点延伸到子节点之后"""
        try:
            from ui.outline_panel import SymbolNode
        except ImportError:
            pytest.skip("SymbolNode 不可用")

        panel = self._make_panel()
        symbols = [
            SymbolNode(name="cls", type="class", line=0, indent=0),
            SymbolNode(name="m1", type="method", line=5, indent=4),
            SymbolNode(name="m2", type="method", line=10, indent=4),
            SymbolNode(name="func", type="function", line=20, indent=0),
        ]
        panel._compute_end_lines(symbols)

        # cls 应该延伸到 line 19（func 的前一行）
        assert symbols[0].end_line == 19
        # m1 到 line 9
        assert symbols[1].end_line == 9
        # m2 到 line 19
        assert symbols[2].end_line == 19
        # func 是最后一个
        assert symbols[3].end_line == 20

    def test_empty(self):
        """空列表不崩"""
        panel = self._make_panel()
        panel._compute_end_lines([])  # 不崩即可

    def test_single(self):
        """单个符号"""
        try:
            from ui.outline_panel import SymbolNode
        except ImportError:
            pytest.skip("SymbolNode 不可用")

        panel = self._make_panel()
        symbols = [
            SymbolNode(name="only", type="function", line=5, indent=0),
        ]
        panel._compute_end_lines(symbols)
        assert symbols[0].end_line == 5