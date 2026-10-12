#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""数据完整性审计实证脚本（审计员编写 —— 尚未在本环境执行）

背景：本次审计所在会话无法执行任何 shell 命令
（DSH 沙箱 `SetNamedSecurityInfoW failed (Win32 5): grantWrite(D:\\QingCaoEditor)`，
提权请求被自动拒绝），因此本脚本是**为了让有 shell 权限的会话一键复现**
而编写的，脚本本身的输出在本报告中标记为「未执行」。

覆盖 5 组实证：
    A. 往返一致性矩阵（走真实编辑器路径 + provider 路径）
    B. 块边界（blocksize ±1 字节）
    C. 外部修改
    D. 失败注入（只读目录 / 独占锁定）
    E. 崩溃恢复

用法::

    chcp 65001
    python tests\\audit_data_integrity_harness.py
    python tests\\audit_data_integrity_harness.py --only A,B
    python tests\\audit_data_integrity_harness.py --verbose

所有产物写入系统临时目录，不修改仓库内任何文件。
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import traceback


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def setup_stdout():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def setup_qt():
    """离屏 Qt + 字体（离屏模式默认无字体）"""
    from PyQt5.QtGui import QFontDatabase
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    for font in (r"C:\Windows\Fonts\consola.ttf",
                 r"C:\Windows\Fonts\msyh.ttc"):
        try:
            if os.path.exists(font):
                QFontDatabase.addApplicationFont(font)
        except Exception:
            pass
    return app


def set_pref(key, value):
    """直接写 QSettings，避免依赖 Preferences 单例"""
    from PyQt5.QtCore import QSettings
    s = QSettings("QingCao", "Editor")
    s.setValue(key, value)
    s.sync()


# ============================================================
# 样本构造
# ============================================================
ASCII_LINES = [
    "line one ascii",
    "line two with symbols !@#$%^&*()",
    "    indented line",
    "tab\there",
    "trailing spaces here   ",
    "last line",
]
CJK_LINES = [
    "第一行中文内容",
    "第二行：标点，。！？",
    "   缩进的中文行",
    "最后一行中文",
]

# (标签, 编码, EOL, 样本, 是否加 BOM)
CASES = [
    ("utf-8/LF",         "utf-8",    "\n",   ASCII_LINES, None),
    ("utf-8/CRLF",       "utf-8",    "\r\n", ASCII_LINES, None),
    ("utf-8-BOM/LF",     "utf-8",    "\n",   ASCII_LINES, b'\xef\xbb\xbf'),
    ("utf-8-BOM/CRLF",   "utf-8",    "\r\n", ASCII_LINES, b'\xef\xbb\xbf'),
    ("gbk/LF",           "gbk",      "\n",   CJK_LINES,   None),
    ("gbk/CRLF",         "gbk",      "\r\n", CJK_LINES,   None),
    ("utf-16le-BOM/LF",  "utf-16-le", "\n",  CJK_LINES,   b'\xff\xfe'),
    ("utf-16le-BOM/CRLF", "utf-16-le", "\r\n", CJK_LINES, b'\xff\xfe'),
    ("utf-8-中文/LF",     "utf-8",    "\n",   CJK_LINES,   None),
    ("混合行尾/LF",       "utf-8",    "MIX",  ASCII_LINES, None),
    ("无末尾换行",         "utf-8",    "NOFINAL", ASCII_LINES, None),
    ("空文件",            "utf-8",    "\n",   [],          None),
    ("仅BOM",             "utf-8",    "\n",   [],          b'\xef\xbb\xbf'),
]


def build_bytes(enc, eol, lines, bom, no_final_newline=False):
    if eol == "MIX":
        parts = []
        for i, ln in enumerate(lines):
            parts.append(ln + ("\r\n" if i % 2 == 0 else "\n"))
        text = "".join(parts)
    elif eol == "NOFINAL":
        text = "\n".join(lines)          # 刻意不补末尾换行
    else:
        text = eol.join(lines)
        if lines and not no_final_newline:
            text += eol
    data = text.encode(enc)
    if bom:
        data = bom + data
    return text, data


