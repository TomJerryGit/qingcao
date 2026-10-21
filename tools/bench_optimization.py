# -*- coding: utf-8 -*-
"""性能基准（可回归）：启动 / 插件 / 事件 / 面板 / 输入 / 大文件 / 会话 / 主题

    python tools\\bench_optimization.py            # 只报告
    python tools\\bench_optimization.py --check    # 超阈值时退出码 1（CI 用）

## 为什么需要这个脚本

本仓库的性能问题多次是"**实测才知道根因**"，而且根因和直觉常常相反：

* 10MB 文件打开 12 秒 —— 直觉以为是 QScintilla，实测 `setText` 只要 0.22s，
  真正原因是 `_has_non_ascii_beyond` 用 Python 逐字节遍历整个文件
  （2080 万次生成器调用）；
* 启动"主题应用 0.73s" —— 实测主题本身很快，0.73s 是 `processEvents`
  顺带触发的插件加载；
* 2MB 文件打开 13 秒 —— 实测是 AI 插件在 UI 线程同步 HTTP 探测 Ollama。

因此这里把**关键路径**固化为数字门槛：改动后跑一次就知道有没有退化。

阈值说明：本机 offscreen 实测值 × 约 2 倍余量，避免正常抖动误报；
CI/他人机器更慢时可用 `--no-check` 或调整 `THRESHOLDS`。
"""
import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402


app = QApplication.instance() or QApplication([])
# offscreen 下真实模态框会段错误；插件激活会问权限
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.critical = staticmethod(lambda *a, **k: QMessageBox.Ok)

from PyQt5.QtGui import QFontDatabase  # noqa: E402


for _p in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\msyh.ttc"):
    if os.path.exists(_p):
        QFontDatabase.addApplicationFont(_p)

# 阈值（秒）：实测值的约 2 倍，留出机器差异余量
THRESHOLDS = {
    "mainwindow": 1.2,
    "startup_total": 2.5,   # 含延迟插件加载（用户实际等待）
    "startup_theme": 1.0,   # 实测 0.53~0.77s 抖动较大
    "event_10k": 0.6,
    "panel_max": 0.3,
    "typing_2000": 0.9,
    "open_1mb": 1.2,
    "open_10mb": 1.5,
    "open_py_2mb": 1.5,
    "session_save": 0.4,
    "theme_notify": 0.8,
}

RESULTS = {}


def measure(name, fn, repeat=1):
    vals = []
    out = None
    for _ in range(repeat):
        t0 = time.perf_counter()
        out = fn()
        vals.append(time.perf_counter() - t0)
    val = statistics.median(vals)
    RESULTS[name] = round(val, 4)
    print("  %-24s %8.3f s%s" % (name, val,
                                 "  (%d 次取中位)" % repeat if repeat > 1 else ""))
    return out


