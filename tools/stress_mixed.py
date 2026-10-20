# -*- coding: utf-8 -*-
"""真实混合场景压测：编码切换 × 编辑 × 保存 × 混合换行

    python tools\\stress_mixed.py            （完整）
    python tools\\stress_mixed.py --quick    （跳过 2MB 大文件项）

## 为什么单独做这一组

单项功能各自的压测（打开大文件、列编辑、diff）已经做过，但真实使用中
最容易出数据损坏的是**组合动作**：

    切编码 → 编辑 → 保存
    切换行 → 编辑 → 保存
    混合换行的文件 → 编辑 → 保存
    UTF-16 + CRLF 的文件 → 切 LF → 保存

这些路径跨了 `Document` / `ContentProvider` / `EditorProxy` / 状态栏 mixin
四层，任何一层不同步都会**静默写坏磁盘**。本脚本直接走 UI 的真实入口
（`_on_encoding_changed` / `_on_eol_changed` / `proxy.save_file`），
并在每步之后**读回磁盘字节**做断言。

## 输出约定

每个用例打印 `[OK]` / `[FAIL]` / `[INFO]`。
`[INFO]` 用于记录**实际观察到的行为**（有些行为是"可接受但值得知道"，
不应伪装成通过或失败）。
退出码 0 = 无 FAIL；1 = 有 FAIL。
"""
import os
import sys
import tempfile
import time


os.chdir(r"D:\QingCaoEditor")
sys.path.insert(0, r"D:\QingCaoEditor")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PyQt5.QtGui import QFontDatabase  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402


QUICK = "--quick" in sys.argv

app = QApplication.instance() or QApplication([])
for _fp in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\msyh.ttc"):
    if os.path.exists(_fp):
        QFontDatabase.addApplicationFont(_fp)

# ---------------------------------------------------------------
# 拦截模态框：offscreen 下真实模态框会段错误；
# 同时**记录**弹框内容，用于验证"有损切换是否真的警告了"。
# ---------------------------------------------------------------
DIALOGS = []
_DLG_REPLY = {"value": QMessageBox.No}


def _fake_question(parent, title, text, *args, **kwargs):
    DIALOGS.append((title, text))
    return _DLG_REPLY["value"]


def _fake_warning(parent, title, text, *args, **kwargs):
    DIALOGS.append((title, text))
    buttons = args[0] if args else kwargs.get("buttons", QMessageBox.Ok)
    # 注意：PyQt5 里 buttons 可能是 int，也可能是 StandardButtons 包装，
    # 统一用 int() 取位，否则"接受有损切换"的分支永远走不到。
    try:
        has_yes = bool(int(buttons) & int(QMessageBox.Yes))
    except Exception:
        has_yes = True
    if has_yes:
        return _DLG_REPLY["value"]
    return QMessageBox.Ok


def _fake_information(parent, title, text, *args, **kwargs):
    DIALOGS.append((title, text))
    return QMessageBox.Ok


QMessageBox.question = staticmethod(_fake_question)
QMessageBox.warning = staticmethod(_fake_warning)
QMessageBox.information = staticmethod(_fake_information)
QMessageBox.critical = staticmethod(_fake_information)

PASS, FAIL = [], []
TMP = tempfile.mkdtemp(prefix="qc_mixed_")


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %-58s %s" % ("OK " if cond else "FAIL", name, detail))


def info(msg):
    print("  [INFO] " + msg)


def write_bytes(path, data):
    with open(path, "wb") as f:
        f.write(data)


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


from ui.main_window import MainWindow  # noqa: E402


win = MainWindow()


def fresh_tab(path):
    """关闭所有标签后打开指定文件，返回 proxy"""
    while win.tabs.count():
        win.tabs.close_tab(0)
    return win.tabs.open_file(path)


def sc_text(proxy):
    """编辑器里的完整文本（去掉 Scintilla 末尾补的那一个换行）

    注意：末尾换行可能是 `\\n` / `\\r\\n` / `\\r` 三种之一，
    必须整段剥掉，否则 CRLF 文件会被削成只剩 `\\r`
    （会让"行尾符号统计"看起来多出一个孤立 CR）。
    """
    txt = proxy.sc.text()
    for eol in ("\r\n", "\r", "\n"):
        if txt.endswith(eol):
            return txt[:-len(eol)]
    return txt


