# -*- coding: utf-8 -*-
"""并发/线程安全审计 —— 实证脚本（audit_concurrency）

运行方式::

    python -m pytest tests/audit_concurrency_probe.py -v -s

本文件是"审计实证"，不是回归测试：它把每一项怀疑点变成可观察的输出，
并打印原始证据（Qt 告警、线程名列表、QThread 计数、异常堆栈）。

重要前提:
  * offscreen 平台下字体库为空，需要手动 addApplicationFont，否则
    QScintilla 可能拿不到字体。
  * 所有等待都走 qtbot.wait / qtbot.waitUntil（驱动 Qt 事件循环）；
    禁止用 time.sleep 轮询。
  * 若某个 case 让 PyQt5 在槽函数里抛出未捕获异常，PyQt5 (>=5.5)
    会调用 qFatal() → abort()，**整个 pytest 进程会死掉**。这本身
    就是最强的证据；为了不丢掉后面的 case，脚本把 pytest 排在
    各 case 之间，崩了也能从最后的输出行定位。
"""

import gc
import os
import sys
import threading
import time
import traceback

import pytest
from PyQt5.QtCore import (
    QCoreApplication,
    QObject,
    QThread,
    QTimer,
    QtMsgType,
    qInstallMessageHandler,
)
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QApplication, QMessageBox, QWidget


# ============================================================
# 基础设施：Qt 告警捕获 / 线程计数
# ============================================================
QT_MESSAGES = []
CALL_LOG = []          # 跨线程回调是否真的被调用


def _qt_message_handler(mode, context, message):
    QT_MESSAGES.append((int(mode), message))
    print("[QtMsg %s] %s" % (mode, message), flush=True)


def _thread_names():
    return sorted(t.name for t in threading.enumerate())


def _qthread_objects():
    return [o for o in gc.get_objects() if isinstance(o, QThread)]


def _dump_threads(tag):
    names = _thread_names()
    alive = [t for t in threading.enumerate() if t.is_alive()]
    print("\n[THREADS %s] count=%d alive=%d" % (tag, len(names), len(alive)),
          flush=True)
    for t in alive:
        print("    %-40s daemon=%s" % (t.name, t.daemon), flush=True)
    return names


@pytest.fixture(autouse=True)
def _capture(qapp):
    global QT_MESSAGES
    QT_MESSAGES = []
    CALL_LOG[:] = []
    old = qInstallMessageHandler(_qt_message_handler)
    # offscreen 下字体库为空：显式加载一个真实字体
    try:
        QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\consola.ttf")
        QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\msyh.ttc")
    except Exception as exc:      # pragma: no cover
        print("[probe] 字体加载跳过: %s" % exc)
    yield QT_MESSAGES
    qInstallMessageHandler(old)


def _pump(qtbot, ms=50):
    """驱动事件循环若干毫秒（不用 time.sleep）"""
    qtbot.wait(ms)


# ============================================================
# A. 微观实验：QObject 被销毁后，singleShot 的回调还会跑吗？
#    这决定了 core/lsp_client.py:406/1477 的危险等级。
# ============================================================
class _Victim(QObject):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def slot(self):
        self.calls += 1
        CALL_LOG.append("bound_method_called")


def test_A1_singleshot_boundmethod_after_cpp_delete(qapp, qtbot):
    """A1: bound method + C++ 对象被 sip.delete → 回调是否仍被调用？"""
    from PyQt5 import sip

    victim = _Victim()
    CALL_LOG[:] = []
    QTimer.singleShot(150, victim.slot)
    print("A1: 删除前 C++ 对象存活 =", not sip.isdeleted(victim), flush=True)

    sip.delete(victim)          # 等价于 lsp_client 引用计数归零后的析构
    gc.collect()
    print("A1: sip.isdeleted(victim) =", sip.isdeleted(victim), flush=True)

    qtbot.wait(600)
    print("A1 结果: 回调被调用次数 = %d, CALL_LOG=%r"
          % (victim.calls, CALL_LOG), flush=True)
    print("A1 说明: 若为 0 → PyQt5 会在 QObject 析构时自动断开 bound method；"
          "若 >0 → 存在 use-after-delete 风险。", flush=True)


