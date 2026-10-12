#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
性能审计基准脚本（配套 docs/audit_performance.md）
=================================================

用途
----
本脚本产出审计报告所需的**全部实测数字**：
  1. 启动路径 cProfile 热点排序（含 `_panels_built` 惰性面板验证）
  2. 1 MB / 10 MB 文件下每类操作的耗时表
  3. 正则回溯（ReDoS）恶意输入测试
  4. 大文件操作前后的 RSS 内存增长

为什么需要它
------------
审计会话中 shell 被沙箱阻断（`SetNamedSecurityInfoW failed (Win32 5):
grantWrite(D:\\QingCaoEditor)`），无法执行任何命令，因此报告里没有实测数字。
在有 shell 的环境里跑本脚本即可补齐。

用法
----
    # 全量（约 10-30 分钟，10 MB 用例很慢）
    python tools/bench_performance_audit.py

    # 只要启动 profile（最快，约 1 分钟）
    python tools/bench_performance_audit.py --only startup

    # 只要 1 MB 用例
    python tools/bench_performance_audit.py --only bigfile --size 1

    # 只要 ReDoS / 内存
    python tools/bench_performance_audit.py --only redos
    python tools/bench_performance_audit.py --only memory

输出
----
stdout 为 Markdown 片段，可直接粘贴进报告。
同时写出 `docs/audit_performance_raw.md`（原始输出留档）。