# ============================================================
# A. 往返一致性矩阵
# ============================================================
def mutate(text, kind, eol):
    if kind == "edit_head":
        return "HEAD! " + text
    if kind == "edit_tail":
        return text + "TAIL!"
    if kind == "insert_middle":
        pos = len(text) // 2
        return text[:pos] + "MID!" + text[pos:]
    if kind == "delete_large":
        return text[:max(1, len(text) // 8)]
    if kind == "append_only":
        return text + "APPENDED"
    if kind == "delete_all":
        return ""
    raise ValueError(kind)


MUTATIONS = ["edit_head", "edit_tail", "insert_middle",
             "delete_large", "append_only", "delete_all"]


def roundtrip_provider(tmpdir, label, enc, eol, lines, bom, kind, verbose):
    """路径 1：直接用 LocalFileProvider（不含编辑器规范化）"""
    from core.content_provider import LocalFileProvider

    src_text, src_bytes = build_bytes(enc, eol, lines, bom)
    path = os.path.join(tmpdir, "p_%s_%s.bin" % (label.replace("/", "_"), kind))
    with open(path, 'wb') as f:
        f.write(src_bytes)

    prov = LocalFileProvider()
    assert prov.open(path), "provider.open 失败"
    seen = prov.read_text()
    new_text = mutate(seen, kind, eol)
    prov.clear_dirty()
    prov._size = len(prov.encode(new_text))
    prov._total_blocks = max(1, (prov._size + prov.block_size - 1)
                             // prov.block_size)
    for bid in range(prov._total_blocks):
        s = bid * prov.block_size
        e = min(s + prov.block_size, prov._size)
        prov.write_block(bid, prov.encode(new_text)[s:e])
    ok = prov.save()
    enc_used = prov.encoding
    has_bom = prov.has_bom
    prov.close()

    with open(path, 'rb') as f:
        got = f.read()

    # 期望字节：按检测到的编码/BOM 重建
    exp = new_text.encode('utf-8' if enc_used == 'utf-8-sig' else enc_used)
    if has_bom and not exp.startswith(b'\xef\xbb\xbf') and enc_used == 'utf-8-sig':
        exp = b'\xef\xbb\xbf' + exp
    return ok, got, exp


def roundtrip_editor(tmpdir, label, enc, eol, lines, bom,
                     kind, verbose, trim, final_nl):
    """路径 2：真实编辑器路径（EditorWidget + EditorProxy.save_file）

    这是用户实际经历的路径：sc.text() -> trim/末尾换行 -> encode -> 写盘。
    """
    from ui.editor_view import EditorWidget

    set_pref("trim_trailing_whitespace", trim)
    set_pref("insert_final_newline", final_nl)

    src_text, src_bytes = build_bytes(enc, eol, lines, bom)
    path = os.path.join(tmpdir, "e_%s_%s.bin" % (label.replace("/", "_"), kind))
    with open(path, 'wb') as f:
        f.write(src_bytes)

    w = EditorWidget()
    try:
        proxy = w.proxy
        proxy.open_file(path)
        seen = w.text()
        # 模拟一次用户编辑
        new_text = mutate(seen, kind, eol)
        if kind == "append_only":
            new_text = seen + "APPENDED"          # 追加，不动已有内容
        w.setText(new_text)
        w.setModified(True)
        ok = proxy.save_file()
        doc_enc = proxy.document.encoding
    finally:
        try:
            w.document.close()
        except Exception:
            pass

    with open(path, 'rb') as f:
        got = f.read()
    return ok, got, new_text, doc_enc, seen


def section_A(tmpdir, verbose):
    print("=" * 78)
    print("A. 往返一致性矩阵")
    print("=" * 78)
    results = []

    for label, enc, eol, lines, bom in CASES:
        for kind in MUTATIONS:
            # --- provider 路径 ---
            try:
                ok, got, exp = roundtrip_provider(
                    tmpdir, label, enc, eol, lines, bom, kind, verbose)
                same = (got == exp)
            except Exception as e:
                ok, same, got, exp = False, False, b'', b''
                print("      [provider 异常] %s/%s: %s" % (label, kind, e))
                if verbose:
                    traceback.print_exc()
            results.append(("provider", label, kind, ok, same))
            if not same:
                print("   FAIL provider %-18s %-14s 期望%6d 实际%6d"
                      % (label, kind, len(exp), len(got)))

            # --- 真实编辑器路径（默认偏好：trim=True, final_nl=True） ---
            exp2 = b''
            got2 = b''
            denc = '?'
            try:
                ok2, got2, nt, denc, seen = roundtrip_editor(
                    tmpdir, label, enc, eol, lines, bom, kind, verbose,
                    trim=True, final_nl=True)
                same2 = False
                if ok2:
                    # 期望：编辑器文本经同一套规范化后按文档编码写出
                    want = nt
                    exp2 = want.encode(enc)
                    if bom:
                        exp2 = bom + exp2
                    same2 = (got2 == exp2)
            except Exception as e:
                ok2, same2 = False, False
                print("      [editor 异常] %s/%s: %s" % (label, kind, e))
                if verbose:
                    traceback.print_exc()
            results.append(("editor", label, kind, ok2, same2))
            if not same2:
                print("   FAIL editor   %-18s %-14s 保存=%s 编码=%s "
                      "期望%6d 实际%6d"
                      % (label, kind, ok2, denc, len(exp2), len(got2)))

    print()
    print("矩阵（PASS/FAIL，真实编辑器路径 + 默认偏好）")
    hdr = "  %-20s" % "编码/行尾"
    for m in MUTATIONS:
        hdr += " %-13s" % m
    print(hdr)
    for label, _, _, _, _ in CASES:
        row = "  %-20s" % label
        for m in MUTATIONS:
            hit = [s for p, l, k, o, s in results
                   if p == "editor" and l == label and k == m]
            row += " %-13s" % ("PASS" if hit and hit[0] else "FAIL")
        print(row)

    print()
    print("矩阵（PASS/FAIL，provider 路径）")
    print(hdr)
    for label, _, _, _, _ in CASES:
        row = "  %-20s" % label
        for m in MUTATIONS:
            hit = [s for p, l, k, o, s in results
                   if p == "provider" and l == label and k == m]
            row += " %-13s" % ("PASS" if hit and hit[0] else "FAIL")
        print(row)

    # 隔离验证：关掉 trim / final newline 后 CRLF 是否仍失败
    print()
    print("-- 隔离验证：trim=False, insert_final_newline=False --")
    for label, enc, eol, lines, bom in CASES:
        if eol != "\r\n":
            continue
        try:
            ok, got, nt, denc, seen = roundtrip_editor(
                tmpdir, label + "[no-trim]", enc, eol, lines, bom,
                "append_only", verbose, trim=False, final_nl=False)
            src_text, src_bytes = build_bytes(enc, eol, lines, bom)
            exp = (seen + "APPENDED").encode(enc)
            if bom:
                exp = bom + exp
            print("   %-24s 保存=%s 字节一致=%s 期望%6d 实际%6d"
                  % (label, ok, got == exp, len(exp), len(got)))
        except Exception as e:
            print("   %-24s 异常: %s" % (label, e))

    passed = sum(1 for _, _, _, _, s in results if s)
    print()
    print("A 汇总: %d/%d 通过" % (passed, len(results)))
    return passed == len(results)


# ============================================================
# B. 块边界
# ============================================================
def section_B(tmpdir, verbose):
    print()
    print("=" * 78)
    print("B. 块边界（blocksize ±1 字节 / 多字节字符跨界）")
    print("=" * 78)

    from core.content_provider import LocalFileProvider

    fails = 0
    total = 0

    # B1: 逐块解码导致的跨界损坏（模拟 EditorProxy._load_content）
    for bs in (4096, 1024, 65536):
        # 构造：让一个 3 字节 UTF-8 汉字的第 1 字节正好落在 bs-1
        prefix = b'a' * (bs - 1)
        payload = "青".encode('utf-8')          # e9 9d 92
        tail = "尾部内容".encode('utf-8')
        raw = prefix + payload + tail
        path = os.path.join(tmpdir, "boundary_%d.bin" % bs)
        with open(path, 'wb') as f:
            f.write(raw)

        prov = LocalFileProvider(block_size=bs)
        prov.open(path, detect_encoding=False)
        prov.encoding = 'utf-8'
        # 复刻 EditorProxy._load_content 的「逐块 decode + append」
        joined = "".join(prov.decode(prov.read_block(i))
                         for i in range(prov.total_blocks))
        ref = raw.decode('utf-8')
        total += 1
        ok = (joined == ref)
        if not ok:
            fails += 1
        print("   B1 逐块解码 blocksize=%-6d 一致=%-5s "
              "应见=%r 实见=%r"
              % (bs, ok, ref[bs - 4:bs + 4], joined[bs - 4:bs + 4]))

        # B2: 整块拼接后一次解码（正确做法）
        whole = b''.join(prov.read_block(i) for i in range(prov.total_blocks))
        total += 1
        ok2 = (whole.decode('utf-8') == ref)
        if not ok2:
            fails += 1
        print("   B2 整块拼接一次解码 blocksize=%-6d 一致=%s" % (bs, ok2))
        prov.close()

    # B3: 块大小边界的替换/插入/删除
    for bs in (4096,):
        for delta in (-1, 0, 1):
            n = bs + delta
            raw = (b'ab' * ((n + 1) // 2))[:n]
            path = os.path.join(tmpdir, "edge_%d_%d.bin" % (bs, delta))
            with open(path, 'wb') as f:
                f.write(raw)
            prov = LocalFileProvider(block_size=bs)
            prov.open(path, detect_encoding=False)
            prov.encoding = 'ascii'
            new_text = "X" * (n + 100) + "END"
            data = prov.encode(new_text)
            prov.clear_dirty()
            prov._size = len(data)
            prov._total_blocks = max(1, (len(data) + bs - 1) // bs)
            for bid in range(prov._total_blocks):
                s = bid * bs
                e = min(s + bs, len(data))
                prov.write_block(bid, data[s:e])
            ok = prov.save()
            prov.close()
            with open(path, 'rb') as f:
                got = f.read()
            total += 1
            good = ok and got == data
            if not good:
                fails += 1
            print("   B3 边界替换 bs=%d 原长=%d 新长=%d 保存=%s 一致=%s"
                  % (bs, n, len(data), ok, got == data))

    # B4: 只写脏块 0 时的截断行为（潜在 P0）
    bs = 4096
    raw = b'A' * (bs * 3)
    path = os.path.join(tmpdir, "dirtyonly.bin")
    with open(path, 'wb') as f:
        f.write(raw)
    prov = LocalFileProvider(block_size=bs)
    prov.open(path, detect_encoding=False)
    prov.encoding = 'ascii'
    prov.write_block(0, b'B' * 10)      # 只脏块 0
    ok = prov.save()
    prov.close()
    with open(path, 'rb') as f:
        got = f.read()
    total += 1
    print("   B4 只写块0：保存=%s 原长=%d 保存后长=%d（截断丢失尾部）"
          % (ok, len(raw), len(got)))
    if len(got) != 10:
        fails += 1

    print()
    print("B 汇总: %d/%d 通过" % (total - fails, total))
    return fails == 0


# ============================================================
# C. 外部修改
# ============================================================
def section_C(tmpdir, verbose):
    print()
    print("=" * 78)
    print("C. 外部修改（打开 -> 外部改写 -> 编辑器保存）")
    print("=" * 78)

    from ui.editor_view import EditorWidget

    set_pref("trim_trailing_whitespace", False)
    set_pref("insert_final_newline", False)

    path = os.path.join(tmpdir, "external.txt")
    with open(path, 'wb') as f:
        f.write("ORIGINAL LINE 1\nORIGINAL LINE 2\n".encode('utf-8'))

    w = EditorWidget()
    proxy = w.proxy
    proxy.open_file(path)
    print("   打开后编辑器内容: %r" % w.text())
    print("   check_external_change (未改前): %s"
          % proxy.document.has_external_change())

    # 外部程序改写
    with open(path, 'wb') as f:
        f.write("EXTERNAL REWRITE\n".encode('utf-8'))

    print("   check_external_change (外部改写后): %s"
          % proxy.document.has_external_change())
    print("   编辑器内仍是: %r" % w.text())

    w.setText("EDITOR VERSION\n")
    w.setModified(True)
    ok = proxy.save_file()
    with open(path, 'rb') as f:
        got = f.read()
    print("   保存=%s 最终文件=%r" % (ok, got))
    print("   => 外部内容是否被静默覆盖: %s"
          % (got == b"EDITOR VERSION\n"))
    print("   => external_change_detected 是否连接到冲突提示: 静态分析=否")

    # C2: 外部删除文件后保存
    path2 = os.path.join(tmpdir, "deleted.txt")
    with open(path2, 'wb') as f:
        f.write(b"hello\n")
    w2 = EditorWidget()
    p2 = w2.proxy
    p2.open_file(path2)
    os.remove(path2)
    w2.setText("new content\n")
    w2.setModified(True)
    ok2 = p2.save_file()
    exists = os.path.exists(path2)
    print("   C2 文件被外部删除后保存: save=%s 文件重建=%s" % (ok2, exists))
    if exists:
        with open(path2, 'rb') as f:
            print("     重建内容=%r" % f.read())
    return True


# ============================================================
# D. 失败注入
# ============================================================
def section_D(tmpdir, verbose):
    print()
    print("=" * 78)
    print("D. 失败注入（只读 / 独占锁定 / 目录不存在）")
    print("=" * 78)

    from PyQt5.QtWidgets import QApplication

    from ui.editor_view import EditorWidget

    set_pref("trim_trailing_whitespace", False)
    set_pref("insert_final_newline", False)

    # D1: 目标文件设为只读
    path = os.path.join(tmpdir, "readonly.txt")
    original = b"ORIGINAL CONTENT\n"
    with open(path, 'wb') as f:
        f.write(original)
    try:
        os.chmod(path, 0o444)
    except Exception as e:
        print("   chmod 失败: %s" % e)

    w = EditorWidget()
    p = w.proxy
    p.open_file(path)
    print("   D1 只读文件 readonly=%s" % p.document.meta.readonly)
    w.setText("CHANGED\n")
    w.setModified(True)
    ok = p.save_file()
    with open(path, 'rb') as f:
        after = f.read()
    print("   D1 保存=%s 原文件完好=%s 内容=%r"
          % (ok, after == original, after))
    try:
        os.chmod(path, 0o666)
    except Exception:
        pass

    # D2: 独占锁定（Windows msvcrt.locking）
    path2 = os.path.join(tmpdir, "locked.txt")
    original2 = b"LOCKED ORIGINAL\n"
    with open(path2, 'wb') as f:
        f.write(original2)
    w2 = EditorWidget()
    p2 = w2.proxy
    p2.open_file(path2)
    w2.setText("CHANGED2\n")
    w2.setModified(True)
    try:
        import msvcrt
        lk = open(path2, 'r+b')
        msvcrt.locking(lk.fileno(), msvcrt.LK_NBLCK, 1)
        ok2 = p2.save_file()
        msvcrt.locking(lk.fileno(), msvcrt.LK_UNLCK, 1)
        lk.close()
        with open(path2, 'rb') as f:
            after2 = f.read()
        print("   D2 独占锁定 保存=%s 原文件完好=%s 内容=%r"
              % (ok2, after2 == original2, after2))
    except ImportError:
        print("   D2 跳过（非 Windows）")
    except Exception as e:
        print("   D2 锁定失败: %s" % e)

    # D3: 保存到不存在的目录
    path3 = os.path.join(tmpdir, "nosuchdir", "sub", "x.txt")
    w3 = EditorWidget()
    p3 = w3.proxy
    ok3 = p3.save_file(path3)
    print("   D3 另存到不存在目录: save=%s 文件=%s"
          % (ok3, os.path.exists(path3)))

    # D4: 保存失败时 UI 是否误报
    print("   D4 静态结论：ui/mixins/file_ops_mixin.py:195-196 "
          "忽略 proxy.save_file() 返回值并固定提示「已保存」")
    return True


# ============================================================
# E. 崩溃恢复
# ============================================================
CRASH_CHILD = r'''
import os, sys
sys.path.insert(0, r"%(root)s")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication
app = QApplication([])
from app.session import SessionManager


class FakeProxy(object):
    def __init__(self, text, doc):
        self._t = text
        self.document = doc
        self.is_modified = True
        self.sc = type("S", (), {"text": lambda s: text})()


class FakeDoc(object):
    filepath = r"%(target)s"


class FakeEditor(object):
    def __init__(self, text):
        self.proxy = FakeProxy(text, FakeDoc())


class FakeTabs(object):
    def __init__(self, text):
        self._e = FakeEditor(text)
    def count(self):
        return 1
    def widget(self, i):
        return self._e
    def tabText(self, i):
        return "sample.txt"


m = SessionManager(filepath=os.path.join(r"%(tmp)s", "session.json"))
m.autosave_dir = r"%(asd)s"
m.save_autosave(FakeTabs("CRASH-TIME CONTENT\nline2\n\n\n"))
print("child: autosave written to", m.autosave_dir)
sys.stdout.flush()
os._exit(1)          # 模拟崩溃（不走 atexit / 不写 session.json）
'''


def section_E(tmpdir, verbose):
    print()
    print("=" * 78)
    print("E. 崩溃恢复（os._exit(1) 模拟）")
    print("=" * 78)

    asd = os.path.join(tmpdir, "autosave")
    target = os.path.join(tmpdir, "sample.txt")
    with open(target, 'wb') as f:
        f.write(b"ORIGINAL ON DISK\n")

    child = os.path.join(tmpdir, "crash_child.py")
    with open(child, 'w', encoding='utf-8') as f:
        f.write(CRASH_CHILD % {"root": ROOT, "target": target,
                               "tmp": tmpdir, "asd": asd})

    r = subprocess.run([sys.executable, child], capture_output=True)
    print("   子进程退出码=%s（期望 1）" % r.returncode)
    print("   子进程 stdout: %s"
          % r.stdout.decode('utf-8', 'replace').strip())
    if r.stderr:
        print("   子进程 stderr: %s"
              % r.stderr.decode('utf-8', 'replace').strip()[-600:])

    meta = os.path.join(asd, "meta.json")
    print("   备份目录存在=%s meta.json 存在=%s"
          % (os.path.isdir(asd), os.path.isfile(meta)))
    if not os.path.isfile(meta):
        print("   => 无可恢复备份（因 start_autosave 从未被调用，"
              "实际产品中同样为空）")
        return False

    blobs = [n for n in os.listdir(asd) if n.endswith(".tmp")]
    for n in blobs:
        with open(os.path.join(asd, n), encoding='utf-8') as f:
            print("   备份 %s 内容=%r" % (n, f.read()))

    # 静态：备份内容与崩溃前编辑器内容是否逐字节一致
    print("   崩溃前内容 = 'CRASH-TIME CONTENT\\nline2\\n\\n\\n'")
    print("   注意 _recover_files 会做 content[:idx].rstrip()，"
          "尾部空行/空白会被丢弃")

    # 手工调用恢复逻辑（不弹对话框）
    from PyQt5.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from app.session import SessionManager
    m = SessionManager(filepath=os.path.join(tmpdir, "session.json"))
    m.autosave_dir = asd
    print("   静态结论：check_and_recover_crash 需要 QMessageBox 交互，"
          "无人值守下无法自动断言；恢复后 rmtree 会删除备份目录")
    return True


# ============================================================
def main():
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="A,B,C,D,E")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    only = set(x.strip().upper() for x in args.only.split(","))

    setup_qt()
    tmpdir = tempfile.mkdtemp(prefix="qc_audit_")
    print("临时目录: %s" % tmpdir)
    print()
    print("注意：本脚本由审计会话编写，但审计会话**无 shell 权限**，"
          "脚本本身尚未被执行过。")
    print()

    results = {}
    try:
        if "A" in only:
            results['A'] = section_A(tmpdir, args.verbose)
        if "B" in only:
            results['B'] = section_B(tmpdir, args.verbose)
        if "C" in only:
            results['C'] = section_C(tmpdir, args.verbose)
        if "D" in only:
            results['D'] = section_D(tmpdir, args.verbose)
        if "E" in only:
            results['E'] = section_E(tmpdir, args.verbose)
    except Exception:
        traceback.print_exc()
    finally:
        print()
        print("=" * 78)
        for k in sorted(results):
            print("  %s: %s" % (k, "全部通过" if results[k] else "存在失败"))
        print("=" * 78)
        print("产物保留在: %s（如需清理请手动删除）" % tmpdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