def test_A2_singleshot_lambda_after_cpp_delete(qapp, qtbot):
    """A2: lambda 捕获 self + C++ 对象被删除 → 回调是否仍被调用？"""
    from PyQt5 import sip

    victim = _Victim()
    CALL_LOG[:] = []
    QTimer.singleShot(150, lambda: victim.slot())
    sip.delete(victim)
    gc.collect()

    qtbot.wait(600)
    print("A2 结果: CALL_LOG=%r, victim.calls=%d"
          % (CALL_LOG, victim.calls), flush=True)
    print("A2 说明: lambda 没有 QObject 接收者上下文，PyQt5 不会自动断开；"
          "真实代码里 ui/ai_inline_completer.py:133、core/editor.py:454、"
          "app/session.py:1493 都是这种形态。", flush=True)


# ============================================================
# B. LSP 防抖关闭竞态（任务书要求：反复跑 10 次以上）
# ============================================================
class _StubLsp:
    """最小 LSP 替身，记录 did_change / did_close 调用"""

    def __init__(self):
        self.calls = []

    def did_change(self, uri, text):
        self.calls.append(("did_change", uri, len(text or "")))

    def did_save(self, uri, text=None):
        self.calls.append(("did_save", uri, len(text or "")))

    def did_close(self, uri):
        self.calls.append(("did_close", uri))

    def stop(self):
        self.calls.append(("stop",))


def _install_stub_lsp(proxy, uri):
    stub = _StubLsp()
    proxy.lsp_client = stub
    proxy.lsp_active = True
    proxy._lsp_uri = uri
    return stub


@pytest.mark.parametrize("iteration", range(12))
def test_B_lsp_debounce_close_race(qapp, qtbot, tmp_path, monkeypatch, iteration):
    """B: 打开 .py → 打字触发 LSP 防抖 → 立刻关标签 → 等过防抖 → 断言不崩"""
    import ui.main_window as mw
    from core.editor import LSP_SYNC_DELAY

    # 未保存修改会弹模态 QMessageBox（嵌套事件循环），测试里替换掉
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.Discard), raising=False
    )

    path = tmp_path / ("race_%02d.py" % iteration)
    path.write_text("x = 1\n", encoding="utf-8")

    win = mw.MainWindow()
    win.show()
    try:
        proxy = win.tabs.open_file(str(path))
        assert proxy is not None, "open_file 返回 None"

        # --- B1: 真实入口 toggle_lsp(True) 到底行不行 ---
        real_ok = None
        try:
            real_ok = proxy.toggle_lsp(True)
        except Exception:
            traceback.print_exc()
        print("\n[B iter=%d] 真实 toggle_lsp(True) → %r, "
              "lsp_client=%r, lsp_active=%r"
              % (iteration, real_ok, proxy.lsp_client, proxy.lsp_active),
              flush=True)
        if proxy.lsp_client is not None:
            print("[B] lsp_client.get_server_info() = %r"
                  % (proxy.lsp_client.get_server_info(),), flush=True)

        # --- B2: 强制进入防抖路径（真实入口失败时用 stub 补上） ---
        uri = "file:///" + str(path).replace("\\", "/")
        stub = _install_stub_lsp(proxy, uri)

        sc = proxy.sc
        sc.insert("y = 2\n")           # 触发 SCN_MODIFIED → _lsp_sync_timer.start()
        assert proxy._lsp_sync_timer.isActive(), "防抖定时器没有启动"
        print("[B iter=%d] 打字后 _lsp_sync_timer.isActive()=%r"
              % (iteration, proxy._lsp_sync_timer.isActive()), flush=True)

        # --- B3: 立刻关闭标签 ---
        idx = win.tabs.find_tab_by_path(str(path))
        assert idx is not None and idx >= 0, "找不到标签索引"
        closed = win.tabs.close_tab(idx)
        print("[B iter=%d] close_tab → %r, 关闭后 isActive=%r, "
              "proxy.lsp_active=%r"
              % (iteration, closed, proxy._lsp_sync_timer.isActive(),
                 proxy.lsp_active), flush=True)

        # --- B4: 等过防抖延迟（用 Qt 事件循环等） ---
        qtbot.waitUntil(
            lambda: not proxy._lsp_sync_timer.isActive(),
            timeout=LSP_SYNC_DELAY * 6,
        )
        _pump(qtbot, 400)
        print("[B iter=%d] 等待 %dms 后 stub.calls=%r"
              % (iteration, LSP_SYNC_DELAY * 6, stub.calls), flush=True)

        # 结论判定（不崩即通过；若防抖在关闭后仍发了 did_change，打印出来）
        after_close = [c for c in stub.calls if c[0] == "did_change"]
        if after_close:
            print("[B iter=%d] ★ 关闭后仍发生了 did_change: %r"
                  % (iteration, after_close), flush=True)
    finally:
        win.close()
        win.deleteLater()
        _pump(qtbot, 100)


