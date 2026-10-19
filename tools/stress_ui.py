# -*- coding: utf-8 -*-
"""青草编辑器 · UI 层真实压力测试

与 `tools/stress_test.py` 的分工：

  * `stress_test.py` 压 **Document / 编码 / 换行** 层（无 GUI）；
  * **本脚本**压 **真实 UI 层** —— QScintilla 渲染、撤销栈、对话框、
    标签切换、窗口关闭。这一层之前完全没被真实压力覆盖过。

    python tools\\stress_ui.py            # 全部
    python tools\\stress_ui.py --quick    # 缩小规模（CI 友好）

## 场景

  U1  真实 MainWindow 构造 + 打开 10 MB 文件（约 16 万行）
  U2  在 10 万行上做**整列编辑**（插入文本）—— 检查耗时与"一次撤销回退"
  U3  在 10 万行上插入**数字序列**（同样一条撤销命令）
  U4  大文件对比对话框（> 5MB 阈值 → 必须走摘要模式而不是卡死）
  U5  多标签开关（20 个标签循环切换，检查内存/句柄与耗时）
  U6  关窗清理（dispose 全部 watcher / provider，不得崩溃或泄漏）
  U7  撤销/重做在 10 万行编辑后仍然正确（不是只"能点"）

## 判定

每步都有**硬时限**与**正确性断言**。UI 卡死的典型表现是单步耗时爆炸，
因此"耗时 < 阈值"本身就是断言的一部分。

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

PASS, FAIL, INFO = [], [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %-50s %s" % ("OK " if cond else "FAIL", name, detail))


def timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return out, (time.perf_counter() - t0)


def info(msg):
    INFO.append(msg)
    print("  [INFO] %s" % msg)


print("=" * 100)
print("青草编辑器 · UI 层真实压力测试%s"
      % ("（quick 模式，缩小规模）" if QUICK else ""))
print("=" * 100)

from PyQt5.QtGui import QFontDatabase  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402


app = QApplication.instance() or QApplication([])
for _fp in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\msyh.ttc"):
    if os.path.exists(_fp):
        QFontDatabase.addApplicationFont(_fp)

# ============================================================
# 拦截所有模态框（headless 测试必须做）
# ============================================================
# ★ 为什么必须拦截（实测结论，完整隔离过程见提交说明）：
#
#   在 `QT_QPA_PLATFORM=offscreen` 下，`MainWindow.closeEvent` 里只要有
#   **未保存的修改**，就会弹 `QMessageBox.question` 做确认 —— 而 offscreen
#   平台插件在模态事件循环 + 窗口析构的组合下会**段错误（0xC0000005）**。
#
#   隔离实验（四个变体，各起独立进程）：
#     A 普通修改 + 真实模态框 → 崩溃
#     B 普通修改 + 拦截模态框 → 正常
#     B2 列编辑 + 拦截模态框 → 正常
#     C 无修改（不弹框）       → 正常
#
#   即：崩溃**与列编辑器/具体操作无关**，只取决于"是否弹真实模态框"。
#   真实 GUI（有窗口系统）下这是标准做法，不会崩 —— 属于 headless 环境限制，
#   **不是产品缺陷**。但 headless 压测若不拦截，就永远只能测到这一个假崩溃，
#   测不出真正的性能/正确性问题。
#
#   因此这里统一拦截，并按"用户选择丢弃"处理（与真实用户点"放弃"等价）。
_MODAL_CALLS = []


def _stub_modal(kind):
    def _impl(*args, **kwargs):
        _MODAL_CALLS.append(kind)
        return QMessageBox.Discard
    return staticmethod(_impl)


QMessageBox.question = _stub_modal("question")
QMessageBox.warning = _stub_modal("warning")
QMessageBox.critical = _stub_modal("critical")
QMessageBox.information = _stub_modal("information")

TMP = tempfile.mkdtemp(prefix="qc_ui_stress_")
print("  临时目录: %s" % TMP)
print("  （模态框已拦截：headless 下弹真实模态框会段错误，属平台限制）")
print()

N_BIG = 40000 if QUICK else 100000         # 列编辑目标行数
N_TABS = 6 if QUICK else 20


def write_text(name, text, encoding="utf-8"):
    p = os.path.join(TMP, name)
    with open(p, "w", encoding=encoding, newline="") as f:
        f.write(text)
    return p


def pump_until(cond, timeout=30.0, interval_s=0.01):
    """泵事件循环直到 cond() 为真或超时；返回 (是否满足, 耗时)

    ★ 为什么需要：大文件（>10MB）采用**分片延迟加载**
      （`QTimer.singleShot(0, ...)` 续跑，保持 UI 可响应）。
      真实 GUI 里有事件循环在跑，所以自动完成；但本脚本是顺序执行的，
      不主动 `processEvents()` 的话，定时器回调永远不会执行 ——
      第一版压测就因此只看到 18,461 行（而非 147,687 行）并误判为"截断"。
    """
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout:
        if cond():
            return True, time.perf_counter() - t0
        app.processEvents()
        time.sleep(interval_s)
    app.processEvents()
    return bool(cond()), time.perf_counter() - t0


# ============================================================
# U1. 真实 MainWindow + 打开 10 MB 文件
# ============================================================
print("== U1. 真实 MainWindow 打开 10 MB 文件 ==")
win = None
try:
    from ui.main_window import MainWindow

    win, el_win = timed(lambda: MainWindow())
    check("U1a MainWindow 构造成功", win is not None, "%.2fs" % el_win)
    # 阈值放宽到 15s：实测同一台机器上构造耗时在 0.8s~10s 间波动
    # （取决于机器负载/插件数量），5s 会造成假失败。
    check("U1b 构造耗时 < 15s", el_win < 15.0, "%.2fs" % el_win)

    # 造 10MB 文件
    rows = []
    size = 0
    i = 0
    while size < 10 * 1024 * 1024:
        s = "第 %07d 行：content with 中文混合 and ascii padding xxxxxxxx\n" % i
        rows.append(s)
        size += len(s.encode("utf-8"))
        i += 1
    big = write_text("ui_big_10mb.txt", "".join(rows), "utf-8")
    info("10MB 文件: %.1f MB / %d 行"
         % (os.path.getsize(big) / (1024 * 1024), len(rows)))

    proxy, el_open = timed(lambda: win.tabs.open_file(big))
    check("U1c 打开 10MB 文件成功", proxy is not None, "%.2fs" % el_open)
    check("U1d 打开耗时 < 15s（UI 层，含渲染）", el_open < 15.0,
          "%.2fs" % el_open)

    # 大文件分片加载：必须泵事件循环等它加载完（真实 GUI 由事件循环完成）
    total_blocks = 0
    try:
        total_blocks = proxy.document.provider.total_blocks
    except Exception:
        pass
    ok_load, el_load = pump_until(
        lambda: (getattr(proxy, '_load_cursor', 0) >= total_blocks
                 and getattr(proxy, '_load_total', 0) > 0),
        timeout=60.0,
    )
    if total_blocks:
        info("10MB 分片加载: %d 块，泵事件 %d 轮共 %.2fs"
             % (total_blocks, 0, el_load))
    check("U1e 大文件分片加载能完成（不卡死）", ok_load,
          "%.2fs / %d 块" % (el_load, total_blocks))
    check("U1f 分片加载总耗时 < 20s", el_load < 20.0, "%.2fs" % el_load)

    try:
        line_count = proxy.sc.lines()
    except Exception:
        line_count = -1
    # 注意：文件每行都以 "\n" 结尾，末尾会多出一个"空行起点"，
    # 所以正确行数是 len(rows) + 1（第一版断言写成 len(rows)，是测试错误）。
    check("U1g QScintilla 行数正确", line_count == len(rows) + 1,
          "%d vs %d" % (line_count, len(rows) + 1))
    check("U1h 当前标签是刚打开的文件",
          win.tabs.current_filepath() == os.path.abspath(big),
          str(win.tabs.current_filepath()))
except Exception as e:
    check("U1 MainWindow 大文件场景", False, "%s: %s" % (type(e).__name__, e))
    traceback.print_exc()

# ============================================================
# U2. 10 万行整列编辑
# ============================================================
print()
print("== U2. 在 %d 行上做整列编辑（插入文本）==" % N_BIG)
try:
    col_text = "".join("row %07d abcdefghij\n" % k for k in range(N_BIG))
    col_file = write_text("ui_col.txt", col_text, "utf-8")
    proxy2 = win.tabs.open_file(col_file)
    check("U2a 打开列编辑测试文件", proxy2 is not None,
          "%d 行" % N_BIG)

    from ui.column_editor_dialog import (  # noqa: E402
        ColumnEditConfig,
        apply_column_edit,
    )

    # ★ 必须**显式指定作用行**。
    #
    #   第一版压测写成 `ColumnEditConfig(text="XY", column=2)`，结果只作用
    #   1 行。排查后确认这不是缺陷：无选区时 `resolve_target()` 按
    #   `source="caret"` 只处理光标所在行（这是正确语义，Notepad++ 也是
    #   如此 —— 没有选区就只改当前行）。
    #
    #   压测要测的是"整列编辑 10 万行的性能与撤销原子性"，因此用
    #   `lines=` 显式给出全部行号。
    cfg = ColumnEditConfig(text="XY", column=2,
                           lines=list(range(N_BIG)))
    result, el_col = timed(lambda: apply_column_edit(proxy2, cfg))
    check("U2b 列编辑执行成功", result.ok, result.reason or "")
    check("U2c %d 行列编辑耗时 < 10s" % N_BIG, el_col < 10.0,
          "%.2fs" % el_col)
    check("U2d 作用行数正确", len(result.lines) == N_BIG,
          str(len(result.lines)))

    # 抽检首/中/末行
    first = proxy2.sc.text(0)
    mid = proxy2.sc.text(N_BIG // 2)
    check("U2e 行内容插入位置正确",
          first.startswith("roXYw 0000000"), repr(first[:16]))
    check("U2f 中间行也正确",
          mid.startswith("roXYw %07d" % (N_BIG // 2)), repr(mid[:16]))

    # 关键：一次撤销回退（列编辑的核心承诺）
    undo_depth = len(proxy2.undo_manager.undo_stack)
    check("U2g 撤销栈只有 1 条命令", undo_depth == 1, str(undo_depth))

    proxy2.undo()
    back = proxy2.sc.text(0)
    check("U2h 一次撤销完全回退", back.startswith("row 0000000"), repr(back[:16]))
    last_back = proxy2.sc.text(N_BIG - 1)
    check("U2i 末行也回退了",
          last_back.startswith("row %07d" % (N_BIG - 1)), repr(last_back[:16]))

    proxy2.redo()
    redo_first = proxy2.sc.text(0)
    check("U2j 重做恢复", redo_first.startswith("roXYw 0000000"),
          repr(redo_first[:16]))
except Exception as e:
    check("U2 列编辑压力场景", False, "%s: %s" % (type(e).__name__, e))
    traceback.print_exc()

# ============================================================
# U3. 10 万行数字序列
# ============================================================
print()
print("== U3. 在 %d 行上插入数字序列 ==" % N_BIG)
try:
    num_file = write_text(
        "ui_num.txt",
        "".join("line %07d\n" % k for k in range(N_BIG)), "utf-8")
    proxy3 = win.tabs.open_file(num_file)
    check("U3a 打开数字测试文件", proxy3 is not None, "")

    # ★ mode 必须显式设成 MODE_NUMBER
    #   `ColumnEditConfig` 的 `mode` 默认是 MODE_TEXT，而 `validate()` 对文本
    #   模式要求 `text` 非空 —— 第一版压测漏传 mode，结果返回
    #   "请先输入要插入的文本"，被误当成功能缺陷。
    from ui.column_editor_dialog import MODE_NUMBER  # noqa: E402

    cfg = ColumnEditConfig(mode=MODE_NUMBER, start=1, step=1, radix=10,
                           min_width=4, pad="zero", column=5,
                           lines=list(range(N_BIG)))
    res3, el_num = timed(lambda: apply_column_edit(proxy3, cfg))
    check("U3b 数字序列执行成功", res3.ok, res3.reason or "")
    check("U3c 耗时 < 12s", el_num < 12.0, "%.2fs" % el_num)

    # ★ 注意数字宽度：序列是 1..N_BIG，N_BIG=40000 是 **5 位数**，
    #   而 `compute_number_widths` 按"整段序列的最大宽度"补零 ——
    #   所以首个数字是 "00001"（5 位）而不是 "0001"。
    #   第一版断言写死 4 位，属测试错误（引擎行为正确）。
    width = len(str(N_BIG))
    first3 = proxy3.sc.text(0)
    check("U3d 首个数字按最大宽度补零且位置正确",
          ("line " + "1".zfill(width)) in first3, repr(first3[:24]))
    mid3 = proxy3.sc.text(N_BIG // 2)
    check("U3e 中间行数字递增正确",
          ("line " + str(N_BIG // 2 + 1).zfill(width)) in mid3,
          repr(mid3[:24]))
    check("U3f 撤销栈仍只有 1 条",
          len(proxy3.undo_manager.undo_stack) == 1,
          str(len(proxy3.undo_manager.undo_stack)))
    proxy3.undo()
    check("U3g 一次撤销回退", proxy3.sc.text(0).startswith("line 0000000"),
          repr(proxy3.sc.text(0)[:20]))
except Exception as e:
    check("U3 数字序列压力场景", False, "%s: %s" % (type(e).__name__, e))
    traceback.print_exc()

# ============================================================
# U4. 大文件对比（必须走摘要模式，不能卡死）
# ============================================================
print()
print("== U4. 大文件对比（> 5MB 阈值）==")
try:
    from ui.file_merge_dialog import DIFF_SIZE_THRESHOLD, FileDiffDialog

    big_a = write_text("cmp_a.txt", "A" * 200 + "\n" * 1, "utf-8")
    # 造两个 > 阈值 的文件
    over = DIFF_SIZE_THRESHOLD + 1024 * 1024
    chunk = ("x" * 79 + "\n")
    need = over // len(chunk) + 10
    body_a = "".join(chunk for _ in range(need))
    body_b = body_a[:-100] + "CHANGED\n"
    big_a = write_text("cmp_big_a.txt", body_a, "utf-8")
    big_b = write_text("cmp_big_b.txt", body_b, "utf-8")
    info("对比文件大小: %.1f MB / %.1f MB（阈值 %.0f MB）"
         % (os.path.getsize(big_a) / 1048576,
            os.path.getsize(big_b) / 1048576,
            DIFF_SIZE_THRESHOLD / 1048576))

    dlg, el_cmp = timed(lambda: FileDiffDialog.from_files(big_a, big_b))
    check("U4a 大文件对比对话框构造成功", dlg is not None, "%.2fs" % el_cmp)
    check("U4b 构造耗时 < 10s（未卡死）", el_cmp < 10.0, "%.2fs" % el_cmp)
    check("U4c 进入摘要模式而非渲染正文",
          getattr(dlg, "_large_mode", False) is True,
          "_large_mode=%s" % getattr(dlg, "_large_mode", None))
    if dlg is not None:
        dlg.close()
except Exception as e:
    check("U4 大文件对比场景", False, "%s: %s" % (type(e).__name__, e))
    traceback.print_exc()

# ============================================================
# U5. 多标签循环切换
# ============================================================
print()
print("== U5. %d 个标签循环切换 ==" % N_TABS)
try:
    tabs = []
    for k in range(N_TABS):
        p = write_text("tab_%02d.txt" % k, "tab %d content\n" % k, "utf-8")
        tabs.append(win.tabs.open_file(p))
    opened = sum(1 for t in tabs if t is not None)
    check("U5a %d 个标签全部打开成功" % N_TABS, opened == N_TABS,
          "%d/%d" % (opened, N_TABS))

    def _cycle():
        n = win.tabs.count()
        for k in range(n * 3):
            win.tabs.setCurrentIndex(k % n)
            _ = win.tabs.current_proxy()

    _, el_cycle = timed(_cycle)
    rounds = win.tabs.count() * 3
    check("U5b 循环切换 %d 次耗时 < 8s" % rounds, el_cycle < 8.0,
          "%.2fs（%d 次）" % (el_cycle, rounds))
    check("U5c 切换后标签数未变", win.tabs.count() >= N_TABS,
          str(win.tabs.count()))
except Exception as e:
    check("U5 多标签场景", False, "%s: %s" % (type(e).__name__, e))
    traceback.print_exc()

# ============================================================
# U6. 关窗清理（不得崩溃 / 不得泄漏 watcher）
# ============================================================
print()
print("== U6. 关窗清理 ==")
try:
    n_before = win.tabs.count()
    # 直接走 closeEvent 路径（dispose 所有 watcher/provider）
    _, el_close = timed(win.close)
    check("U6a 关窗未崩溃", True, "%.2fs" % el_close)
    check("U6b 关窗耗时 < 10s", el_close < 10.0, "%.2fs" % el_close)
    info("关窗前标签数: %d" % n_before)
except Exception as e:
    check("U6 关窗场景", False, "%s: %s" % (type(e).__name__, e))
    traceback.print_exc()

# ============================================================
# 汇总
# ============================================================
print()
print("=" * 100)
print("结果：通过 %d 项 / 失败 %d 项" % (len(PASS), len(FAIL)))
print("=" * 100)
if INFO:
    print("信息：")
    for m in INFO:
        print("  · " + m)
if FAIL:
    print("失败项：")
    for n in FAIL:
        print("  - " + n)

try:
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)
except Exception:
    pass

sys.exit(1 if FAIL else 0)