def section(title):
    print()
    print("=" * 74)
    print(title)
    print("=" * 74)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="超阈值返回非零退出码")
    parser.add_argument("--json", type=str, default="",
                        help="把结果写入 JSON 文件")
    args = parser.parse_args()

    from ui.main_window import MainWindow  # noqa: E402

    section("1. 冷启动（到插件全部可用）")
    win = measure("mainwindow", MainWindow)

    # 延迟插件加载是真正的启动尾段：泵事件直到 plugin_manager 就绪
    t0 = time.perf_counter()
    deadline = t0 + 10.0
    while time.perf_counter() < deadline:
        app.processEvents()
        if getattr(win, "plugin_manager", None) is not None:
            break
        time.sleep(0.005)
    app.processEvents()
    RESULTS["startup_total"] = round(time.perf_counter() - t0, 4)
    print("  %-24s %8.3f s（含插件加载）" % ("startup_total",
                                             RESULTS["startup_total"]))
    pm = getattr(win, "plugin_manager", None)
    print("  插件管理器: %r" % (pm,))

    measure("startup_theme", win.apply_startup_theme)

    section("3. 事件分发")
    from app.event_bus import EventBus  # noqa: E402

    bus = EventBus()
    hits = {"n": 0}

    def _on_status(_event):
        hits["n"] += 1

    bus.status_message.connect(_on_status)

    def _emit():
        for i in range(10000):
            bus.emit_status("msg %d" % i, 1000, "info")

    measure("event_10k", _emit)
    print("  回调命中: %d" % hits["n"])

    section("4. 面板首次构造")
    panel_times = {}
    for name in ("outline", "dir_tree", "gsearch", "console", "plugins_panel",
                 "perf_monitor", "minimap", "problems", "lsp",
                 "undo_history", "task"):
        t0 = time.perf_counter()
        win._ensure_panel(name)
        panel_times[name] = round(time.perf_counter() - t0, 4)
        app.processEvents()
    RESULTS["panel_max"] = max(panel_times.values())
    for k, v in panel_times.items():
        print("    %-14s %7.3f s" % (k, v))
    print("  %-24s %8.3f s" % ("panel_max", RESULTS["panel_max"]))

    section("5. 输入延迟")
    ed = win.tabs.add_tab("bench.txt")
    proxy = ed.proxy
    proxy.set_text("x" * 100 + "\n")
    app.processEvents()
    N = 2000

    def _typing():
        for i in range(N):
            proxy.sc.insertAt("a", 0, i)

    measure("typing_2000", _typing)
    print("  单字符: %.1f µs" % (RESULTS["typing_2000"] / N * 1e6))

    section("6. 大文件打开（含内容完整性校验）")
    tmp = tempfile.mkdtemp(prefix="qc_bench_")
    try:
        cases = []
        big_txt = os.path.join(tmp, "big.txt")
        with open(big_txt, "wb") as f:
            f.write(b"hello world 12345\n" * 580_000)
        cases.append(("open_10mb", big_txt, 580_001))
        mid_txt = os.path.join(tmp, "mid.txt")
        with open(mid_txt, "wb") as f:
            f.write(b"hello world 12345\n" * 55_000)
        cases.append(("open_1mb", mid_txt, 55_001))
        big_py = os.path.join(tmp, "big.py")
        with open(big_py, "wb") as f:
            f.write(b"def a():\n    return 1\n" * 250_000)
        cases.append(("open_py_2mb", big_py, 500_001))
        for name, path, expect_lines in cases:
            while win.tabs.count():
                win.tabs.close_tab(0)
            pr = measure(name, lambda p=path: win.tabs.open_file(p))
            app.processEvents()
            lines = pr.sc.lines() if pr is not None else -1
            print("    行数=%d（期望 %d）%s"
                  % (lines, expect_lines,
                     " ✔" if lines == expect_lines else " ✘ 内容不完整!"))
            if lines != expect_lines:
                RESULTS[name] = 999.0     # 数据不完整视为严重失败
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    section("7. 会话保存")
    sess = getattr(win, "session", None)
    if sess is not None:
        try:
            measure("session_save", lambda: sess.save(win.tabs, win))
        except Exception as e:
            print("  session.save 失败: %s" % e)
            RESULTS["session_save"] = -1

    section("8. 主题切换（全窗口 notify_widgets）")
    from infrastructure.theme_loader import BuiltinThemes, notify_widgets  # noqa: E402

    theme = BuiltinThemes.light_clean()
    measure("theme_notify", lambda: notify_widgets(win, theme))

    try:
        win.close()
    except Exception:
        pass

    section("结果汇总")
    problems = []
    for name, limit in THRESHOLDS.items():
        val = RESULTS.get(name)
        if val is None:
            continue
        mark = "OK"
        if val > limit:
            mark = "FAIL"
            problems.append((name, val, limit))
        print("  %-24s %8.3f s   阈值 %5.2f s   %s"
              % (name, val, limit, mark))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"results": RESULTS, "thresholds": THRESHOLDS},
                      f, ensure_ascii=False, indent=2)
        print("\n  结果已写入: %s" % args.json)

    if problems:
        print("\n  性能回归 %d 项:" % len(problems))
        for name, val, limit in problems:
            print("    - %s: %.3f s > %.2f s" % (name, val, limit))
        return 1 if args.check else 0
    print("\n  全部在阈值内")
    return 0


if __name__ == "__main__":
    sys.exit(main())
