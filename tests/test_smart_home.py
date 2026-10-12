"""editor_view._smart_home 字节偏移计算（P1-B4）"""


def _calc_indent_bytes(line_text):
    """复刻 _smart_home 里的计算逻辑"""
    stripped = line_text.lstrip()
    indent = len(line_text) - len(stripped)
    return indent, len(line_text[:indent].encode('utf-8'))


class TestIndentBytes:
    def test_ascii_spaces(self):
        """ASCII 空格：字符数 = 字节数"""
        indent, indent_bytes = _calc_indent_bytes("    def foo")
        assert indent == 4
        assert indent_bytes == 4

    def test_tabs(self):
        """Tab：1 字符 = 1 字节"""
        indent, indent_bytes = _calc_indent_bytes("\t\tdef foo")
        assert indent == 2
        assert indent_bytes == 2

    def test_full_width_space(self):
        """全角空格：1 字符 = 3 字节"""
        indent, indent_bytes = _calc_indent_bytes("\u3000\u3000def foo")
        assert indent == 2
        assert indent_bytes == 6  # 关键：不是 2

    def test_mixed(self):
        """混合空格 + 全角"""
        indent, indent_bytes = _calc_indent_bytes("  \u3000def foo")
        assert indent == 3
        assert indent_bytes == 2 + 3  # 2 ASCII + 3 (全角)

    def test_no_indent(self):
        """无缩进"""
        indent, indent_bytes = _calc_indent_bytes("def foo")
        assert indent == 0
        assert indent_bytes == 0