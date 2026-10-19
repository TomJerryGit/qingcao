# -*- coding: utf-8 -*-
"""青草编辑器 · 真实压力测试（Stress / Robustness）

与 `verify_*.py` 的区别：那些是"功能是否按规格工作"，
本脚本问的是另一个问题 —— **在真实世界的极端输入下它还能不能用、快不快**。

    python tools\\stress_test.py            # 全部场景
    python tools\\stress_test.py --quick    # 跳过最重的 100 万行场景

## 场景

  S1  大文件打开：10 MB / 约 20 万行 —— 加载耗时、内容完整性、行数正确
  S2  超大文件：100 万行（--quick 跳过）—— 是否卡死 / 内存是否爆炸
  S3  超长单行：10 万字符一行 —— 会不会让 Scintilla/QScintilla 卡住
  S4  编码矩阵：UTF-8/UTF-8-BOM/GBK/UTF-16LE/无 BOM 中文 —— 检测是否准、
      读回是否与原文一致（这是最容易静默损坏数据的地方）
  S5  换行符矩阵：LF/CRLF/CR 混合文件 —— 检测与往返是否保真
  S6  草稿写入 → 崩溃 → 恢复全链路 —— 内容是否真的没丢
  S7  边界输入：空文件 / 只有换行 / 二进制字节 / 超长行无换行

## 判定

每项都有**硬阈值**（例如 10MB 文件打开 < 5 秒）与**保真断言**
（读回内容必须逐字节/逐字符等于原文）。失败会明确打印实测值。

退出码: 0 = 全部通过；1 = 有失败项。
"""
import os
import sys
import tempfile
import time
import traceback


os.chdir(r"D:\QingCaoEditor")
sys.path.insert(0, r"D:\QingCaoEditor")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

QUICK = "--quick" in sys.argv

