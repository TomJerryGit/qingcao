#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
诊断 coverage 报"couldn't-parse"的文件
============================================================
逐字节分析文件，定位语法/编码/截断问题

用法：
    python tools/diagnose_broken.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def print_header(t):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


def print_ok(m):
    print("  [OK]   " + m)


def print_warn(m):
    print("  [WARN] " + m)


def print_fail(m):
    print("  [FAIL] " + m)


def print_info(m):
    print("  [INFO] " + m)


def analyze_file(rel_path):
    """分析单个文件"""
    print_header(f"诊断: {rel_path}")

    path = ROOT / rel_path
    if not path.exists():
        print_fail(f"文件不存在")
        return

    # 文件大小
    size = path.stat().st_size
    print_info(f"文件大小: {size} 字节")

    # 读取字节
    try:
        with open(path, 'rb') as f:
            raw = f.read()
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return

    # 编码检测
    print_info("尝试用不同编码解码...")
    encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb18030', 'latin-1']
    decode_ok = None
    decode_error = None

    for enc in encodings:
        try:
            text = raw.decode(enc)
            print_ok(f"  {enc}: 成功（{len(text)} 字符）")
            if decode_ok is None:
                decode_ok = enc
        except UnicodeDecodeError as e:
            print_warn(f"  {enc}: 失败 - {str(e)[:60]}")
            if decode_error is None:
                decode_error = (enc, e)

    # 显示错误位置上下文
    if decode_error:
        enc, e = decode_error
        pos = e.start
        print()
        print_info(f"UTF-8 解码失败位置: 字节 {pos}")
        print_info("上下文（前 40 字节 / 后 40 字节）:")
        start = max(0, pos - 40)
        end = min(len(raw), pos + 40)
        context = raw[start:end]
        print(f"      {context!r}")
        # 显示十六进制
        hex_str = ' '.join(f'{b:02x}' for b in context)
        print(f"      HEX: {hex_str}")

    # 编译测试
    print()
    print_info("尝试编译（compile 检测语法错误）...")
    try:
        if decode_ok:
            src = raw.decode(decode_ok)
            compile(src, str(path), 'exec')
            print_ok(f"编译成功")
        else:
            print_fail("无法解码，跳过编译")
            return
    except SyntaxError as e:
        print_fail(f"语法错误:")
        print(f"         行 {e.lineno}: {e.msg}")
        if e.text:
            print(f"         代码: {e.text.rstrip()}")
        # 显示错误行上下文
        if decode_ok:
            src = raw.decode(decode_ok)
            lines = src.split('\n')
            n = e.lineno or 1
            for i in range(max(0, n - 3), min(len(lines), n + 2)):
                marker = ">>>" if i + 1 == n else "   "
                print(f"      {marker} {i + 1:4d}: {repr(lines[i])[:100]}")
        return
    except Exception as e:
        print_fail(f"编译异常: {type(e).__name__}: {e}")
        return

    # 显示文件末尾 200 字节
    print()
    print_info("文件末尾 200 字节（检查是否截断）:")
    tail = raw[-200:]
    try:
        tail_text = tail.decode('utf-8', errors='replace')
        for line in tail_text.split('\n')[-8:]:
            print(f"      {repr(line)[:100]}")
    except Exception:
        print(f"      {tail!r}")


def main():
    print()
    print("#" * 60)
    print("#  文件诊断")
    print("#" * 60)
    print(f"  项目根目录: {ROOT}")

    targets = [
        "core/code_templates.py",
        "ui/help_browser.py",
    ]

    for rel in targets:
        analyze_file(rel)

    print()
    print("=" * 60)
    print("诊断完成")
    print("=" * 60)

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"\n脚本异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)