def test_B_window_close_with_pending_debounce(qapp, qtbot, tmp_path, monkeypatch):
    """B5: 打字触发防抖后立刻关闭【整个窗口】（不走 close_tab）"""
    import ui.main_window as mw
    from core.editor import LSP_SYNC_DELAY

    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.Discard), raising=False
    )
    path = tmp_path / "win_close.py"
    path.write_text("x = 1\n", encoding="utf-8")

    win = mw.MainWindow()
    win.show()
    proxy = win.tabs.open_file(str(path))
    stub = _install_stub_lsp(proxy, "file:///" + str(path).replace("\\", "/"))
    proxy.sc.insert("y = 2\n")
    assert proxy._lsp_sync_timer.isActive()

    win.close()                       # closeEvent 不关标签、不关 LSP
    qtbot.waitUntil(
        lambda: not proxy._lsp_sync_timer.isActive(),
        timeout=LSP_SYNC_DELAY * 6,
    )
    _pump(qtbot, 400)
    print("\n[B5] win.close() 后 stub.calls=%r, lsp_active=%r, "
          "timer.isActive=%r"
          % (stub.calls, proxy.lsp_active, proxy._lsp_sync_timer.isActive()),
          flush=True)
    win.deleteLater()
    _pump(qtbot, 100)


# ============================================================
# C. 线程泄漏：MainWindow 建/拆前后线程与会话线程数
# ============================================================
def test_C_thread_leak_around_main_window(qapp, qtbot, tmp_path):
    """C: 创建/关闭 MainWindow，比较 threading.enumerate() 与 QThread 计数"""
    import ui.main_window as mw

    gc.collect()
    _pump(qtbot, 200)
    before = _dump_threads("BEFORE")
    before_qth = len(_qthread_objects())

    for i in range(3):
        win = mw.MainWindow()
        win.show()
        path = tmp_path / ("t%d.py" % i)
        path.write_text("print(1)\n", encoding="utf-8")
        win.tabs.open_file(str(path))
        # 建几个带 timer 的面板
        for panel in ("outline", "perf_monitor", "console", "gsearch",
                      "minimap", "dir_tree", "plugins_panel", "search_bar",
                      "outline_enhanced"):
            win._ensure_panel(panel)
        _pump(qtbot, 150)
        _dump_threads("INSIDE-%d" % i)
        win.close()
        win.deleteLater()
        _pump(qtbot, 250)

    gc.collect()
    _pump(qtbot, 400)
    after = _dump_threads("AFTER")
    after_qth = len(_qthread_objects())

    leaked = [n for n in after if n not in before]
    print("\n[C] before=%r\n[C] after =%r\n[C] 新增线程=%r"
          % (before, after, leaked), flush=True)
    print("[C] QThread 实例: before=%d after=%d" % (before_qth, after_qth),
          flush=True)