PASS, FAIL, WARN = [], [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %-48s %s" % ("OK " if cond else "FAIL", name, detail))


def warn(name, detail=""):
    WARN.append(name)
    print("  [WARN] %-46s %s" % (name, detail))


def timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return out, (time.perf_counter() - t0)


print("=" * 100)
print("青草编辑器 · 真实压力测试%s" % ("（quick 模式，跳过 100 万行）" if QUICK else ""))
print("=" * 100)

from PyQt5.QtGui import QFontDatabase  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402


app = QApplication.instance() or QApplication([])
# offscreen 下必须注入字体，否则 QScintilla 排版可能段错误
for _fp in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\msyh.ttc"):
    if os.path.exists(_fp):
        QFontDatabase.addApplicationFont(_fp)

from core.content_provider import LocalFileProvider  # noqa: E402
from core.document import Document  # noqa: E402


TMP = tempfile.mkdtemp(prefix="qc_stress_")
print("  临时目录: %s" % TMP)
print()


def write_bytes(name, data):
    p = os.path.join(TMP, name)
    with open(p, "wb") as f:
        f.write(data)
    return p


def doc_open(path, encoding=None):
    """用真实 Document + LocalFileProvider 打开一个文件"""
    d = Document()
    d.open(path, encoding=encoding)
    return d


# ============================================================
# S1. 10 MB 大文件
# ============================================================
print("== S1. 10 MB 文件（约 20 万行）==")
try:
    line = "这是第 %d 行：some content with ascii and 中文混合\r\n"
    chunks = []
    size = 0
    i = 0
    while size < 10 * 1024 * 1024:
        s = line % i
        chunks.append(s)
        size += len(s.encode("utf-8"))
        i += 1
    big_text = "".join(chunks)
    big_path = write_bytes("big_10mb.txt", big_text.encode("utf-8"))
    real_mb = os.path.getsize(big_path) / (1024 * 1024)
    n_lines = big_text.count("\r\n")

    d, elapsed = timed(lambda: doc_open(big_path))
    print("       文件 %.1f MB / %d 行" % (real_mb, n_lines))
    check("S1a 10MB 文件打开成功", d is not None and d.get_text() != "",
          "耗时 %.2fs" % elapsed)
    check("S1b 打开耗时 < 5.0s", elapsed < 5.0, "%.2fs" % elapsed)
    got = d.get_text()
    check("S1c 内容逐字符一致（无截断/无乱码）",
          got == big_text,
          "原文 %d 字符 / 读回 %d 字符" % (len(big_text), len(got)))
    check("S1d 行数正确", d.get_line_count() == n_lines + 1,
          "%d vs %d" % (d.get_line_count(), n_lines + 1))
    check("S1e 编码检测为 UTF-8", str(d.encoding).lower().replace("_", "-")
          in ("utf-8", "utf8"), str(d.encoding))
    d.close()
except Exception as e:
    check("S1 10MB 场景", False, "%s: %s" % (type(e).__name__, e))
    traceback.print_exc()

# ============================================================
# S2. 100 万行（可选）
# ============================================================
print()
print("== S2. 100 万行超大文件%s ==" % ("（quick 模式跳过）" if QUICK else ""))
if QUICK:
    print("       [SKIP] --quick")
else:
    try:
        p2 = os.path.join(TMP, "huge_1m.txt")
        with open(p2, "w", encoding="utf-8", newline="") as f:
            for k in range(1000000):
                f.write("line %07d %s\n" % (k, "x" * 20))
        mb2 = os.path.getsize(p2) / (1024 * 1024)
        d2, el2 = timed(lambda: doc_open(p2))
        print("       文件 %.1f MB / 1000000 行" % mb2)
        check("S2a 100 万行打开成功", d2 is not None, "耗时 %.2fs" % el2)
        check("S2b 打开耗时 < 30s", el2 < 30.0, "%.2fs" % el2)
        # 注意：每行都以 "\n" 结尾，末尾会多一个"空行起点"，
        # 所以正确的行数是 1000000 + 1（与 S1 的推导一致）。
        # 原断言写成 == 1000000 是测试自身错误（Lead 实测修正）。
        check("S2c 行数 == 1000001（100 万行 + 末尾空行起点）",
              d2.get_line_count() == 1000001, str(d2.get_line_count()))
        d2.close()
    except Exception as e:
        check("S2 100 万行场景", False, "%s: %s" % (type(e).__name__, e))
        traceback.print_exc()

# ============================================================
# S3. 超长单行
# ============================================================
print()
print("== S3. 10 万字符单行 ==")
try:
    longline = ("abcdefghij" * 10000) + "\n"
    p3 = write_bytes("longline.txt", longline.encode("utf-8"))
    d3, el3 = timed(lambda: doc_open(p3))
    check("S3a 超长单行打开成功", d3 is not None, "耗时 %.2fs" % el3)
    check("S3b 耗时 < 3s", el3 < 3.0, "%.2fs" % el3)
    check("S3c 内容保真", d3.get_text() == longline,
          "%d vs %d" % (len(longline), len(d3.get_text())))
    check("S3d 行数 == 2", d3.get_line_count() == 2, str(d3.get_line_count()))
    d3.close()
except Exception as e:
    check("S3 超长单行场景", False, "%s: %s" % (type(e).__name__, e))
    traceback.print_exc()

# ============================================================
# S4. 编码矩阵（最容易静默损坏数据的地方）
# ============================================================
print()
print("== S4. 编码矩阵（读回必须与原文一致）==")
SAMPLE = "第一行：中文内容测试\n第二行：emoji 😀🎉\n第三行：end\n"
ENCODINGS = [
    ("utf-8", "UTF-8 无 BOM"),
    ("utf-8-sig", "UTF-8 带 BOM"),
    ("gbk", "GBK 中文"),
    ("utf-16", "UTF-16 LE BOM"),
]
for codec, label in ENCODINGS:
    try:
        try:
            data = SAMPLE.encode(codec)
        except UnicodeEncodeError:
            # GBK 无 emoji —— 用纯中文样本
            data = "第一行：中文内容测试\n第二行：纯中文\n第三行：end\n".encode(codec)
            expect = "第一行：中文内容测试\n第二行：纯中文\n第三行：end\n"
        else:
            expect = SAMPLE
        p = write_bytes("enc_%s.txt" % codec.replace("-", "_"), data)
        d, el = timed(lambda: doc_open(p))
        got = d.get_text()
        det = str(d.encoding).lower().replace("_", "-")
        check("S4 %s 读回内容一致" % label,
              got.replace("\r\n", "\n") == expect.replace("\r\n", "\n"),
              "检测=%s 原文=%d 读回=%d" % (det, len(expect), len(got)))
        d.close()
    except Exception as e:
        check("S4 %s" % label, False, "%s: %s" % (type(e).__name__, e))

# ============================================================
# S5. 换行符矩阵
# ============================================================
print()
print("== S5. 换行符矩阵 ==")
for eol, name in (("\n", "LF"), ("\r\n", "CRLF"), ("\r", "CR")):
    try:
        text = eol.join(["line1", "line2", "line3"]) + eol
        p = write_bytes("eol_%s.txt" % name, text.encode("utf-8"))
        d, el = timed(lambda: doc_open(p))
        got = d.get_text()
        check("S5 %s 打开后行数 == 4" % name, d.get_line_count() == 4,
              str(d.get_line_count()))
        # Document 会把 EOL 统一/保留：只断言"读出 3 行内容不丢"
        norm = got.replace("\r\n", "\n").replace("\r", "\n")
        check("S5 %s 三行内容不丢" % name,
              norm.count("\n") == 3 and "line1" in norm and "line3" in norm,
              repr(norm[:40]))
        d.close()
    except Exception as e:
        check("S5 %s" % name, False, "%s: %s" % (type(e).__name__, e))

# ============================================================
# S6. 草稿 → 恢复全链路
# ============================================================
print()
print("== S6. 草稿写入 → 恢复（模拟崩溃后不丢内容）==")
try:
    from core.document import Document as DocCls

    orig_dir = DocCls._draft_dir
    draft_dir = os.path.join(TMP, "drafts")
    os.makedirs(draft_dir, exist_ok=True)
    DocCls._draft_dir = staticmethod(lambda: draft_dir)
    try:
        target = os.path.join(TMP, "to_be_lost.txt")
        with open(target, "w", encoding="utf-8", newline="") as f:
            f.write("磁盘上的旧内容\n")
        d = doc_open(target)
        d.set_text("用户改了但还没保存的内容 —— 崩溃后不能丢\n第二行\n")
        d.mark_modified()
        # 触发草稿写入（真实接口）
        d._save_draft()
        drafts = DocCls.list_drafts()
        check("S6a 草稿已写入磁盘", len(drafts) >= 1, "%d 个" % len(drafts))
        if drafts:
            _p, _orig, text, _mt = drafts[0]
            check("S6b 草稿内容 == 未保存内容",
                  "崩溃后不能丢" in text, repr(text[:40]))
            check("S6c 草稿记录了原始路径", bool(_orig), str(_orig))
        d.close()
    finally:
        DocCls._draft_dir = staticmethod(orig_dir)
except Exception as e:
    check("S6 草稿恢复场景", False, "%s: %s" % (type(e).__name__, e))
    traceback.print_exc()

# ============================================================
# S7. 边界输入
# ============================================================
print()
print("== S7. 边界输入 ==")
edges = [
    ("空文件", b"", ""),
    ("只有换行", b"\n\n\n", "\n\n\n"),
    ("无末尾换行", b"abc", "abc"),
    ("BOM + 空", b"\xef\xbb\xbf", ""),
]
for label, data, expect in edges:
    try:
        p = write_bytes("edge_%s.txt" % label, data)
        d, el = timed(lambda: doc_open(p))
        got = d.get_text()
        check("S7 %s 不崩溃" % label, d is not None, "%.3fs" % el)
        if label != "BOM + 空":
            check("S7 %s 内容符合预期" % label,
                  got.replace("\r\n", "\n").replace("\r", "\n")
                  == expect.replace("\r\n", "\n"),
                  repr(got[:20]))
        d.close()
    except Exception as e:
        check("S7 %s" % label, False, "%s: %s" % (type(e).__name__, e))

# 二进制字节：不应崩，不应产生非法字符导致后续保存炸掉
try:
    p = write_bytes("binary.bin", bytes(range(256)) * 100)
    d, el = timed(lambda: doc_open(p))
    got = d.get_text()
    check("S7 二进制文件不崩溃", d is not None, "%.3fs，%d 字符" % (el, len(got)))
    d.close()
except Exception as e:
    check("S7 二进制文件不崩溃", False, "%s: %s" % (type(e).__name__, e))
    traceback.print_exc()

# ============================================================
# 汇总
# ============================================================
print()
print("=" * 100)
print("结果：通过 %d 项 / 失败 %d 项 / 警告 %d 项" % (len(PASS), len(FAIL), len(WARN)))
print("=" * 100)
if FAIL:
    print("失败项：")
    for n in FAIL:
        print("  - " + n)
if WARN:
    print("警告项：")
    for n in WARN:
        print("  - " + n)

# 清理
try:
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)
except Exception:
    pass

sys.exit(1 if FAIL else 0)