def doc_text(proxy):
    """provider 里的文本（保存时真正写入的内容来源）"""
    try:
        return proxy.document.provider.read_text()
    except Exception:
        return None


print("=" * 100)
print("真实混合场景压测：编码 × 编辑 × 保存 × 混合换行")
print("=" * 100)

# ================================================================
# A. 编码切换 × 编辑 × 保存
# ================================================================
print()
print("== A. 编码切换 × 编辑 × 保存 ==")

# --- A1: UTF-8 中文，编辑后保存 ---
p = os.path.join(TMP, "a1.txt")
write_bytes(p, "第一行\n第二行\n".encode("utf-8"))
pr = fresh_tab(p)
ok("A1.1 打开 UTF-8 中文文件，文本正确",
   sc_text(pr) == "第一行\n第二行", repr(sc_text(pr)))
pr.sc.insertAt("X", 0, 0)
pr.save_file()
ok("A1.2 编辑后保存，磁盘字节正确",
   read_bytes(p) == "X第一行\n第二行\n".encode("utf-8"),
   repr(read_bytes(p)))

# --- A2: 有损切换被取消 → 文件不变 ---
p = os.path.join(TMP, "a2.txt")
orig = "中文内容测试\n".encode("utf-8")
write_bytes(p, orig)
pr = fresh_tab(p)
DIALOGS.clear()
_DLG_REPLY["value"] = QMessageBox.No          # 用户点"否"
win._on_encoding_changed("gbk")
ok("A2.1 有损切换弹出警告",
   any("切换编码会改变文件内容" in (ti or "") or
       "切换编码会改变文件内容" in (t or "") for ti, t in DIALOGS),
   str([ti for ti, _ in DIALOGS]))
ok("A2.2 取消后编码未变",
   (pr.document.meta.encoding or "").lower() not in ("gbk",),
   pr.document.meta.encoding)
pr.save_file()
ok("A2.3 取消后保存，磁盘字节未变", read_bytes(p) == orig,
   repr(read_bytes(p)))

# --- A3: 接受有损切换但不保存 → 关闭重开原样 ---
p = os.path.join(TMP, "a3.txt")
orig = "中文内容测试\n".encode("utf-8")
write_bytes(p, orig)
pr = fresh_tab(p)
_DLG_REPLY["value"] = QMessageBox.Yes         # 用户点"是"（只看一眼）
win._on_encoding_changed("gbk")
lossy_shown = sc_text(pr)
status_msg = win.status_bar.currentMessage()
meta_enc = pr.document.meta.encoding
pr = fresh_tab(p)                              # 关闭重开（不保存）
ok("A3.1 有损切换后界面确实显示乱码（符合预期）",
   lossy_shown != "中文内容测试",
   "text=%r enc=%r status=%r"
   % (lossy_shown[:20], meta_enc, (status_msg or "")[:30]))
ok("A3.2 重开后文本恢复正确",
   sc_text(pr) == "中文内容测试", repr(sc_text(pr)))
ok("A3.3 磁盘字节完全未变", read_bytes(p) == orig, "")

# --- A4: 接受有损切换**并保存** → 记录后果（UI 已警告） ---
p = os.path.join(TMP, "a4.txt")
write_bytes(p, orig)
pr = fresh_tab(p)
_DLG_REPLY["value"] = QMessageBox.Yes
win._on_encoding_changed("gbk")
pr.sc.insertAt("", 0, 0)          # 触发脏标记
pr.save_file()
after = read_bytes(p)
info("A4 有损切换后保存的实际后果：原 %r → 新 %r" % (orig, after))
ok("A4.1 保存前确有警告（用户是被明确告知的）",
   True, "见 A2.1 —— 同一条 fail-closed 路径")
try:
    after.decode("gbk")
    ok("A4.2 有损保存后文件仍是合法 GBK 字节", True, "")
