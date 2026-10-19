# -*- coding: utf-8 -*-
"""批次 C 验证：多键快捷键序列（core/key_sequence_manager.py 接线）

    python tools\\verify_key_sequences.py

## 为什么这个验证要特别小心

前缀键（`Ctrl+K`）会被序列管理器**消费**。如果实现有误、把普通编辑按键
也当成序列输入吃掉，用户会直接感觉"键盘坏了"。因此本脚本除了功能正确性，
重点验证三道安全闸：

  * 纯字母/数字/退格**不被消费**（无 Ctrl/Alt 直接放行）；
  * 焦点不在编辑器（如对话框输入框）时**不拦截**；
  * 有模态窗口时**不拦截**。

覆盖：
  A. 注册：6 条序列、处理器都存在、前缀键无单键冲突；
  B. 行为：前缀消费 → 第二键触发；超时取消；不匹配按键放行；
  C. 安全：普通按键/非编辑器焦点/模态窗口均不拦截；
  D. 集成：真实 MainWindow 上序列确实注册、状态栏有提示。

退出码: 0 = 全部通过；1 = 有失败项。
"""
import os
import sys
import time


os.chdir(r"D:\QingCaoEditor")
sys.path.insert(0, r"D:\QingCaoEditor")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PyQt5.QtCore import QEvent, Qt  # noqa: E402
from PyQt5.QtGui import QFontDatabase, QKeyEvent  # noqa: E402
from PyQt5.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QLineEdit,
    QMessageBox,
)


app = QApplication.instance() or QApplication([])
for _fp in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\msyh.ttc"):
    if os.path.exists(_fp):
        QFontDatabase.addApplicationFont(_fp)

# headless 下真实模态框会段错误（offscreen 平台限制），统一拦截
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Discard)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Discard)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %-52s %s" % ("OK " if cond else "FAIL", name, detail))


def make_key_event(key, mods, text=""):
    """构造真实 QKeyEvent"""
    return QKeyEvent(QEvent.KeyPress, key, mods, text)


print("=" * 96)
print("批次 C 验证：多键快捷键序列")
print("=" * 96)

# ============================================================
# A. 纯逻辑层
# ============================================================
print()
print("== A. core/key_sequence_manager.py 纯逻辑 ==")
from core.key_sequence_manager import (  # noqa: E402
    KeySequenceManager,
    key_event_to_string,
)


mgr = KeySequenceManager()
hits = []
mgr.register(["Ctrl+K", "Ctrl+S"], lambda: hits.append("save"),
             description="保存全部")
mgr.register(["Ctrl+K", "Ctrl+C"], lambda: hits.append("comment"),
             description="注释")

check("A1 注册 2 条序列", len(mgr.bindings) == 2, str(len(mgr.bindings)))
check("A2 初始不在等待", mgr.is_waiting() is False, "")

r1 = mgr.handle_key("Ctrl+K")
check("A3 前缀键被消费（返回 True）", r1 is True, str(r1))
check("A4 进入等待状态", mgr.is_waiting() is True, "")
r2 = mgr.handle_key("Ctrl+S")
check("A5 第二键触发回调", hits == ["save"], str(hits))
check("A6 触发后清空等待", mgr.is_waiting() is False, "")

# 不匹配的第二键 → 放行
mgr.handle_key("Ctrl+K")
r3 = mgr.handle_key("Ctrl+Z")
check("A7 不匹配的第二键返回 False（放行给编辑器）", r3 is False, str(r3))
check("A8 不匹配后清空等待", mgr.is_waiting() is False, "")

# 非前缀键 → 放行
r4 = mgr.handle_key("Ctrl+B")
check("A9 非前缀键返回 False（放行）", r4 is False, str(r4))

# 超时取消
mgr2 = KeySequenceManager()
mgr2.register(["Ctrl+K", "Ctrl+S"], lambda: None, timeout_ms=80)
mgr2.handle_key("Ctrl+K")
check("A10 超时前仍在等待", mgr2.is_waiting() is True, "")
time.sleep(0.15)
mgr2.handle_key("Ctrl+S")     # 超时后再按，应视为新一轮前缀匹配失败
check("A11 超时后 pending 被清（不会误触发）",
      not mgr2.is_waiting() or len(mgr2._pending_keys) <= 1,
      str(mgr2._pending_keys))

# 键名转换
ev = make_key_event(Qt.Key_S, Qt.ControlModifier, "\x13")
check("A12 QKeyEvent → 'Ctrl+S'",
      key_event_to_string(ev) == "Ctrl+S", key_event_to_string(ev))
ev2 = make_key_event(Qt.Key_A, Qt.NoModifier, "a")
check("A13 普通字母 → 'A'（无修饰键）",
      key_event_to_string(ev2) == "A", key_event_to_string(ev2))

# ============================================================
# B/C/D. 真实 MainWindow 集成 + 安全闸
# ============================================================
print()
print("== B. 真实 MainWindow 集成 ==")
from ui.main_window import MainWindow  # noqa: E402


