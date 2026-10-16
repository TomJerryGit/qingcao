# -*- coding: utf-8 -*-
"""青草编辑器 · 性能剖析（profiler）验证

不依赖 pytest，直接运行::

    python tools\\verify_profiler.py

覆盖：
  A. 纯逻辑（core/profiler.py）：start/stop/get_result/save_report 的
     状态机与报告内容；重复 start、未 start 就 stop 等边界；
  B. 真实 GUI（ui/profiler_panel.py，offscreen）：对话框可构造、
     按钮行为、状态标签随开始/停止变化、停止后结果框有内容；
  C. 接线：MainWindow 里确实注册了「⏱ 性能剖析…」菜单项、
     有 `_show_profiler` 方法、且该项**不绑快捷键**
     （避免与 tests/test_shortcuts.py 的重复检测冲突）。

退出码: 0 = 全部通过；1 = 有失败项。
"""
import os
import sys
import tempfile


os.chdir(r"D:\QingCaoEditor")
sys.path.insert(0, r"D:\QingCaoEditor")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %-56s %s" % ("OK " if cond else "FAIL", name, detail))


def burn_cpu(n=200000):
    """做一点确定性的 Python 工作，保证 cProfile 有东西可记"""
    return sum(i * i for i in range(n))


print("=" * 96)
print("青草编辑器 · 性能剖析验证")
print("=" * 96)

# ============================================================
# A. 纯逻辑
# ============================================================
print()
print("== A. core/profiler.py 纯逻辑 ==")
from core.profiler import Profiler, get_profiler  # noqa: E402


p = Profiler()
check("A1 新建实例 active=False", p.active is False, str(p.active))
check("A2 未 start 时 stop() 返回 None", p.stop() is None, repr(p.stop()))
check("A3 未 start 时 get_result() 为 None",
      p.get_result() is None, repr(p.get_result()))

check("A4 start() 返回 True", p.start() is True, "")
check("A5 start() 后 active=True", p.active is True, str(p.active))
check("A6 重复 start() 返回 False（已在运行）", p.start() is False, "")

burn_cpu()
report = p.stop()
check("A7 stop() 返回非空报告", bool(report),
      "%d 字符" % len(report or ""))
check("A8 报告含 pstats 列名 ncalls", "ncalls" in (report or ""), "")
check("A9 报告含 pstats 列名 tottime", "tottime" in (report or ""), "")
check("A10 报告里能看到我们调用的函数 burn_cpu",
      "burn_cpu" in (report or ""), "")
check("A11 stop() 后 active=False", p.active is False, str(p.active))
check("A12 get_result() 与 stop() 返回值一致",
      p.get_result() == report, "")

tmp = os.path.join(tempfile.gettempdir(), "qc_profiler_verify.txt")
try:
    check("A13 save_report() 返回 True", p.save_report(tmp) is True, "")
    with open(tmp, encoding="utf-8") as fh:
        check("A14 保存内容与报告一致", fh.read() == report, "")
finally:
    if os.path.exists(tmp):
        os.remove(tmp)
check("A15 get_profiler() 返回单例",
      get_profiler() is get_profiler(), "")

# 未产出报告时 save_report 必须失败而不是写空文件
p2 = Profiler()
check("A16 无报告时 save_report() 返回 False",
      p2.save_report(tmp) is False, "")
check("A17 无报告时未创建文件", not os.path.exists(tmp), "")

# ============================================================
# B. GUI
# ============================================================
print()
print("== B. ui/profiler_panel.py 对话框（offscreen）==")
from PyQt5.QtWidgets import QApplication  # noqa: E402


app = QApplication.instance() or QApplication([])

from ui.profiler_panel import ProfilerDialog  # noqa: E402


dlg = ProfilerDialog(None)
check("B1 ProfilerDialog 可构造（parent=None）", dlg is not None, "")
check("B2 三个按钮齐全",
      all(hasattr(dlg, n) for n in ("start_btn", "stop_btn", "save_btn")), "")
