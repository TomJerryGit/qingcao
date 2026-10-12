# -*- coding: utf-8 -*-
"""A6 回归测试：搜索必须复用行索引，不能退化为 O(n²)

修复前的严重缺陷
----------------
`SearchEngine._get_line_text()` 每次调用都执行

    text = self.provider.read_text()
    lines = text.splitlines()

即**读取并切分整个文件**，而它被 `_build_match` 在**每个匹配**上
调用一次 → 复杂度 O(匹配数 × 文件大小) ≈ O(N²)。

实测（重复 50 字符文本，搜索 "quick"）：

    16 KB   0.031 s     297 匹配
    64 KB   0.426 s    1191 匹配
    256 KB  9.799 s    4766 匹配
    1 MB    > 25 s 未完成
    10 MB   > 15 min 无输出

本文件用"多匹配 + 中等体积"的负载来卡住这个复杂度：
若行索引被重新构建（或每匹配重读全文），耗时会在 10 s 量级；
复用索引后应在 1 s 内完成。阈值取得较宽（1.5 s），只用来
拦截**数量级**级别的退化，不追求精确基准。

另外还拦截一个本次实际踩过的坑：把行索引"合并"时若写成
`return index[:-1]`，每次调用都会拷贝整张表（实测 183 µs/次，
1 MB 即 3.5 s）。因此同时断言"每次搜索只构建一次索引"。
"""
import os
import time

import pytest


LINE = "the quick brown fox jumps over the lazy dog 0123456789\n"


