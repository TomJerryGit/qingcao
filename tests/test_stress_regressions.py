# -*- coding: utf-8 -*-
"""回归测试：真实压力测试发现的两个数据/结构缺陷

## 缺陷 1：UTF-16/UTF-32 文件的 BOM 被当成正文读入

`BOMS` 把 UTF-16/32 的 BOM 映射成**裸端序编码**（`utf-16-le` 等），
这类编码不剥离 BOM，解出来第一个字符就是 `U+FEFF`。

实测：32 字符的 UTF-16LE 文件被读成 **33** 字符，首字符 `U+FEFF`。
文本看起来"没坏"，但会破坏搜索/替换/解析/行级 diff。
对比之下 UTF-8 BOM 走 `'utf-8-sig'`（自动剥离），所以这是**不对称**缺陷。

## 缺陷 2：纯 CR（老式 Mac）换行文件被算成 1 行

`Document.build_line_index()` 只认 `'\\n'`，于是
`"line1\\rline2\\rline3\\r"` 的行索引是 `[0]` → `get_line_count() == 1`。
文本没丢，但行号/行数全错 → 跳转到行、行级 diff、列编辑器、书签、
LSP 行列位置全部错位。
"""
import os
import sys
import tempfile

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _open(tmp_path, name, data, encoding=None):
    from core.document import Document
    p = tmp_path / name
    p.write_bytes(data)
    d = Document()
    d.open(str(p), encoding=encoding)
    return d


# ============================================================
# 缺陷 1：BOM 不得进入正文
# ============================================================
SAMPLE = "第一行：中文\n第二行：end\n"


@pytest.mark.parametrize("codec", ["utf-16", "utf-16-le", "utf-16-be"])
def test_utf16_bom_not_in_text(qapp, tmp_path, codec):
    """UTF-16 各种写法的 BOM 都不应出现在读回的正文里"""
    if codec == "utf-16-le":
        data = b"\xff\xfe" + SAMPLE.encode("utf-16-le")
    elif codec == "utf-16-be":
        data = b"\xfe\xff" + SAMPLE.encode("utf-16-be")
    else:
        data = SAMPLE.encode("utf-16")        # 自动带 LE BOM
    d = _open(tmp_path, "u16_%s.txt" % codec, data)
    try:
        got = d.get_text()
        assert not got.startswith("\ufeff"), (
            "读回的正文以 BOM（U+FEFF）开头 —— "
            "`decode()` 没有剥离 BOM（缺陷复发）。repr=%r" % (got[:20],)
        )
        assert got == SAMPLE, (
            "UTF-16 内容不一致：期望 %r 实际 %r"
            % (SAMPLE, got[:40])
        )
        assert len(got) == len(SAMPLE)
    finally:
        d.close()


def test_utf16_bom_reported_in_metadata(qapp, tmp_path):
    """BOM 被剥离，但元数据里必须仍记录 has_bom（保存时才知道要不要写回）"""
    data = b"\xff\xfe" + SAMPLE.encode("utf-16-le")
    d = _open(tmp_path, "u16_meta.txt", data)
    try:
        assert d.meta.has_bom is True, "has_bom 应为 True（元数据丢失）"
    finally:
        d.close()


def test_utf16_bom_file_roundtrip_bytes(qapp, tmp_path):
    """往返保存后字节应与原文件一致（BOM 不重复、不丢失）"""
    data = b"\xff\xfe" + SAMPLE.encode("utf-16-le")
    d = _open(tmp_path, "u16_rt.txt", data)
    try:
        d.mark_modified()
        out = tmp_path / "u16_rt_saved.txt"
        d.save(str(out))
        assert out.read_bytes() == data, (
            "保存后字节与原文不一致：\n"
            "  原文 %r\n  保存 %r" % (data[:12], out.read_bytes()[:12])
        )
    finally:
        d.close()


