# -*- coding: utf-8 -*-
"""探针：复现/否认"跨 64KiB 块边界多字节字符损坏"（P0-A）

构造一个 UTF-8 汉字正好跨在块边界上的文件，按块独立解码再拼接，
与整文件解码的结果比较。
"""
import io
import os
import sys
import tempfile


sys.path.insert(0, r"D:\QingCaoEditor")
os.chdir(r"D:\QingCaoEditor")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.content_provider import LocalFileProvider  # noqa: E402


BS = 64 * 1024
han = "测".encode("utf-8")          # 3 字节
print("  块大小 =", BS, " 单字字节 =", han.hex())

# 让最后一个字节落在块边界之后（即汉字跨越边界）
for offset in (0, 1, 2):
    pad = b"a" * (BS - offset)
    raw = pad + han * 3 + b"b" * 10
    fd, path = tempfile.mkstemp(suffix=".txt")
    os.write(fd, raw)
    os.close(fd)
    try:
        prov = LocalFileProvider()
        prov.open(path)
        ref = raw.decode("utf-8")
        joined = "".join(
            prov.decode(prov.read_block(i)) for i in range(prov.total_blocks)
        )
        # 整体 read_text
        whole = prov.read_text()
        ok_joined = joined == ref
        ok_whole = whole == ref
        print("  偏移%+d | 块数=%d | 逐块拼接==原文: %-5s | read_text==原文: %-5s"
              % (-offset, prov.total_blocks, ok_joined, ok_whole))
        if not ok_joined:
            d = next(i for i, (a, b) in enumerate(zip(joined, ref)) if a != b)
            print("        首个差异位置 %d: 逐块得到 %r, 原文 %r"
                  % (d, joined[d], ref[d]))
        if not ok_whole:
            d = next(i for i, (a, b) in enumerate(zip(whole, ref)) if a != b)
            print("        read_text 差异位置 %d: %r vs %r"
                  % (d, whole[d], ref[d]))
        prov.close()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