check("B3 排序下拉存在且有选项",
      hasattr(dlg, "sort_combo") and dlg.sort_combo.count() >= 4,
      "%d 项" % getattr(dlg.sort_combo, 'count', lambda: 0)())
check("B4 结果框存在（report_view）",
      hasattr(dlg, "report_view") and dlg.report_view is not None, "")

status0 = dlg.status_label.text()
dlg.start_btn.click()
status1 = dlg.status_label.text()
check("B5 点击开始后状态文案变化", status1 != status0,
      "%r -> %r" % (status0, status1))
check("B6 开始后状态含「运行」", "运行" in status1, status1)

burn_cpu()
dlg.stop_btn.click()
status2 = dlg.status_label.text()
check("B7 点击停止后状态变化回未运行", status2 != status1,
      "%r -> %r" % (status1, status2))

# ⚠️ 属性名必须是实际存在的 `report_view`。
#    实测：面板里是 `self.report_view = QPlainTextEdit(...)`，
#    并没有 result_edit / output_edit —— 凭猜测写断言会假失败。
result_widget = getattr(dlg, "report_view", None)
if result_widget is not None:
    text = result_widget.toPlainText()
    check("B8 停止后结果框有报告内容", bool(text), "%d 字符" % len(text))
    check("B9 结果框内容含 ncalls", "ncalls" in text, "")
else:
    check("B8 停止后结果框有报告内容", False, "未找到 report_view 控件")

dlg.close()

# ============================================================
# C. 接线
# ============================================================
print()
print("== C. 接线（MainWindow）==")
from PyQt5.QtWidgets import QAction  # noqa: E402

from ui.main_window import MainWindow  # noqa: E402


win = MainWindow()
check("C1 MainWindow 有 _show_profiler 方法",
      callable(getattr(win, "_show_profiler", None)), "")

items = [a for a in win.findChildren(QAction) if "性能剖析" in a.text()]
check("C2 菜单里存在「性能剖析」项", len(items) == 1,
      "%d 项: %s" % (len(items), [a.text() for a in items]))
if items:
    act = items[0]
    check("C3 菜单项文本正确", act.text() == "⏱ 性能剖析…", repr(act.text()))
    check("C4 **不绑快捷键**（避免重复绑定）",
          act.shortcut().isEmpty(), repr(act.shortcut().toString()))
    check("C5 有 tooltip 说明局限", bool(act.toolTip()), "")
    check("C6 tooltip 提到「Python」局限",
          "Python" in act.toolTip(), "")

# 静态确认插在「性能监控」之后（同级菜单、顺序相邻）
tools_menu = getattr(win, "tools_menu", None)
if tools_menu is not None:
    texts = [a.text() for a in tools_menu.actions()]
    idx_perf = next((i for i, t in enumerate(texts) if "性能监控" in t), -1)
    idx_prof = next((i for i, t in enumerate(texts) if "性能剖析" in t), -1)
    check("C7 「性能剖析」紧跟在「性能监控」之后",
          idx_perf >= 0 and idx_prof == idx_perf + 1,
          "监控@%d 剖析@%d" % (idx_perf, idx_prof))
else:
    check("C7 「性能剖析」紧跟在「性能监控」之后", False, "无 tools_menu")

# AST 静态检查：main_window 源码里确实引用了 _show_profiler
import ast
import io


src = io.open("ui/main_window.py", encoding="utf-8").read()
tree = ast.parse(src)
hit = any(
    isinstance(n, ast.Attribute) and n.attr == "_show_profiler"
    for n in ast.walk(tree)
)
check("C8 main_window 源码把 _show_profiler 接到了菜单上", hit, "")

print()
print("=" * 96)
print("结果：通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
print("=" * 96)
if FAIL:
    print("失败项：")
    for n in FAIL:
        print("  - " + n)
sys.exit(1 if FAIL else 0)