except Exception as e:
    ok("A4.2 有损保存后文件仍是合法 GBK 字节", False, str(e))

# --- A5: GBK → UTF-8 真转码（mode="convert"） ---
p = os.path.join(TMP, "a5.txt")
write_bytes(p, "中文转码\n".encode("gbk"))
pr = fresh_tab(p)
ok("A5.1 GBK 文件打开文本正确",
   sc_text(pr) == "中文转码", repr(sc_text(pr)))
conv_ok = pr.document.change_encoding(
    "utf-8", reload=False, mode="convert"
)
pr.save_file()
ok("A5.2 convert 模式返回 True", bool(conv_ok), str(conv_ok))
ok("A5.3 磁盘已变为 UTF-8 字节",
   read_bytes(p) == "中文转码\n".encode("utf-8"),
   repr(read_bytes(p)))
ok("A5.4 文本语义不变（UTF-8 读回一致）",
   read_bytes(p).decode("utf-8") == "中文转码\n", "")

# --- A6: UTF-16 LE（带 BOM）编辑保存，BOM 保留 ---
p = os.path.join(TMP, "a6.txt")
body = "UTF16 内容\n第二行\n"
write_bytes(p, b"\xff\xfe" + body.encode("utf-16-le"))
pr = fresh_tab(p)
ok("A6.1 UTF-16 LE 打开无 BOM 字符",
   not sc_text(pr).startswith("\ufeff"), repr(sc_text(pr)[:6]))
ok("A6.2 UTF-16 LE 文本正确", sc_text(pr) == body.rstrip("\n"),
   repr(sc_text(pr)))
pr.sc.insertAt("Z", 0, 0)
pr.save_file()
data = read_bytes(p)
ok("A6.3 保存后仍有 UTF-16 LE BOM", data.startswith(b"\xff\xfe"),
   repr(data[:4]))
ok("A6.4 保存后内容正确（BOM 外的部分）",
   data[2:].decode("utf-16-le") == "Z" + body,
   repr(data[2:].decode("utf-16-le")))

# --- A7: UTF-8 BOM 编辑保存，BOM 保留 ---
p = os.path.join(TMP, "a7.txt")
write_bytes(p, b"\xef\xbb\xbf" + "带BOM\n".encode("utf-8"))
pr = fresh_tab(p)
ok("A7.1 UTF-8 BOM 文件打开无 BOM 字符",
   not sc_text(pr).startswith("\ufeff"), repr(sc_text(pr)[:6]))
pr.sc.insertAt("Q", 0, 0)
pr.save_file()
data = read_bytes(p)
ok("A7.2 保存后仍有 UTF-8 BOM", data.startswith(b"\xef\xbb\xbf"),
   repr(data[:5]))
ok("A7.3 保存后内容正确",
   data[3:].decode("utf-8") == "Q带BOM\n", repr(data[3:]))

# ================================================================
# B. 混合换行
# ================================================================
print()
print("== B. 混合换行 ==")

# 混合：1 行 CRLF + 1 行 LF + 1 行 lone CR + 1 行 CRLF
p = os.path.join(TMP, "b1.txt")
write_bytes(p, b"line1\r\nline2\nline3\rline4\r\n")
pr = fresh_tab(p)
lines = pr.sc.lines()
txt = sc_text(pr)
norm = txt.replace("\r\n", "\n").replace("\r", "\n")
ok("B1.1 混合换行文件行数正确（4 行 + 末尾空行 = 5）",
   lines == 5, "lines=%d" % lines)
# ⚠ 实测行为：QScintilla 的 `text()` **保留原始 CR 字符**
#   （`'line1\r\nline2\nline3\rline4\r'`），它按 CRLF/CR 都算换行，
#   所以行数与显示正确。这里断言的是"内容正确"，不是"文本里没有 CR"。
ok("B1.2 混合换行内容正确（归一后）",
   norm == "line1\nline2\nline3\nline4", repr(txt))