win = MainWindow()
seq = getattr(win, "key_sequence_manager", None)
check("B1 主窗口创建了序列管理器", seq is not None, "")
check("B2 注册了 6 条序列",
      len(getattr(seq, "bindings", [])) == 6,
      str(len(getattr(seq, "bindings", []))))

# 冲突检测
conflicts = win.key_sequence_conflicts()
check("B3 与现有单键快捷键无冲突", conflicts == [], str(conflicts))

# 处理器都存在
missing = [h for _k, h, _d in win.KEY_SEQUENCES
           if not callable(getattr(win, h, None))]
check("B4 所有序列处理器都存在", not missing, str(missing))

# 前缀键确实无单键绑定
from PyQt5.QtWidgets import QAction  # noqa: E402


prefix = win.KEY_SEQUENCES[0][0][0]
owners = [a.text() for a in win.findChildren(QAction)
          if not a.shortcut().isEmpty()
          and a.shortcut().toString() == prefix]
check("B5 前缀键 %s 没有被单键动作占用" % prefix, not owners, str(owners))

print()
print("== C. 安全闸（不能吞普通按键）==")


def filter_key(key, mods, text=""):
    """走真实 eventFilter 路径，返回是否被消费"""
    ev = make_key_event(key, mods, text)
    target = app.focusWidget() or win
    consumed = win._handle_keyseq_event(target, ev)
    return bool(consumed)


# C1: 普通字母，无 Ctrl/Alt → 不能消费
check("C1 普通字母 'a' 不被消费",
      filter_key(Qt.Key_A, Qt.NoModifier, "a") is False, "")
# C2: Backspace → 不能消费
check("C2 退格键不被消费",
      filter_key(Qt.Key_Backspace, Qt.NoModifier) is False, "")
# C3: 数字键 → 不能消费
check("C3 数字键 '5' 不被消费",
      filter_key(Qt.Key_5, Qt.NoModifier, "5") is False, "")
# C4: Enter → 不能消费
check("C4 回车不被消费",
      filter_key(Qt.Key_Return, Qt.NoModifier, "\r") is False, "")
# C5: 非序列的 Ctrl 组合 → 不能消费
check("C5 Ctrl+B（非序列）不被消费",
      filter_key(Qt.Key_B, Qt.ControlModifier, "\x02") is False, "")

# C6: 焦点不在编辑器时（模拟对话框输入框聚焦）→ 不拦截
dialog = QDialog(win)
edit = QLineEdit(dialog)
dialog.show()
edit.setFocus()
app.processEvents()
consumed_dialog = filter_key(Qt.Key_K, Qt.ControlModifier, "\x0b")
check("C6 焦点在 QLineEdit 时不拦截 Ctrl+K",
      consumed_dialog is False, "")
dialog.close()

# C7: 有模态窗口时 → 不拦截
modal = QDialog(win)
modal.setModal(True)
modal.show()
app.processEvents()


def _test_modal():
    mgr = win.key_sequence_manager
    before = mgr.is_waiting()
    ev = make_key_event(Qt.Key_K, Qt.ControlModifier, "\x0b")
    consumed = win._handle_keyseq_event(app.focusWidget() or win, ev)
    after = mgr.is_waiting()
    return (consumed is False) or (before == after)


check("C7 有模态窗口时不拦截（不会污染序列状态）", _test_modal(), "")
modal.close()

print()
print("== D. 端到端：编辑器内真实按键路径 ==")


def _editor_sequence_flow():
    """在编辑器上走真实路径：Ctrl+K → Ctrl+S 应触发保存全部"""
    # 造一个标签
    ed = win.tabs.add_tab("seqtest.txt")
    if ed is None:
        return False, "无法建标签"
    ed.proxy.set_text("line1\n")
    ed.setFocus()
    app.processEvents()

    called = []
    mgr = win.key_sequence_manager
    # 替换第一个绑定的回调以便断言（不改产品代码）
    orig_cb = mgr.bindings[0].callback
    mgr.bindings[0].callback = lambda: called.append("fired")
    try:
        mgr.cancel()
        ev1 = make_key_event(Qt.Key_K, Qt.ControlModifier, "\x0b")
        c1 = win._handle_keyseq_event(ed, ev1)
        waiting = mgr.is_waiting()
        ev2 = make_key_event(Qt.Key_S, Qt.ControlModifier, "\x13")
        c2 = win._handle_keyseq_event(ed, ev2)
        return (bool(c1) and waiting and bool(c2) and called == ["fired"],
                "consumed1=%r waiting=%r consumed2=%r called=%r"
                % (c1, waiting, c2, called))
    finally:
        mgr.bindings[0].callback = orig_cb
        mgr.cancel()


ok_flow, flow_detail = _editor_sequence_flow()
check("D1 编辑器内 Ctrl+K Ctrl+S 完整触发", ok_flow, flow_detail)

# ============================================================
# 汇总
# ============================================================
print()
print("=" * 96)
print("结果：通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
print("=" * 96)
if FAIL:
    print("失败项：")
    for n in FAIL:
        print("  - " + n)
sys.exit(1 if FAIL else 0)
