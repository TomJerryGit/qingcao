# -*- coding: utf-8 -*-
"""回归测试：列编辑必须是**线性**的，不能退回 O(n²)

## 缺陷背景（真实 UI 压测发现）

原实现逐行 `SCI_INSERTTEXT`：

    n=1,000  逐条插入 0.115s   批量 setText 0.002s
    n=8,000  逐条插入 8.635s   批量 setText 0.003s

翻倍 n 约 4 倍耗时 → O(n²)。外推 10 万行 ≈ **22 分钟**。
而"在 10 万行上插入数字序列"正是列编辑的核心场景（对标 Notepad++）。

修复后实测：10 万行 **3.68s**（撤销 2.9s / 重做 2.1s，均正确）。

## 本测试的策略

不直接断言绝对耗时（机器速度差异大，会让 CI 不稳定），而是断言
**缩放比**：规模翻 4 倍时，耗时不应超过 ~8 倍。
线性算法约 4 倍，二次方算法约 16 倍 —— 两者区分度很大。
"""
import os
import sys
import time

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtGui import QFontDatabase
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    for p in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\msyh.ttc"):
        if os.path.exists(p):
            QFontDatabase.addApplicationFont(p)
    yield app


def _make_editor(tmp_path, n_rows, name):
    """构造真实 QsciScintilla + Document + EditorProxy"""
    from PyQt5.Qsci import QsciScintilla

    from core.document import Document
    from core.editor import EditorProxy

    p = tmp_path / name
    p.write_text("".join("row %07d abcdefghij\n" % k for k in range(n_rows)),
                 encoding="utf-8", newline="")
    sc = QsciScintilla()
    sc.setUtf8(True)
    doc = Document()
    doc.open(str(p))
    proxy = EditorProxy(sc, doc)
    proxy.open_file(str(p))
    return proxy


def _time_column_edit(proxy, n_rows):
    from ui.column_editor_dialog import (
        ColumnEditConfig,
        apply_column_edit,
    )

    cfg = ColumnEditConfig(text="XY", column=2, lines=list(range(n_rows)))
    t0 = time.perf_counter()
    r = apply_column_edit(proxy, cfg)
    return r, (time.perf_counter() - t0)