def test_utf8_bom_still_stripped(qapp, tmp_path):
    """UTF-8 BOM 的行为不能被破坏（走 utf-8-sig，本来就剥离）"""
    data = b"\xef\xbb\xbf" + SAMPLE.encode("utf-8")
    d = _open(tmp_path, "u8bom.txt", data)
    try:
        got = d.get_text()
        assert not got.startswith("\ufeff"), repr(got[:20])
        assert got == SAMPLE
    finally:
        d.close()


def test_no_bom_file_unaffected(qapp, tmp_path):
    """没有 BOM 的普通文件不受影响（防止剥 BOM 逻辑误伤正文首字符）"""
    d = _open(tmp_path, "nobom.txt", SAMPLE.encode("utf-8"))
    try:
        assert d.get_text() == SAMPLE
        assert d.meta.has_bom is False
    finally:
        d.close()


# ============================================================
# 缺陷 2：换行符 → 行索引
# ============================================================
@pytest.mark.parametrize("eol,label", [
    ("\n", "LF"),
    ("\r\n", "CRLF"),
    ("\r", "CR"),
])
def test_line_count_all_eol_styles(qapp, tmp_path, eol, label):
    """LF / CRLF / CR 三种换行的行数都必须正确"""
    text = eol.join(["line1", "line2", "line3"]) + eol
    d = _open(tmp_path, "eol_%s.txt" % label, text.encode("utf-8"))
    try:
        # 3 行内容 + 末尾一个空行起点 = 4
        assert d.get_line_count() == 4, (
            "%s 文件行数 = %d（期望 4）" % (label, d.get_line_count())
        )
    finally:
        d.close()


def test_cr_line_starts_are_correct(qapp, tmp_path):
    """纯 CR 文件的行首位置必须正确（不只是行数对）"""
    d = _open(tmp_path, "cr_starts.txt", b"aaa\rbbb\rccc\r")
    try:
        assert d.get_line_count() == 4
        assert d.get_line_text(0) == "aaa"
        assert d.get_line_text(1) == "bbb"
        assert d.get_line_text(2) == "ccc"
        assert d.get_line_text(3) == ""
    finally:
        d.close()


def test_crlf_not_double_counted(qapp, tmp_path):
    """CRLF 不能被算成两行（\r 与 \n 各断一次）—— 这是修 CR 时最易引入的回归"""
    d = _open(tmp_path, "crlf_count.txt", b"a\r\nb\r\nc\r\n")
    try:
        assert d.get_line_count() == 4, (
            "CRLF 被重复计数，行数 = %d（期望 4）" % d.get_line_count()
        )
        assert d.get_line_text(0) == "a"
        assert d.get_line_text(1) == "b"
        assert d.get_line_text(2) == "c"
    finally:
        d.close()


def test_mixed_eol_line_count(qapp, tmp_path):
    """混合换行文件也要合理（LF + CRLF + CR 混排）"""
    d = _open(tmp_path, "mixed.txt", b"a\nb\r\nc\rd")
    try:
        # a / b / c / d = 4 行，末尾无换行
        assert d.get_line_count() == 4, str(d.get_line_count())
        assert d.get_line_text(0) == "a"
        assert d.get_line_text(1) == "b"
        assert d.get_line_text(2) == "c"
        assert d.get_line_text(3) == "d"
    finally:
        d.close()


def test_line_index_does_not_change_text(qapp, tmp_path):
    """修行索引**不能改文本**（否则保存就会改写用户文件）"""
    raw = b"x\r\ny\rz\n"
    d = _open(tmp_path, "nochange.txt", raw)
    try:
        d.build_line_index()
        d.mark_modified()
        out = tmp_path / "nochange_saved.txt"
        d.save(str(out))
        assert out.read_bytes() == raw, (
            "行索引修复把文本改了：原文 %r 保存 %r"
            % (raw, out.read_bytes())
        )
    finally:
        d.close()