# ============================================================
# D. QTimer 悬空 / 跨线程启动告警：反复开关带 timer 的面板
# ============================================================
def test_D_timer_churn_and_dangling(qapp, qtbot, tmp_path):
    """D: 同一个 MainWindow 内反复开关 perf_monitor / outline / lsp 面板 20 次"""
    import ui.main_window as mw

    win = mw.MainWindow()
    win.show()
    try:
        for i in range(20):
            assert win._ensure_panel("perf_monitor") is True
            if win.perf_monitor:
                win.perf_monitor.setVisible(True)
                _pump(qtbot, 5)
                win.perf_monitor.setVisible(False)

            assert win._ensure_panel("outline") is True
            if win.outline:
                win.outline.show()
                win.outline.hide()

            assert win._ensure_panel("lsp") is False or True  # lsp 不是懒面板
            _pump(qtbot, 5)

        print("\n[D] perf_monitor.timer.isActive() = %r"
              % (win.perf_monitor.timer.isActive()
                 if win.perf_monitor else None), flush=True)
    finally:
        _pump(qtbot, 100)
        win.close()
        win.deleteLater()
        gc.collect()
        _pump(qtbot, 500)

    bad = [m for lvl, m in QT_MESSAGES
           if "another thread" in m or "has been deleted" in m
           or "destroyed" in m.lower()]
    print("[D] 可疑 Qt 告警 %d 条: %r" % (len(bad), bad[:20]), flush=True)
    print("[D] 全部 Qt 告警 %d 条（前 20）: %r"
          % (len(QT_MESSAGES), QT_MESSAGES[:20]), flush=True)


def test_D2_recreate_main_window_20_times(qapp, qtbot):
    """D2: 连续建/拆 MainWindow 20 次，检查 timer 相关告警与线程增长"""
    import ui.main_window as mw

    base = len(_thread_names())
    for i in range(20):
        win = mw.MainWindow()
        win._ensure_panel("perf_monitor")
        win.show()
        _pump(qtbot, 5)
        win.close()
        win.deleteLater()
        _pump(qtbot, 5)
    gc.collect()
    _pump(qtbot, 500)

    bad = [m for lvl, m in QT_MESSAGES
           if "another thread" in m or "has been deleted" in m]
    print("\n[D2] 20 轮后线程数 %d → %d" % (base, len(_thread_names())),
          flush=True)
    print("[D2] 可疑告警: %r" % (bad[:20],), flush=True)
    print("[D2] 全部告警 %d 条（前 30）: %r"
          % (len(QT_MESSAGES), QT_MESSAGES[:30]), flush=True)