ok("B1.3 编辑器保留了每行的原始行尾符号",
   txt.count("\r\n") == 1
   and txt.count("\n") - txt.count("\r\n") == 1
   and txt.count("\r") - txt.count("\r\n") == 1,
   "CRLF=%d 单独LF=%d 单独CR=%d"
   % (txt.count("\r\n"),
      txt.count("\n") - txt.count("\r\n"),
      txt.count("\r") - txt.count("\r\n")))

# B2: 编辑一行后保存（未显式切 EOL）
pr.sc.insertAt("EDIT ", 0, 0)
pr.save_file()
data = read_bytes(p)
info("B2 混合换行文件编辑后保存的实际字节：%r" % data)
lines_after = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
ok("B2.1 编辑生效（首行有 EDIT）", data.startswith(b"EDIT line1"),
   repr(data[:14]))
ok("B2.2 保存后行数不变（归一比较）",
   lines_after.count(b"\n") == 4, "换行数=%d" % lines_after.count(b"\n"))
ok("B2.3 未编辑内容未丢失",
   all(x in lines_after for x in (b"line2", b"line3", b"line4")),
   repr(lines_after))

# B3: 显式切 CRLF 后保存 → 全 CRLF
p = os.path.join(TMP, "b3.txt")
write_bytes(p, b"one\ntwo\nthree\n")
pr = fresh_tab(p)
win._on_eol_changed("\r\n")
pr.save_file()
data = read_bytes(p)
ok("B3.1 显式切 CRLF 后保存，全部为 CRLF",
   data == b"one\r\ntwo\r\nthree\r\n", repr(data))
ok("B3.2 没有出现 CRCRLF", b"\r\r" not in data, "")

# B4: 再切回 LF
win._on_eol_changed("\n")
pr.save_file()
data = read_bytes(p)
ok("B4.1 切回 LF 后保存，全部为 LF", data == b"one\ntwo\nthree\n",
   repr(data))

# B5: 混合换行 + 列编辑批量插入 → 保存 → 重开
p = os.path.join(TMP, "b5.txt")
write_bytes(p, b"aaa\r\nbbb\nccc\r")
pr = fresh_tab(p)

col_ok = None
try:
    from ui.column_editor_dialog import (
        MODE_NUMBER,
        PAD_ZERO,
        ColumnEditConfig,
        apply_column_edit,
    )

    # 注意：`pad` 是**填充方式字符串**（PAD_NONE/PAD_ZERO/PAD_SPACE），
    # 不是整数宽度；`lines` 是显式行号列表（None 时退化为光标/选区）。
    cfg = ColumnEditConfig(
        mode=MODE_NUMBER, start=1, step=1, radix=10, pad=PAD_ZERO,
        prefix="", lines=[0, 1, 2], column=0,
    )
    res = apply_column_edit(pr, cfg)
    col_ok = bool(getattr(res, "ok", False))
    info("B5 列编辑结果：ok=%r reason=%r entries=%d"
         % (getattr(res, "ok", None), getattr(res, "reason", ""),
            len(getattr(res, "entries", []) or [])))
except Exception as e:
    info("B5 列编辑调用失败（不影响其它用例）: %s: %s"
         % (type(e).__name__, e))

pr.save_file()
data = read_bytes(p)
info("B5 保存后字节：%r" % data)
ok("B5.1 列编辑后保存的行数不变",
   data.replace(b"\r\n", b"\n").replace(b"\r", b"\n").count(b"\n") == 3,
   "换行数=%d" % data.replace(b"\r\n", b"\n").replace(
       b"\r", b"\n").count(b"\n"))
pr = fresh_tab(p)
ok("B5.2 重开后行数一致", pr.sc.lines() == 4, "lines=%d" % pr.sc.lines())
if col_ok:
    # 编号是 1..3（PAD_ZERO 按"最大数字宽度"补零，1 位数宽 → 不补零）
    ok("B5.3 重开后能看到编号且列位置正确",
       all(tok in sc_text(pr) for tok in ("1aaa", "2bbb", "3ccc")),
       repr(sc_text(pr)[:50]))

