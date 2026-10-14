# -*- coding: utf-8 -*-
"""跨块边界与编码探测的穷举验证（P0-A / P0-A'）

覆盖：
  * 1~4 字节 UTF-8 字符（含中文、emoji）落在块边界每一个偏移上
  * ASCII 前缀 + 后置非 ASCII（chardet 误判 ascii 的经典场景）
  * 多块文件（>2 块）跨多个边界
  * 编码回环：read_text() -> encode() 必须逐字节还原原文件
  * 单字节编码（latin-1）与 GBK 不应被边界逻辑破坏
"""
import os
import sys
import tempfile


sys.path.insert(0, r"D:\QingCaoEditor")
os.chdir(r"D:\QingCaoEditor")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.content_provider import LocalFileProvider  # noqa: E402


BS = 64 * 1024
fails = []
total = 0


def roundtrip(label, raw, expect_enc=None):
    global total
    total += 1
    fd, path = tempfile.mkstemp(suffix=".bin")
    os.write(fd, raw)
    os.close(fd)
    try:
        p = LocalFileProvider()
        p.open(path)
        try:
            ref = raw.decode("utf-8")
        except UnicodeDecodeError:
            ref = None
        joined = b"".join(p.read_block(i) for i in range(p.total_blocks))
        whole_raw = p.read_all()
        text = p.read_text()
        enc_back = p.encode(text)
        ok = (
            joined == raw
            and whole_raw == raw
            and (ref is None or text == ref)
            and enc_back == raw
        )
        if expect_enc is not None and p._encoding != expect_enc:
            ok = False
        if not ok:
            fails.append((label, p._encoding, len(joined) == len(raw),
                          whole_raw == raw, enc_back == raw))
        p.close()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


print("=" * 72)
print("块边界穷举（1~4 字节字符 × 每个偏移）")
print("=" * 72)
CHARS = {
    "1B-ascii": b"Z",
    "2B-latin": "\u00e9".encode(),          # é  -> c3 a9
    "3B-han": "测".encode(),                 # 测 -> e6 b5 8b
    "4B-emoji": "\U0001F600".encode(),       # 😀 -> f0 9f 98 80
}
for name, enc in CHARS.items():
    for offset in range(0, len(enc) + 2):
        raw = b"a" * (BS - offset) + enc * 2 + b"b" * 8
        # 纯 ASCII 文件被判为 ascii 是**正确**行为，
        # 只有含多字节字符时才要求判为 utf-8
        want = "ascii" if enc.isascii() else "utf-8"
        roundtrip("%s offset=%d" % (name, offset), raw, want)
print("  已测 %d 个用例，失败 %d" % (total, len(fails)))

print()
print("=" * 72)
print("ASCII 前缀 + 后置非 ASCII（chardet 误判 ascii）")
print("=" * 72)
for prefix in (0, 100, 4000, 4096, 4097, 8000, BS, BS + 100):
    raw = b"a" * prefix + "中文测试内容".encode() * 3
    roundtrip("ascii前缀=%d" % prefix, raw, "utf-8")
print("  累计 %d 个用例，失败 %d" % (total, len(fails)))

print()
print("=" * 72)
print("多块文件（跨多个边界）")
print("=" * 72)
for blocks in (2, 3, 5):
    raw = ("行内容abc中文\n".encode() * 8000)[: (BS * blocks - 1)]
    roundtrip("多块 n=%d" % blocks, raw, "utf-8")
print("  累计 %d 个用例，失败 %d" % (total, len(fails)))

print()
print("=" * 72)
print("单字节编码不应被破坏（latin-1 / GBK）")
print("=" * 72)
for off in (0, 1, 2):
    raw = b"\xe9" * (BS - off) + b"tail"       # latin-1 的 é
    roundtrip("latin1 offset=%d" % off, raw)
gbk = ("中文测试".encode("gbk")) * 20000
roundtrip("gbk 大文件", gbk)

print()
print("=" * 72)
print("结果")
print("=" * 72)
print("  总用例 = %d" % total)
print("  失败   = %d" % len(fails))
for f in fails[:20]:
    print("    FAIL %-28s enc=%-8s len_ok=%s raw_ok=%s rt_ok=%s" % f)
if not fails:
    print("  ✅ 全部通过")
sys.exit(1 if fails else 0)