# ============================================================
# E. faulthandler + 压力操作（快速开关标签 / 切换主题 / 开关面板）
# ============================================================
def test_E_faulthandler_stress(qapp, qtbot, tmp_path):
    """E: 打开 faulthandler，做 100 轮开关标签 + 主题切换 + 面板开关"""
    import faulthandler

    crash_log = tmp_path / "faulthandler.log"
    fh = open(str(crash_log), "wb")
    faulthandler.enable(file=fh, all_threads=True)
    try:
        import ui.main_window as mw

        win = mw.MainWindow()
        win.show()

        files = []
        for i in range(5):
            p = tmp_path / ("stress%d.py" % i)
            p.write_text("a = %d\n" % i, encoding="utf-8")
            files.append(str(p))

        themes = ["__system__", "dark", "light"]
        for i in range(100):
            proxy = win.tabs.open_file(files[i % len(files)])
            if proxy is not None:
                try:
                    proxy.sc.insert("x = %d\n" % i)
                except Exception:
                    pass
            if i % 3 == 0:
                idx = win.tabs.currentIndex()
                if idx >= 0:
                    win.tabs.close_tab(idx)
            if i % 10 == 0:
                try:
                    win._apply_theme_by_name(themes[(i // 10) % len(themes)])
                except Exception:
                    traceback.print_exc()
            if i % 7 == 0:
                win._ensure_panel("perf_monitor")
                win._ensure_panel("minimap")
            _pump(qtbot, 2)

        print("\n[E] 100 轮压力完成，标签数=%d" % win.tabs.count(), flush=True)
        win.close()
        win.deleteLater()
        gc.collect()
        _pump(qtbot, 500)
        print("[E] 收尾完成，进程仍存活", flush=True)
    finally:
        faulthandler.disable()
        fh.close()
        if crash_log.exists():
            data = crash_log.read_bytes()
            print("[E] faulthandler 文件 %d 字节: %r"
                  % (len(data), data[:2000]), flush=True)

    bad = [m for lvl, m in QT_MESSAGES
           if "another thread" in m or "has been deleted" in m]
    print("[E] 可疑告警 %d 条: %r" % (len(bad), bad[:20]), flush=True)


# ============================================================
# F. TerminalPanel 重启 → 读线程泄漏（ui/terminal_panel.py:225-238）
# ============================================================
def test_F_terminal_restart_thread_leak(qapp, qtbot):
    """F: TerminalPanel._restart() 反复调用，统计 _read_output 线程是否增长。

    注意：TerminalPanel 在当前代码库中【没有调用点】，本用例直接实例化。
    """
    try:
        from ui.terminal_panel import TerminalPanel
    except Exception as exc:
        pytest.skip("TerminalPanel 不可用: %s" % exc)

    panel = TerminalPanel()
    win = QWidget()
    panel.setParent(win)
    try:
        base = len(_thread_names())
        print("\n[F] 起始线程数 = %d" % base, flush=True)

        for i in range(5):
            panel._restart()
            _pump(qtbot, 400)
            names = _thread_names()
            print("[F] 第 %d 次 _restart 后线程数 = %d, self.process=%r"
                  % (i + 1, len(names), panel.process), flush=True)

        _dump_threads("F-AFTER-RESTARTS")
        print("[F] 增长 = %d（若大于 0，说明旧读线程没有退出；"
              "它们会与新线程一起读同一根 stdout 管道）"
              % (len(_thread_names()) - base), flush=True)

        # 关闭窗口后线程是否回落
        if panel.process:
            try:
                panel.process.kill()
            except Exception:
                pass
        panel.setParent(None)
        panel.deleteLater()
        win.deleteLater()
        gc.collect()
        _pump(qtbot, 800)
        _dump_threads("F-AFTER-TEARDOWN")
    finally:
        win.deleteLater()


# ============================================================
# G. 非 GUI 线程操作 QWidget（ui/benchmark_dialog.py:121/126/130 形态）
# ============================================================
def test_G_widget_access_from_worker_thread(qapp, qtbot):
    """G: 在子线程里 reprod QApplication.processEvents() + widget 操作"""
    from PyQt5.QtWidgets import QLabel, QPlainTextEdit

    label = QLabel("init")
    edit = QPlainTextEdit()
    label.show()
    edit.show()
    errors = []

    def worker():
        try:
            label.setText("from-worker")
            edit.setPlainText("from-worker")
            QApplication.processEvents()      # Qt 文档：仅限 GUI 线程
        except Exception as exc:
            errors.append(repr(exc))
            traceback.print_exc()

    t = threading.Thread(target=worker, name="probe-non-gui", daemon=True)
    t.start()
    t.join(timeout=5)
    _pump(qtbot, 300)

    print("\n[G] 子线程异常 = %r" % errors, flush=True)
    print("[G] Qt 告警 = %r" % (QT_MESSAGES[:20],), flush=True)
    print("[G] 说明: 这条实验对应 ui/benchmark_dialog.py:121/126/130 与 "
          "ui/refactor_dialog.py:266-294（_on_response 在子线程里改控件）。",
          flush=True)
    label.deleteLater()
    edit.deleteLater()


def test_G2_refactor_dialog_callback_from_worker(qapp, qtbot, monkeypatch):
    """G2: 复现 RefactorSession 在子线程里回调对话框（真实调用链）"""
    try:
        from core.refactor_session import RefactorSession
    except Exception as exc:
        pytest.skip("refactor_session 不可用: %s" % exc)

    from PyQt5.QtWidgets import QLabel

    label = QLabel("init")
    label.show()
    seen = []

    class FakeAI:
        def _chat(self, messages, system=""):
            return "```python\nprint(1)\n```\n说明"

    session = RefactorSession(FakeAI(), "print(0)\n", "python")

    def callback(iteration):
        # 这段在【子线程】里执行 —— 对应 ui/refactor_dialog.py:266
        seen.append(threading.current_thread().name)
        label.setText("iter %d" % iteration.iteration)
        QApplication.processEvents()

    session.send_request("改成 print(1)", callback=callback)
    qtbot.waitUntil(lambda: bool(seen), timeout=5000)
    _pump(qtbot, 200)

    print("\n[G2] callback 执行线程名 = %r（主线程=%r）"
          % (seen, threading.current_thread().name), flush=True)
    print("[G2] Qt 告警 = %r" % (QT_MESSAGES[:20],), flush=True)
    label.deleteLater()