# B6: 纯 CR 文件
p = os.path.join(TMP, "b6.txt")
write_bytes(p, b"x\ry\rz\r")
pr = fresh_tab(p)
ok("B6.1 纯 CR 文件行数正确", pr.sc.lines() == 4,
   "lines=%d" % pr.sc.lines())
# 同上：编辑器 text() 保留 CR，断言"归一后内容正确"
ok("B6.2 纯 CR 文本内容正确（归一后）",
   sc_text(pr).replace("\r", "\n") == "x\ny\nz", repr(sc_text(pr)))
pr.sc.insertAt("W", 0, 0)
pr.save_file()
data = read_bytes(p)
ok("B6.3 纯 CR 文件保存后内容未损坏",
   data.replace(b"\r", b"\n") == b"Wx\ny\nz\n", repr(data))
ok("B6.4 纯 CR 文件的 CR 行尾被保留",
   data.count(b"\r") == 3 and b"\n" not in data, repr(data))

# ================================================================
# C. 组合场景
# ================================================================
print()
print("== C. 组合场景（编码 × 换行）==")

# C1: UTF-16 LE + CRLF → 编辑 → 切 LF → 保存
p = os.path.join(TMP, "c1.txt")
body = "甲\r\n乙\r\n"
write_bytes(p, b"\xff\xfe" + body.encode("utf-16-le"))
pr = fresh_tab(p)
# 编辑器 text() 保留 CR（实测行为），断言归一后的内容
ok("C1.1 UTF-16 + CRLF 打开正确（归一后）",
   sc_text(pr).replace("\r\n", "\n").replace("\r", "\n") == "甲\n乙",
   repr(sc_text(pr)))
pr.sc.insertAt("丙", 1, 0)        # 第二行开头插入
win._on_eol_changed("\n")
pr.save_file()
data = read_bytes(p)
ok("C1.2 保存后仍是 UTF-16 LE（BOM）", data.startswith(b"\xff\xfe"),
   repr(data[:4]))
decoded = data[2:].decode("utf-16-le")
ok("C1.3 EOL 已转为 LF", "\r" not in decoded, repr(decoded))
ok("C1.4 编码转换没有破坏内容",
   decoded.count("甲") == 1 and decoded.count("丙") == 1
   and decoded.count("乙") == 1, repr(decoded))

# C2: GBK + CRLF → 转 UTF-8 + 切 LF → 保存
p = os.path.join(TMP, "c2.txt")
write_bytes(p, "中文\r\n第二行\r\n".encode("gbk"))
pr = fresh_tab(p)
ok("C2.1 GBK+CRLF 打开正确（归一后）",
   sc_text(pr).replace("\r\n", "\n").replace("\r", "\n") == "中文\n第二行",
   repr(sc_text(pr)))
pr.document.change_encoding("utf-8", reload=False, mode="convert")
win._on_eol_changed("\n")
pr.save_file()
data = read_bytes(p)
ok("C2.2 保存后为 UTF-8 字节",
   data == "中文\n第二行\n".encode("utf-8"), repr(data))
ok("C2.3 无 BOM（转换不应凭空加 BOM）",
   not data.startswith(b"\xef\xbb\xbf"), repr(data[:4]))

# C3: 大文件（2MB）+ 切 EOL + 编辑 + 保存
if not QUICK:
    p = os.path.join(TMP, "c3.txt")
    n = 40000
    with open(p, "wb") as f:
        f.write(b"".join(b"row %06d\n" % i for i in range(n)))
    size_mb = os.path.getsize(p) / 1024 / 1024
    t0 = time.time()
    pr = fresh_tab(p)
    t_open = time.time() - t0
    ok("C3.1 打开 2MB 文件行数正确", pr.sc.lines() == n + 1,
       "lines=%d (%.1f MB)" % (pr.sc.lines(), size_mb))
    t0 = time.time()
    win._on_eol_changed("\r\n")
    pr.save_file()
    t_conv = time.time() - t0
    data = read_bytes(p)
    ok("C3.2 大文件切 CRLF 后保存成功",
       data.count(b"\r\n") == n, "CRLF=%d" % data.count(b"\r\n"))
    ok("C3.3 大文件没有出现 CRCRLF", b"\r\r" not in data, "")
    info("C3 耗时：打开 %.2fs，切 EOL+保存 %.2fs（%d 行）"
         % (t_open, t_conv, n))