def _write_dup_file(path, target_bytes):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(LINE * max(1, target_bytes // len(LINE)))


@pytest.fixture()
def count_index_builds(monkeypatch):
    """统计行索引被构建的次数

    返回一个 dict：{'n': 构建次数}
    """
    from core import search as search_mod

    counter = {"n": 0}
    original = search_mod.SearchEngine._ensure_line_index

    def counting(self):
        # 只在"真的要构建"时计数（未缓存）
        if self._line_offsets_full is None:
            counter["n"] += 1
        return original(self)

    monkeypatch.setattr(
        search_mod.SearchEngine, "_ensure_line_index", counting
    )
    return counter


class TestLineTextCorrectness:
    """行文本与行列位置必须正确（性能优化不能改变语义）"""

    def test_line_and_col_and_line_text(self, qapp):
        from core.content_provider import MemoryProvider
        from core.search import SearchEngine, SearchOptions

        text = "first line\nhello world\nhello again\n中文行 hello\nlast"
        prov = MemoryProvider()
        prov.open(initial_text=text)
        result = SearchEngine(
            prov, SearchOptions(pattern="hello")
        ).search()

        assert result.count == 3
        got = [(m.line, m.col, m.line_text) for m in result.matches]
        assert got == [
            (2, 0, "hello world"),
            (3, 0, "hello again"),
            (4, 4, "中文行 hello"),   # 中文各占 1 字符 -> col=4
        ]

    def test_get_line_text_matches_splitlines(self, qapp):
        """逐行核对：应与 splitlines 的语义一致（不含换行符）"""
        from core.content_provider import MemoryProvider
        from core.search import SearchEngine, SearchOptions

        text = "a\n\nb\nc\r\nd"
        prov = MemoryProvider()
        prov.open(initial_text=text)
        engine = SearchEngine(prov, SearchOptions(pattern="a"))

        expected = text.replace("\r\n", "\n").split("\n")
        for i, want in enumerate(expected, start=1):
            assert engine._get_line_text(i) == want, (
                "第 %d 行不一致" % i
            )

    def test_out_of_range_returns_empty(self, qapp):
        from core.content_provider import MemoryProvider
        from core.search import SearchEngine, SearchOptions

        prov = MemoryProvider()
        prov.open(initial_text="only line")
        engine = SearchEngine(prov, SearchOptions(pattern="only"))

        assert engine._get_line_text(0) == ""
        assert engine._get_line_text(99) == ""
        assert engine._get_line_text(-1) == ""

    def test_crlf_line_text_has_no_trailing_cr(self, qapp):
        from core.content_provider import MemoryProvider
        from core.search import SearchEngine, SearchOptions

        prov = MemoryProvider()
        prov.open(initial_text="aa\r\nbb hello\r\ncc")
        result = SearchEngine(
            prov, SearchOptions(pattern="hello")
        ).search()

        assert result.matches[0].line_text == "bb hello"
        assert "\r" not in result.matches[0].line_text


class TestNoQuadraticBehavior:
    """多匹配场景不能退化为 O(n²)"""

    def test_many_matches_finishes_quickly(self, qapp, tmp_path):
        """约 256 KB、约 5 000 个匹配：必须远快于二次复杂度

        修复前该用例需 ~10 s（256 KB 实测 9.8 s / 4766 匹配）；
        修复后为 O(N)。
        """
        from core.content_provider import LocalFileProvider
        from core.search import SearchEngine, SearchOptions

        path = tmp_path / "many.txt"
        _write_dup_file(str(path), 256 * 1024)

        prov = LocalFileProvider()
        try:
            prov.open(str(path))
            start = time.perf_counter()
            result = SearchEngine(
                prov, SearchOptions(pattern="quick")
            ).search()
            elapsed = time.perf_counter() - start
        finally:
            prov.close()

        assert result.error is None
        assert result.count > 3000, "匹配数太少，不构成压力负载"
        # 修复前 ~10 s；这里给 1.5 s 的宽裕上限，只拦截数量级退化
        assert elapsed < 1.5, (
            "搜索耗时 %.2f s（%d 个匹配）——疑似退回 O(n²)："
            "每个匹配都在重读/重切整个文件" % (elapsed, result.count)
        )

    def test_line_index_built_only_once_per_search(
        self, qapp, tmp_path, count_index_builds
    ):
        """整次搜索只应构建一次行索引

        拦截"每次匹配都重建索引"，以及"合并索引时每次拷贝整表"
        （`return index[:-1]`）这类退化。
        """
        from core.content_provider import LocalFileProvider
        from core.search import SearchEngine, SearchOptions

        path = tmp_path / "once.txt"
        _write_dup_file(str(path), 64 * 1024)

        prov = LocalFileProvider()
        try:
            prov.open(str(path))
            result = SearchEngine(
                prov, SearchOptions(pattern="quick")
            ).search()
        finally:
            prov.close()

        assert result.count > 500
        assert count_index_builds["n"] == 1, (
            "行索引被构建了 %d 次（应为 1 次）"
            % count_index_builds["n"]
        )

    def test_line_index_not_copied_per_match(
        self, qapp, tmp_path, count_index_builds
    ):
        """定位单个匹配的开销不应随文件行数线性增长

        这是"合并索引"时踩过的坑：`_build_line_index()` 若返回
        `index[:-1]`，每次调用都拷贝约 19 000 个元素的列表
        （实测 183 µs/次）。这里用同一方法的多次调用总耗时来卡住它。
        """
        from core.content_provider import LocalFileProvider
        from core.search import SearchEngine, SearchOptions

        path = tmp_path / "big.txt"
        _write_dup_file(str(path), 1024 * 1024)

        prov = LocalFileProvider()
        try:
            prov.open(str(path))
            engine = SearchEngine(prov, SearchOptions(pattern="quick"))

            n = 2000
            start = time.perf_counter()
            for i in range(n):
                engine._position_to_line_col(i * 50)
            per_call = (time.perf_counter() - start) / n
        finally:
            prov.close()

        # 修好后约 10 µs/次；带整表拷贝时约 190 µs/次
        assert per_call < 80e-6, (
            "_position_to_line_col 每次 %.1f µs，疑似在拷贝整张行索引表"
            % (per_call * 1e6)
        )


class TestLargeFilePracticality:
    """实际可用性：1 MB 文件必须秒级完成"""

    def test_one_mb_file_is_practical(self, qapp, tmp_path):
        """修复前 1 MB 需要 >25 s（实测未完成）"""
        from core.content_provider import LocalFileProvider
        from core.search import SearchEngine, SearchOptions

        path = tmp_path / "one_mb.txt"
        _write_dup_file(str(path), 1024 * 1024)

        prov = LocalFileProvider()
        try:
            prov.open(str(path))
            start = time.perf_counter()
            result = SearchEngine(
                prov, SearchOptions(pattern="quick")
            ).search()
            elapsed = time.perf_counter() - start
        finally:
            prov.close()

        assert result.count > 15000
        assert elapsed < 5.0, (
            "1 MB 搜索耗时 %.2f s（修复前 >25 s）" % elapsed
        )
