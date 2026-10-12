#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""数据完整性往返矩阵（Lead 实证脚本，已按真实 API 修正）

验证「打开 → 编辑 → 保存」后文件字节是否与期望**精确一致**。
本项目出现过 P0 级数据损坏（保存不截断导致尾部残留旧字节），
因此对每种编码/行尾组合做字节级断言。

真实 API（已核实）：
    LocalFileProvider(block_size=...)   # 构造不接受路径
    provider.open(path, encoding=None)  # 打开
    provider.read_text()
    provider.save() / provider.save(filepath)
    provider.close()

用法::

    python tools/audit_data_roundtrip.py
    python tools/audit_data_roundtrip.py --verbose
"""
import os
import shutil
import sys
import tempfile
import traceback


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

# 每种编码用各自可编码的样本（GBK 无法表示 emoji，故分开构造）
ASCII_LINES = [
    "line one ascii",
    "third line with symbols !@#$%^&*()",
    "tab\there",
    "quotes \"double\" and 'single'",
    "backslash \\ and percent %",
    "    indented line",
    "last line no trailing newline",
]
CJK_LINES = [
    "line one ascii",
    "第二行中文内容",
    "第三行：标点，。！？",
    "tab\there",
    "quotes \"double\" and 'single'",
    "    indented line",
    "最后一行无换行结尾",
]

# (标签, 编码, 是否CRLF, 用哪套样本, 是否有BOM)
CASES = [
    ("utf-8",            "utf-8",    False, ASCII_LINES, False),
    ("utf-8 + CRLF",     "utf-8",    True,  ASCII_LINES, False),
    ("utf-8-sig",        "utf-8",    False, ASCII_LINES, True),
    ("utf-16",           "utf-16",   False, ASCII_LINES, False),
    ("gbk",              "gbk",      False, CJK_LINES,   False),
    ("gbk + CRLF",       "gbk",      True,  CJK_LINES,   False),
    ("utf-8 中文",        "utf-8",    False, CJK_LINES,   False),
    ("utf-8 中文 + CRLF", "utf-8",    True,  CJK_LINES,   False),
]


def build_bytes(encoding, crlf, lines, bom):
    nl = "\r\n" if crlf else "\n"
    text = nl.join(lines)
    data = text.encode(encoding)
    if bom:
        data = b'\xef\xbb\xbf' + data
    return data


def decode_sample(raw, encoding, bom):
    """把样本字节解码成编辑器会看到的文本（去 BOM）"""
    data = raw
    enc = encoding
    if bom:
        data = data[3:]
        enc = 'utf-8'
    return data.decode(enc)


def run_case(tmpdir, label, encoding, crlf, lines, bom, mutate, verbose=False):
    raw = build_bytes(encoding, crlf, lines, bom)
    safe = label.replace(' ', '_').replace('+', 'p')
    path = os.path.join(tmpdir, "sample_%s.txt" % safe)
    with open(path, 'wb') as f:
        f.write(raw)

    from core.content_provider import LocalFileProvider

    provider = LocalFileProvider()
    if not provider.open(path):
        return False, "%s / %s: provider.open() 失败" % (label, mutate.__name__)

    nl = "\r\n" if crlf else "\n"
    text = provider.read_text()
    expected_text = mutate(text, nl)
    expected_bytes = expected_text.encode(encoding)
    if bom:
        expected_bytes = b'\xef\xbb\xbf' + expected_bytes

    # 走真实编辑+保存路径
    provider.write_text(expected_text)
    ok_save = provider.save()
    provider.close()

    with open(path, 'rb') as f:
        got = f.read()

    if got == expected_bytes:
        if verbose:
            print("      ok    %s" % mutate.__name__)
        return True, ""

    mismatch_at = next((i for i in range(min(len(got), len(expected_bytes)))
                        if got[i] != expected_bytes[i]),
                       min(len(got), len(expected_bytes)))
    detail = (
        "      保存%s | 期望 %d 字节, 实际 %d 字节, 首个差异 @%d\n"
        "      期望尾部: %r\n"
        "      实际尾部: %r"
        % ("成功" if ok_save else "**失败**", len(expected_bytes), len(got),
           mismatch_at, expected_bytes[-36:], got[-36:])
    )
    return False, detail


def m_edit_head(text, nl):
    lines = text.split(nl)
    lines[0] = "EDITED HEAD " + lines[0]
    return nl.join(lines)


def m_edit_tail(text, nl):
    lines = text.split(nl)
    lines[-1] = lines[-1] + " EDITED TAIL"
    return nl.join(lines)


def m_insert_middle(text, nl):
    lines = text.split(nl)
    lines.insert(len(lines) // 2, "INSERTED MIDDLE LINE")
    return nl.join(lines)


def m_delete_large(text, nl):
    """删除大段——旧版会残留尾部字节的典型场景"""
    return nl.join(text.split(nl)[:2])


def m_append_only(text, nl):
    return text + nl + "APPENDED LINE"


def m_clear_all(text, nl):
    return "x"


MUTATIONS = [m_edit_head, m_edit_tail, m_insert_middle,
             m_delete_large, m_append_only, m_clear_all]


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])

    print("=" * 78)
    print("数据完整性往返矩阵：provider.open -> 编辑 -> save -> 字节比对")
    print("=" * 78)
    print()

    tmpdir = tempfile.mkdtemp(prefix="qc_roundtrip_")
    results, failures = [], []

    for label, enc, crlf, lines, bom in CASES:
        print("  [%s]" % label)
        for mut in MUTATIONS:
            try:
                ok, detail = run_case(tmpdir, label, enc, crlf, lines, bom, mut)
            except Exception as e:
                ok = False
                detail = ("      异常 %s: %s\n%s"
                          % (type(e).__name__, e, traceback.format_exc(limit=4)))
            results.append((label, mut.__name__, ok))
            print("      %-5s %s" % ("ok" if ok else "FAIL", mut.__name__))
            if not ok:
                failures.append((label, mut.__name__, detail))
        print()

    total = len(results)
    passed = sum(1 for _, _, ok in results if ok)

    print("=" * 78)
    print("汇总: %d/%d 通过, %d 失败" % (passed, total, total - passed))
    print("=" * 78)

    if failures:
        print()
        print("失败详情:")
        for label, name, detail in failures:
            print("  --- %s / %s ---" % (label, name))
            print(detail)
            print()

    print()
    print("矩阵（行=编码, 列=编辑操作）:")
    hdr = "  %-20s" % "编码"
    for m in MUTATIONS:
        hdr += " %-13s" % m.__name__[2:]
    print(hdr)
    for label, _, _, _, _ in CASES:
        row = "  %-20s" % label
        for m in MUTATIONS:
            hit = [ok for l, n, ok in results if l == label and n == m.__name__]
            row += " %-13s" % ("PASS" if hit and hit[0] else "FAIL")
        print(row)

    shutil.rmtree(tmpdir, ignore_errors=True)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