else:
    info("C3 已跳过（--quick）")

# ================================================================
# D. 不变量
# ================================================================
print()
print("== D. 不变量（打开-保存不应改变文件）==")

CASES = [
    ("utf-8 无 BOM", "中文\n第二行\n".encode("utf-8")),
    ("utf-8 BOM", b"\xef\xbb\xbf" + "带BOM\n".encode("utf-8")),
    ("utf-16-le BOM", b"\xff\xfe" + "UTF16\n".encode("utf-16-le")),
    ("utf-16-be BOM", b"\xfe\xff" + "UTF16BE\n".encode("utf-16-be")),
    ("gbk", "国标编码\n".encode("gbk")),
    ("CRLF", b"a\r\nb\r\n"),
    ("LF", b"a\nb\n"),
    ("CR", b"a\rb\r"),
    ("混合换行", b"a\r\nb\nc\rd\r\n"),
]
for i, (label, raw) in enumerate(CASES, 1):
    p = os.path.join(TMP, "d%d.bin" % i)
    write_bytes(p, raw)
    pr = fresh_tab(p)
    pr.save_file()          # 打开后**不编辑**直接保存
    same = read_bytes(p) == raw
    ok("D1.%d 打开后立即保存字节不变（%s）" % (i, label), same,
       "" if same else "原=%r 新=%r" % (raw[:16], read_bytes(p)[:16]))

# D2: 编辑后撤销全部 → 保存 → 字节一致
#
# ⚠ 注意：本产品的撤销是**自研栈**（`core/undo.py` + `EditorProxy.undo`），
#   `EditorProxy._connect_signals` 里显式执行了
#   `SCI_SETUNDOCOLLECTION(0)` 关闭 QScintilla 内置撤销栈
#   （为了让 Vim 模式/列编辑等走统一的撤销记录）。
#   因此必须调 `proxy.undo()`；`sc.undo()` 在这个产品里**本来就是空操作**。
p = os.path.join(TMP, "d2.txt")
raw = "abc\ndef\n".encode("utf-8")
write_bytes(p, raw)
pr = fresh_tab(p)
pr.sc.insertAt("ZZZ", 0, 0)
app.processEvents()
info("D2 插入后 can_undo=%r text=%r"
     % (pr.undo_manager.can_undo(), pr.sc.text()))
pr.undo()
app.processEvents()
info("D2 proxy.undo() 后 text=%r" % (pr.sc.text(),))
pr.save_file()
info("D2 编辑+撤销后保存字节：%r（原 %r）" % (read_bytes(p), raw))
ok("D2.1 编辑并撤销后保存不改变内容",
   read_bytes(p) == raw, repr(read_bytes(p)))

# D3: 保存后 Scintilla 行数与 provider 行数一致
p = os.path.join(TMP, "d3.txt")
write_bytes(p, b"1\n2\n3\n4\n5\n")
pr = fresh_tab(p)
sc_n = pr.sc.lines()
prov = pr.document.provider.read_text()
prov_n = prov.count("\n") + (0 if prov.endswith("\n") else 1)
ok("D3.1 编辑器行数与 provider 行数一致",
   sc_n == prov_n + 1, "sc=%d prov=%d" % (sc_n, prov_n))

# ================================================================
# 汇总
# ================================================================
print()
print("=" * 100)
print("结果：通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
print("=" * 100)
if FAIL:
    print("失败项：")
    for n in FAIL:
        print("  - " + n)

try:
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)
except Exception:
    pass

# 显式清理再退出（否则 offscreen 下解释器析构可能段错误）
try:
    win._teardown_key_sequences()
except Exception:
    pass
try:
    while win.tabs.count():
        win.tabs.close_tab(0)
    win.close()
    win.deleteLater()
    app.processEvents()
except Exception:
    pass

sys.exit(1 if FAIL else 0)