# ============================================================
# 1. 正确性（先确保批量算法本身对）
# ============================================================
def test_batch_column_edit_correctness(qapp, tmp_path):
    """批量插入后每行位置正确、且一次撤销能完整回退"""
    n = 500
    proxy = _make_editor(tmp_path, n, "ok.txt")
    try:
        r, _el = _time_column_edit(proxy, n)
        assert r.ok, r.reason
        assert len(r.lines) == n

        sc = proxy.sc
        assert sc.text(0).startswith("roXYw 0000000"), sc.text(0)[:20]
        assert sc.text(n // 2).startswith("roXYw %07d" % (n // 2))
        assert sc.text(n - 1).startswith("roXYw %07d" % (n - 1))

        # 一次撤销完整回退
        assert len(proxy.undo_manager.undo_stack) == 1
        proxy.undo()
        assert sc.text(0).startswith("row 0000000")
        assert sc.text(n - 1).startswith("row %07d" % (n - 1))

        # 重做恢复
        proxy.redo()
        assert sc.text(0).startswith("roXYw 0000000")
    finally:
        try:
            proxy.sc.deleteLater()
        except Exception:
            pass


def test_batch_column_edit_multibyte_positions(qapp, tmp_path):
    """含中文/emoji 的行：UTF-8 字节位置换算必须正确

    批量算法在 Python 侧按**字符**切片，而列编辑给的是**字节**位置，
    换算错了就会在中文中间插入、产生乱码。
    """
    from PyQt5.Qsci import QsciScintilla

    from core.document import Document
    from core.editor import EditorProxy
    from ui.column_editor_dialog import ColumnEditConfig, apply_column_edit

    lines = ["中文内容%03d😀abc" % k for k in range(200)]
    p = tmp_path / "mb.txt"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")

    sc = QsciScintilla()
    sc.setUtf8(True)
    doc = Document()
    doc.open(str(p))
    proxy = EditorProxy(sc, doc)
    proxy.open_file(str(p))
    try:
        cfg = ColumnEditConfig(text="|", column=6, lines=list(range(200)))
        r = apply_column_edit(proxy, cfg)
        assert r.ok, r.reason

        before_len = sum(len(ln) for ln in lines)
        # 核心断言（批量算法最容易出错的地方）：
        #   1. **绝不能出现 U+FFFD** —— 那说明插入点落在多字节字符中间
        #      （把字节偏移当字符偏移就会这样）；
        #   2. 原有的中文 / emoji 一个字都不能丢；
        #   3. 撤销必须逐行精确还原。
        for i in range(200):
            ln = sc.text(i)
            assert "\ufffd" not in ln, "第 %d 行出现替换字符: %r" % (i, ln[:40])
            assert "中文内容" in ln, "第 %d 行中文丢失: %r" % (i, ln[:40])
            assert "😀" in ln, "第 %d 行 emoji 丢失: %r" % (i, ln[:40])
            assert ln.replace("\r\n", "\n").rstrip("\n").endswith("abc"), (
                "第 %d 行尾部被破坏: %r" % (i, ln[:40])
            )
        # 每行多插入 1 个字符（200 行），而 `sc.text()` 还包含 200 个换行符。
        # 注意 `before_len` 只统计行内字符、不含 "\n"。
        n_lines = len(lines)
        expected_len = before_len + n_lines + n_lines   # 行内 + 换行 + 插入
        assert len(sc.text()) == expected_len, (
            "插入后长度 %d，期望 %d（原 %d + %d 换行 + %d 插入）"
            % (len(sc.text()), expected_len, before_len, n_lines, n_lines)
        )

        proxy.undo()
        for i in range(200):
            got = sc.text(i).replace("\r\n", "\n").rstrip("\n")
            assert got == lines[i], (
                "撤销后第 %d 行未还原: %r（期望 %r）" % (i, got[:40], lines[i][:40])
            )
    finally:
        try:
            sc.deleteLater()
        except Exception:
            pass


# ============================================================
# 2. 缩放（防 O(n²) 回归）
# ============================================================
def test_column_edit_scales_linearly(qapp, tmp_path):
    """规模翻 4 倍（1000 → 4000），耗时不应超过 8 倍

    线性算法约 4 倍；二次方算法约 16 倍。阈值 8 倍能稳定区分两者，
    同时给机器抖动留余量。
    """
    small_n = 1000
    large_n = 4000

    p1 = _make_editor(tmp_path, small_n, "s1.txt")
    try:
        _r1, t_small = _time_column_edit(p1, small_n)
    finally:
        try:
            p1.sc.deleteLater()
        except Exception:
            pass

    p2 = _make_editor(tmp_path, large_n, "s4.txt")
    try:
        _r2, t_large = _time_column_edit(p2, large_n)
    finally:
        try:
            p2.sc.deleteLater()
        except Exception:
            pass

    # 小规模可能极快（<1ms），用下限避免除零/噪声放大
    base = max(t_small, 0.002)
    ratio = t_large / base

    assert ratio < 8.0, (
        "列编辑疑似退回 O(n²)：规模 %d→%d（4 倍），耗时 %.3fs→%.3fs"
        "（%.1f 倍，阈值 8 倍）。\n"
        "修复方向：批量重建文本 + 单次 setText，而不是逐行 SCI_INSERTTEXT"
        "（见 ui/column_editor_dialog.py::_apply_inserts_to_text）。"
        % (small_n, large_n, t_small, t_large, ratio)
    )


def test_column_edit_100k_under_budget(qapp, tmp_path):
    """10 万行列编辑必须在 60s 内完成（修复前外推约 22 分钟）

    这是"可用性"底线而非性能优化目标：真实用户（对标 Notepad++）
    会在 10 万行文件上插入行号。
    """
    n = 100_000
    proxy = _make_editor(tmp_path, n, "huge.txt")
    try:
        r, elapsed = _time_column_edit(proxy, n)
        assert r.ok, r.reason
        assert len(r.lines) == n
        assert elapsed < 60.0, (
            "10 万行列编辑耗时 %.1fs（预算 60s）—— 已降级为不可用"
            % elapsed
        )
        # 抽查正确性
        assert proxy.sc.text(0).startswith("roXYw 0000000")
        assert proxy.sc.text(n - 1).startswith("roXYw %07d" % (n - 1))
    finally:
        try:
            proxy.sc.deleteLater()
        except Exception:
            pass