注意
----
本脚本在无 shell 会话中编写，**未经运行验证**。每个基准都包了
try/except，单项失败不会中断整体。若某项报 `SKIP/ERROR`，请把
异常原文贴进报告的"未覆盖"一节。
"""

import cProfile
import gc
import io
import os
import pstats
import statistics
import sys
import tempfile
import time
import traceback


# ---- 离屏 GUI（必须在任何 PyQt5 导入之前） ----
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# ---- 控制台 GBK 兼容 ----
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 离屏环境无字体，QScintilla 会用不到等宽字体
CONSOLA = r"C:\Windows\Fonts\consola.ttf"

OUT_LINES = []


def emit(line=""):
    """同时打印并留档"""
    print(line)
    OUT_LINES.append(line)


def hr(title):
    emit()
    emit("## " + title)
    emit()


def med(fn, runs=5, warmup=1):
    """多次运行取中位数（秒）。返回 (中位数, 全部样本)"""
    samples = []
    for _ in range(warmup):
        try:
            fn()
        except Exception:
            pass
    for _ in range(runs):
        gc.collect()
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return statistics.median(samples), samples


def fmt_ms(sec):
    return "%.1f" % (sec * 1000.0)


def guard(label, fn):
    """执行并返回 (ok, value_or_none, err)"""
    try:
        return True, fn(), None
    except Exception as e:
        emit("- `%s` **ERROR**: %s" % (label, e))
        return False, None, e


# ============================================================
# 0. 环境
# ============================================================
def env_info():
    hr("0. 环境")
    emit("| 项 | 值 |")
    emit("|---|---|")
    emit("| Python | %s |" % sys.version.replace("\n", " "))
    emit("| platform | %s |" % sys.platform)

    try:
        from PyQt5.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
        emit("| Qt | %s |" % QT_VERSION_STR)
        emit("| PyQt5 | %s |" % PYQT_VERSION_STR)
    except Exception as e:
        emit("| PyQt5 | 不可用: %s |" % e)

    try:
        from PyQt5.Qsci import QSCINTILLA_VERSION_STR
        emit("| QScintilla | %s |" % QSCINTILLA_VERSION_STR)
    except Exception as e:
        emit("| QScintilla | 不可用: %s |" % e)

    for mod in ("psutil", "hyperscan"):
        try:
            m = __import__(mod)
            emit("| %s | %s |" % (mod, getattr(m, "__version__", "?")))
        except ImportError:
            emit("| %s | 未安装 |" % mod)


def make_qapp():
    from PyQt5.QtGui import QFontDatabase
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    if os.path.exists(CONSOLA):
        QFontDatabase.addApplicationFont(CONSOLA)
    return app


# ============================================================
# 1. 启动 cProfile
# ============================================================
def bench_startup():
    """启动热点：import + MainWindow() 构造"""
    hr("1. 启动路径 cProfile")
    make_qapp()

    emit("### 1.1 import ui.main_window")
    ok, _, _ = guard("import", lambda: __import__(
        "ui.main_window", fromlist=["MainWindow"]))
    if not ok:
        return

    t_import = None
    def _imp():
        import importlib

        import ui.main_window as mw
        importlib.reload(mw)
    t_import, _ = med(_imp, runs=3, warmup=0)
    emit("- import `ui.main_window`（reload 热态）中位数: **%s ms**"
         % fmt_ms(t_import))

    emit()
    emit("### 1.2 MainWindow() 构造成本（cProfile cumtime top 15）")
    from ui.main_window import MainWindow

    def _build():
        w = MainWindow()
        w.deleteLater()
        return w

    pr = cProfile.Profile()
    t0 = time.perf_counter()
    pr.enable()
    win = _build()
    pr.disable()
    t_build = time.perf_counter() - t0
    emit("- `MainWindow()` 单次构造: **%s ms**" % fmt_ms(t_build))

    buf = io.StringIO()
    st = pstats.Stats(pr, stream=buf).sort_stats("cumulative")
    st.print_stats(15)
    emit()
    emit("```")
    emit(buf.getvalue().rstrip())
    emit("```")

    emit()
    emit("### 1.3 惰性面板验证（`_panels_built` 应为空集）")
    win2 = MainWindow()
    built = getattr(win2, "_panels_built", None)
    emit("- `_panels_built` = `%r`" % (built,))
    if built is not None:
        emit("- 判定: **%s**"
             % ("惰性生效（空集）" if len(built) == 0
                else "惰性未完全生效，已构造: %r" % (sorted(built),)))
    for name in getattr(MainWindow, "_LAZY_PANELS", ()):
        emit("- `%s` = %r" % (name, getattr(win2, name, "<缺失>")))

    emit()
    emit("### 1.4 逐面板构造成本（单独计时）")
    emit("| 面板 | 构造耗时 (ms) |")
    emit("|---|---|")
    for name in getattr(MainWindow, "_LAZY_PANELS", ()):
        w = MainWindow()

        def _one(n=name, ww=w):
            ww._ensure_panel(n)

        ok, t, err = guard(name, lambda: med(_one, runs=3, warmup=0)[0])
        if ok:
            emit("| %s | %s |" % (name, fmt_ms(t)))
        else:
            emit("| %s | ERROR |" % name)
        w.deleteLater()

    win2.deleteLater()


# ============================================================
# 2. 大文件生成
# ============================================================
def make_python_file(path, target_bytes, matches_every=37):
    """生成一个规模可控的 .py 文件（函数多、有匹配点）"""
    chunks = []
    size = 0
    i = 0
    head = ("# -*- coding: utf-8 -*-\n"
            "import os\nimport sys\n\n"
            "NEEDLE = 'quick brown fox'\n\n")
    chunks.append(head)
    size += len(head)
    while size < target_bytes:
        body = (
            "def function_%d(a, b, c):\n"
            "    \"\"\"docstring for function_%d\"\"\"\n"
            "    value = a + b * c\n"
            "    if value > 10 and value < 1000:\n"
            "        return 'quick brown fox %d'\n"
            "    elif value == 0:\n"
            "        return os.path.join('a', 'b')\n"
            "    for i in range(3):\n"
            "        value += i\n"
            "    return value\n\n"
        ) % (i, i, i)
        chunks.append(body)
        size += len(body)
        i += 1
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(chunks))
    return os.path.getsize(path)


def bench_bigfile(size_mb):
    hr("2. 大文件操作耗时表（%d MB）" % size_mb)
    make_qapp()

    from PyQt5.Qsci import QsciLexerPython, QsciScintilla

    tmpdir = tempfile.mkdtemp(prefix="qcbench_")
    path = os.path.join(tmpdir, "big_%dmb.py" % size_mb)
    nbytes = make_python_file(path, size_mb * 1024 * 1024)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    nlines = text.count("\n") + 1
    emit("- 文件: `%s`" % path)
    emit("- 实际大小: **%d 字节**（%.2f MB）" % (nbytes, nbytes / 1048576.0))
    emit("- 行数: **%d**" % nlines)
    emit()

    emit("| 操作 | 中位数 (ms) | 样本 (ms) | >500ms? | 备注 |")
    emit("|---|---|---|---|---|")

    def row(name, fn, runs=5, note=""):
        try:
            m, s = med(fn, runs=runs)
            samples = ", ".join(fmt_ms(x) for x in s)
            emit("| %s | **%s** | %s | %s | %s |" % (
                name, fmt_ms(m), samples,
                "**是**" if m > 0.5 else "否", note))
            return m
        except Exception as e:
            emit("| %s | ERROR | - | - | %s |" % (name, repr(e)[:120]))
            return None

    # ---- 打开（provider + Scintilla） ----
    from core.content_provider import LocalFileProvider

    def op_open_provider():
        p = LocalFileProvider()
        p.open(path)
        p.close()
    row("打开(provider)", op_open_provider)

    sc = QsciScintilla()
    sc.setUtf8(True)
    sc.setLexer(QsciLexerPython())

    def op_settext():
        sc.setText(text)
    row("打开(Scintilla setText 全文)", op_settext, runs=3,
        note="O(N) 文本灌入 + 词法分析")

    def op_text_copy():
        _ = sc.text()
    row("`sc.text()` 单次全文拷贝", op_text_copy, runs=5,
        note="P1 重复计算基线")

    # ---- provider.read_text() —— 是否缓存 ----
    prov = LocalFileProvider()
    prov.open(path)
    row("`provider.read_text()` 第 1 次", lambda: prov.read_text(), runs=1)
    row("`provider.read_text()` 第 2 次（是否缓存）",
        lambda: prov.read_text(), runs=3,
        note="若与第 1 次同量级 => **无缓存**")

    # ---- 搜索 ----
    from core.search import SearchEngine, SearchOptions
    opts = SearchOptions(pattern="quick brown fox", is_regex=False)

    def op_search_full():
        e = SearchEngine(prov, opts)
        e.search()
    m_search = row("搜索(新建 engine，含 read_text)", op_search_full, runs=3)

    def op_search_warm():
        e = SearchEngine(prov, opts)
        e.search()
    row("搜索(第 2 次)", op_search_warm, runs=3,
        note="新 engine => 无跨次缓存")

    # ---- 替换（O(M*N) 重点） ----
    def op_replace():
        from core.search import ReplaceEngine
        e = SearchEngine(prov, opts)
        r = e.search()
        ReplaceEngine(prov).replace_all(r, "REPLACED", is_regex=False)
    row("全部替换(ReplaceEngine.replace_all)", op_replace, runs=1,
        note="O(M*N) 字符串重建，见 F1")

    prov.close()

    # ---- 大纲解析 ----
    def op_outline():
        from ui.outline_panel import SymbolParser
        p = SymbolParser()
        p.parse(text, "python", path)
    row("大纲解析(全量)", op_outline, runs=3)

    # ---- 代码度量（O(F*N) 重点） ----
    def op_metrics():
        from core.code_metrics import analyze_file
        analyze_file(path)
    row("代码度量 analyze_file", op_metrics, runs=1,
        note="含 O(F*N)，见 F5")
    try:
        from core.code_metrics import analyze_python, calculate_complexity
        row("  └ analyze_python", lambda: analyze_python(text), runs=1)
        row("  └ calculate_complexity",
            lambda: calculate_complexity(text), runs=3)
    except Exception as e:
        emit("|   └ 拆分计时 | ERROR | - | - | %s |" % repr(e)[:80])

    # ---- 代码坏味（死代码，仅留档） ----
    def op_smell():
        from core.code_smell import get_smells
        get_smells(text, "python")
    row("代码坏味 get_smells", op_smell, runs=1,
        note="**运行时无调用点**，仅留档，见 F17")

    # ---- 字数统计 ----
    import re as _re

    def op_wordcount():
        chars = len(text)
        _ = len(_re.sub(r"\s", "", text))
        _ = len(text.split())
        _ = text.count("\n") + 1
        _ = len([l for l in text.split("\n") if l.strip()])
        return chars
    row("字数统计(单次，插件每秒跑一次)", op_wordcount, runs=3,
        note="见 F9：隐藏面板也每秒执行")

    # ---- 高亮全部 ----
    from core.search import SearchOptions as SO

    def op_highlight():
        opts2 = SO(pattern="quick brown fox", is_regex=True)
        e = SearchEngine(prov_dummy(), opts2)
        return e.search()
    try:
        prov2 = LocalFileProvider()
        prov2.open(path)

        def prov_dummy():
            return prov2

        row("高亮全部(highlight_all 等价：regex 全文扫描)",
            op_highlight, runs=3, note="见 F3")
        prov2.close()
    except Exception as e:
        emit("| 高亮全部 | ERROR | - | - | %s |" % repr(e)[:80])

    # ---- 折叠 ----
    def op_fold():
        sc.setFolding(QsciScintilla.BoxedFoldStyle)
        for i in range(0, min(nlines, 20000), 500):
            sc.SendScintilla(sc.SCI_TOGGLEFOLD, i)
    row("折叠(全部折叠)", op_fold, runs=1)

    # ---- Minimap ----
    def op_minimap():
        from ui.minimap import Minimap
        mm = Minimap()
        mm.set_editor(sc)
        mm.deleteLater()
    row("Minimap set_editor(全文拷贝+共享 lexer)", op_minimap, runs=3,
        note="见 F6")

    # ---- 行索引 ----
    def op_line_index_build():
        from core.search import SearchEngine
        e = SearchEngine(prov3(), SO(pattern="x"))
        e._ensure_line_index()

    try:
        prov3 = LocalFileProvider()
        prov3.open(path)
        row("搜索行索引构建", op_line_index_build, runs=3)
        prov3.close()
    except Exception as e:
        emit("| 搜索行索引构建 | ERROR | - | - | %s |" % repr(e)[:80])

    # ---- document.build_line_index（逐字符 Python 循环） ----
    def op_doc_line_index():
        from core.document import Document
        d = Document()
        d.provider = prov4()
        d._invalidate_line_index()
        d.build_line_index()
    try:
        prov4 = LocalFileProvider()
        prov4.open(path)

        def prov4():
            return prov4

        row("document.build_line_index（逐字符循环）",
            op_doc_line_index, runs=1, note="见 F13")
        prov4.close()
    except Exception as e:
        emit("| document.build_line_index | ERROR | - | - | %s |"
             % repr(e)[:80])

    sc.deleteLater()
    emit()
    emit("生成的文件保留在: `%s`（审计结束可删）" % tmpdir)
    return path, text, nlines


# ============================================================
# 3. ReDoS
# ============================================================
REDOS_CASES = [
    ("(a+)+$", "a" * 50000 + "!"),
    ("(a|a)*$", "a" * 50000 + "!"),
    ("(.*)*b", "a" * 50000 + "!"),
    ("^\\s*$", " " * 100000 + "x"),
    ("(x+x+)+y", "x" * 40000 + "z"),
]


def _worker(pattern, subject, q):
    import re
    try:
        rx = re.compile(pattern)
        t0 = time.perf_counter()
        rx.search(subject)
        q.put(("ok", time.perf_counter() - t0))
    except Exception as e:
        q.put(("err", repr(e)))


def bench_redos(timeout=10.0):
    hr("3. 正则回溯（ReDoS）")
    emit("超时上限 %.0f s（子进程计时，超时即判定卡死）" % timeout)
    emit()
    emit("| 恶意正则 | 输入 | 结果 | 耗时 (s) |")
    emit("|---|---|---|---|")

    import multiprocessing as mp
    ctx = mp.get_context("spawn")

    for pattern, subject in REDOS_CASES:
        q = ctx.Queue()
        p = ctx.Process(target=_worker, args=(pattern, subject, q))
        p.start()
        p.join(timeout)
        if p.is_alive():
            p.terminate()
            p.join()
            emit("| `%s` | %s×%d | **卡死/超时** | >%.0f |"
                 % (pattern, subject[0], len(subject), timeout))
        else:
            try:
                kind, val = q.get_nowait()
                if kind == "ok":
                    emit("| `%s` | %s×%d | 完成 | %.4f |"
                         % (pattern, subject[0], len(subject), val))
                else:
                    emit("| `%s` | %s×%d | 编译错误 | %s |"
                         % (pattern, subject[0], len(subject), val))
            except Exception:
                emit("| `%s` | %s×%d | 进程异常退出 | - |"
                     % (pattern, subject[0], len(subject)))

    emit()
    emit("### 3.1 应用内路径：timeout_seconds 是否生效")
    emit()
    emit("把上表任一卡死正则填进「查找」框并勾选「正则」，观察：")
    emit("- `core/search.py:102` 声明了 `timeout_seconds=30`，")
    emit("  但全仓库只有声明处出现该字段（`grep -n timeout_seconds`），")
    emit("  `iter_matches()` 只检查 `is_cancelled()` 与 `max_results`。")
    emit("- 因此预期：**超时选项不生效，UI 永久冻结**（见 F4）。")
    emit()
    emit("用以下片段可实测确认（会卡住，务必用子进程 + 超时）：")
    emit()
    emit("```python")
    emit("from core.search import SearchEngine, SearchOptions")
    emit("from core.content_provider import LocalFileProvider")
    emit("p = LocalFileProvider(); p.open('big.py')")
    emit("opt = SearchOptions(pattern=r'(a+)+$', is_regex=True)")
    emit("SearchEngine(p, opt).search()   # 无超时保护")
    emit("```")


# ============================================================
# 4. 内存
# ============================================================
def bench_memory(size_mb=10):
    hr("4. 内存（RSS）")
    try:
        import psutil
    except ImportError:
        emit("psutil 未安装，跳过。`pip install psutil` 后重跑。")
        return

    proc = psutil.Process()

    def rss_mb():
        gc.collect()
        return proc.memory_info().rss / 1048576.0

    make_qapp()
    tmpdir = tempfile.mkdtemp(prefix="qcmem_")
    path = os.path.join(tmpdir, "mem_%dmb.py" % size_mb)
    nbytes = make_python_file(path, size_mb * 1024 * 1024)

    base = rss_mb()
    emit("- 文件大小: **%.2f MB**" % (nbytes / 1048576.0))
    emit("- 基线 RSS: **%.1f MB**" % base)
    emit()
    emit("| 步骤 | RSS (MB) | 增量 (MB) |")
    emit("|---|---|---|")

    def step(name, fn, release=True):
        before = rss_mb()
        try:
            fn()
        except Exception as e:
            emit("| %s | ERROR %s | - |" % (name, repr(e)[:60]))
            return
        if release:
            gc.collect()
        after = rss_mb()
        emit("| %s | %.1f | %+.1f |" % (name, after, after - before))
        return after

    from core.content_provider import LocalFileProvider

    prov_holder = {}

    def _open():
        p = LocalFileProvider()
        p.open(path)
        prov_holder["p"] = p
    step("provider.open (mmap)", _open)

    def _readtext():
        prov_holder["text"] = prov_holder["p"].read_text()
    step("provider.read_text() 首次", _readtext)

    def _readtext2():
        prov_holder["text2"] = prov_holder["p"].read_text()
    step("provider.read_text() 第二次（无缓存 => 再涨一份）", _readtext2,
         release=False)

    from PyQt5.Qsci import QsciLexerPython, QsciScintilla
    sc_holder = {}

    def _sc():
        sc = QsciScintilla()
        sc.setUtf8(True)
        sc.setText(prov_holder["text"])
        sc_holder["sc"] = sc
    step("QsciScintilla.setText(全文)", _sc)

    def _minimap():
        from ui.minimap import Minimap
        mm = Minimap()
        mm.set_editor(sc_holder["sc"])
        sc_holder["mm"] = mm
    step("Minimap.set_editor（第二份完整文档）", _minimap)

    def _search():
        from core.search import SearchEngine, SearchOptions
        opt = SearchOptions(pattern="quick brown fox")
        e = SearchEngine(prov_holder["p"], opt)
        res = e.search()
        sc_holder["res"] = res
        sc_holder["eng"] = e
    step("SearchEngine.search（matches + _text_cache）", _search)

    # 释放后是否回落
    def _release():
        sc_holder.pop("eng", None)
        sc_holder.pop("res", None)
    before = rss_mb()
    _release()
    step("释放 engine/result 后", lambda: None)
    emit()
    emit("- 提示：若「第二次 read_text」增量 ≈ 文件大小，即证实 "
         "`LocalFileProvider.read_text()` **无缓存**（F2）。")
    emit("- 提示：Minimap 那一步增量 ≈ 文件大小，证实 Minimap "
         "持有**第二份完整文档**（F6）。")


# ============================================================
# main
# ============================================================
def main():
    args = sys.argv[1:]

    def opt(name, default=None):
        if name in args:
            i = args.index(name)
            if i + 1 < len(args):
                return args[i + 1]
        return default

    only = opt("--only")
    size = int(opt("--size", "10"))

    t_start = time.perf_counter()
    env_info()

    sections = {
        "startup": bench_startup,
        "bigfile": lambda: bench_bigfile(size),
        "redos": bench_redos,
        "memory": lambda: bench_memory(size),
    }

    if only:
        if only not in sections:
            emit("未知 --only 值: %s（可选: %s）"
                 % (only, ", ".join(sections)))
            return 1
        guard(only, sections[only])
    else:
        for name, fn in sections.items():
            emit()
            emit("---")
            guard(name, fn)

    hr("总耗时")
    emit("- 全部基准耗时: **%.1f s**" % (time.perf_counter() - t_start))

    out = os.path.join(ROOT, "docs", "audit_performance_raw.md")
    try:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(OUT_LINES) + "\n")
        print()
        print("[留档] 原始输出已写入: %s" % out)
    except Exception as e:
        print("[留档] 写入失败: %s" % e)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n中断")
        sys.exit(130)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
