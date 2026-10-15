# -*- coding: utf-8 -*-
"""D3：真调试器 + 断点标记测试。

覆盖 6 条用户路径：

1. 设断点 → 启动调试 → 停在断点行（并在编辑器里高亮）
   `TestBreakpoints*`、`TestDriverInternals`、`TestRealDebugRun`
2. 单步 over / into / out —— `TestSessionCommands`、`TestRealDebugRun`
3. 继续运行 —— `TestSessionCommands`、`TestRealDebugRun`
4. 查看局部变量 / 调用栈 —— `TestDriverInternals`、`TestPanel`
5. 终止且**不留孤儿进程** —— `TestSessionStop`、`TestRealDebugRun`
6. 错误场景（后端不可用 / 未保存 / 非 Python）给用户可见提示
   —— `TestBackendProbe`、`TestPluginGuards`

以及 Lead 追加的 `external_change_detected` 接线回归（`TestExternalChangeWiring`）。
"""
import importlib.util
import io
import json
import os
import queue
import subprocess
import sys
import threading
import time
import types

import pytest
from PyQt5.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt5.QtGui import QFontDatabase, QKeyEvent


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.path.join(ROOT, "plugins", "python_debugger")
PLUGIN_INIT = os.path.join(PLUGIN_DIR, "__init__.py")
DRIVER_PATH = os.path.join(PLUGIN_DIR, "driver.py")

_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\consola.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
)


# ============================================================
# fixtures / 加载工具
# ============================================================
@pytest.fixture(scope="session", autouse=True)
def _inject_fonts(qapp):
    """offscreen 下注入字体，避免缺字体导致 segfault。"""
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                QFontDatabase.addApplicationFont(path)
            except Exception:
                pass
    yield


def load_module_by_path(name, path):
    """按文件路径加载模块（与 PluginLoader 的做法一致）。"""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


@pytest.fixture(scope="module")
def plugin_module(qapp):
    """按 **PluginLoader 的方式**加载插件。

    PluginLoader 用 `spec_from_file_location` + 合成模块名加载
    `plugins/*/__init__.py`，插件因此没有包上下文；本 fixture 复刻这条
    路径，顺便证明插件里的子模块加载（`_load_sibling`）是有效的。

    依赖 `qapp`：插件里的 DebugSession / DebuggerPanel 都是 QObject，
    保证测试期间存在 QApplication。
    """
    return load_module_by_path("qingcao_plugin_python_debugger", PLUGIN_INIT)


@pytest.fixture(scope="module")
def driver():
    """加载驱动脚本模块（driver.py 同样是脚本，无包上下文）。"""
    return load_module_by_path(
        "qingcao_plugin_python_debugger_driver_for_test", DRIVER_PATH
    )


@pytest.fixture
def session(qapp, plugin_module):
    """未启动的 DebugSession（不发子进程）。"""
    return plugin_module.DebugSession()


# ============================================================
# 测试替身
# ============================================================
class FakeProcess:
    """模拟 subprocess.Popen 的最小接口（不真起进程）。

    `wait_plan` 用来驱动"优雅退出 / 需要 terminate / 需要 kill"三条路径：
    "exit" → wait 立刻返回；"timeout" → 抛 TimeoutExpired。
    """

    def __init__(self, returncode=None, wait_plan=None):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self._returncode = returncode
        self._wait_plan = list(wait_plan or [])
        self.wait_calls = []
        self.terminate_calls = 0
        self.kill_calls = 0

    def poll(self):
        return self._returncode

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        if self._wait_plan:
            action = self._wait_plan.pop(0)
            if action == "timeout":
                raise subprocess.TimeoutExpired("cmd", timeout or 0)
            if action == "exit":
                self._returncode = 0
                return 0
        return self._returncode

    def terminate(self):
        self.terminate_calls += 1
        # 真实世界里 terminate 之后进程会退出（这里模拟 SIGTERM 的退出码）
        self._returncode = -15

    def kill(self):
        self.kill_calls += 1
        self._returncode = -9


class BrokenStdin:
    def write(self, _data):
        raise OSError("管道已关闭")

    def flush(self):
        raise OSError("管道已关闭")

    def close(self):
        pass


class FakeProxy:
    """EditorProxy 的替身（插件逻辑测试用）。"""

    def __init__(self, filepath=None, modified=False, breakpoints=None):
        self.document = types.SimpleNamespace(filepath=filepath)
        self.is_modified = modified
        self.breakpoint_lines = list(breakpoints or [])
        self.toggled = []
        self.highlighted = []
        self.cleared = 0
        self.breakpoints_changed = _Signal()

    def get_breakpoints(self):
        return sorted(self.breakpoint_lines)

    def toggle_breakpoint(self, line=None):
        if line is None:
            line = 0
        if line in self.breakpoint_lines:
            self.breakpoint_lines.remove(line)
        else:
            self.breakpoint_lines.append(line)
        self.toggled.append(line)
        return True

    def clear_breakpoints(self):
        count = len(self.breakpoint_lines)
        self.breakpoint_lines = []
        return count

    def highlight_debug_line(self, line):
        self.highlighted.append(line)
        return True

    def clear_debug_line(self):
        self.cleared += 1


class _Signal:
    """极简信号替身（只支持 connect，不依赖 Qt）。"""

    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self, *args):
        for slot in list(self.slots):
            slot(*args)


class FakeSession(QObject):
    """DebugSession 的替身：信号签名与真实实现一致。"""

    output_received = pyqtSignal(str, str)
    break_hit = pyqtSignal(str, int)
    finished = pyqtSignal(int)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.started = []
        self.breakpoint_updates = []
        self.commands = []
        self._running = True
        self.last_paused = {"event": "break", "file": "x.py", "line": 1}

    @property
    def is_running(self):
        return self._running

    def start(self, script, args=None, cwd=None):
        self.started.append(script)
        return True

    def set_breakpoints(self, files):
        self.breakpoint_updates.append(files)
        return True

    def continue_(self):
        self.commands.append("continue")
        return True

    def step_over(self):
        self.commands.append("step_over")
        return True

    def step_into(self):
        self.commands.append("step_into")
        return True

    def step_out(self):
        self.commands.append("step_out")
        return True

    def request_locals(self):
        self.commands.append("locals")
        return True

    def request_stack(self):
        self.commands.append("stack")
        return True

    def stop(self):
        self.commands.append("stop")
        self._running = False
        return True


class FakeApi:
    """PluginAPI 的替身：只记录不弹窗。"""

    def __init__(self):
        self.menus = []
        self.statuses = []
        self.messages = []
        self.logs = []
        self.editors = []
        self.filepath = None
        self.save_result = True
        self.save_calls = 0

    # ---- 菜单 / 日志 / 提示 ----
    def add_menu(self, path, callback, shortcut=None):
        entry = {"path": path, "callback": callback, "shortcut": shortcut}
        self.menus.append(entry)
        return entry

    def log(self, message, level="info"):
        self.logs.append((level, message))

    def show_status(self, message, timeout=3000, level="info"):
        self.statuses.append((level, str(message)))

    def show_message(self, title, message, icon="info"):
        self.messages.append((title, str(message), icon))

    # ---- 编辑器 ----
    def current_editor(self):
        return self.editors[0] if self.editors else None

    def all_editors(self):
        return list(self.editors)

    def get_current_filepath(self):
        return self.filepath

    def get_main_window(self):
        return None

    def save_current_file(self):
        self.save_calls += 1
        return self.save_result

    def ask_string(self, *_args, **_kwargs):
        return "", False

    # ---- 断言辅助 ----
    def menu_paths(self):
        return [entry["path"] for entry in self.menus]

    def status_text(self):
        return " | ".join(text for _level, text in self.statuses)

    def message_text(self):
        return "\n".join(text for _t, text, _i in self.messages)


def make_plugin(plugin_module, api=None):
    plugin = plugin_module.Plugin()
    plugin.api = api or FakeApi()
    plugin._session = None
    plugin._panel = None
    plugin._watched_proxies = set()
    return plugin


# ============================================================
# 1. 断点（宿主侧）
# ============================================================
class TestBreakpoints:
    def test_proxy_toggle_on_bare_scintilla(self, qapp):
        """裸 QsciScintilla（无 ui/editor_view 的包装）也能增删查。"""
        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy

        sc = QsciScintilla()
        sc.setText("a\nb\nc\nd\n")
        proxy = EditorProxy(sc, Document())

        assert proxy.get_breakpoints() == []
        assert proxy.toggle_breakpoint(2) is True
        assert proxy.get_breakpoints() == [2]
        assert proxy.toggle_breakpoint(2) is True
        assert proxy.get_breakpoints() == []

    def test_proxy_breakpoints_changed_signal(self, qapp):
        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy

        sc = QsciScintilla()
        sc.setText("a\nb\nc\n")
        proxy = EditorProxy(sc, Document())
        seen = []
        proxy.breakpoints_changed.connect(seen.append)

        proxy.toggle_breakpoint(1)
        proxy.toggle_breakpoint(2)
        assert seen[-1] == [1, 2]

        assert proxy.clear_breakpoints() == 2
        assert seen[-1] == []
        assert proxy.get_breakpoints() == []

    def test_editor_widget_breakpoints_and_visibility(self, qapp):
        """EditorWidget：断点可读写，且**装订线真的显示得出来**。"""
        from ui.editor_view import (
            MARKER_BOOKMARK,
            MARKER_BREAKPOINT,
            EditorWidget,
        )

        editor = EditorWidget()
        try:
            editor.setText("a\nb\nc\nd\ne\n")
            assert editor.get_breakpoints() == []
            assert editor._toggle_breakpoint_at_line(3) is True
            assert editor.get_breakpoints() == [3]
            assert editor._toggle_breakpoint_at_line(3) is True
            assert editor.get_breakpoints() == []

            # "能看到"的最低条件：存在一个显示该 marker 的边距
            assert editor.marginWidth(1) > 0, "断点装订线宽度为 0，断点不可见"
            mask = editor.marginMarkerMask(1)
            assert mask & (1 << MARKER_BREAKPOINT), (
                "margin 1 没有把断点 marker 纳入掩码，红点不会显示"
            )
            assert mask & (1 << MARKER_BOOKMARK), "margin 1 也应显示书签"
        finally:
            editor.deleteLater()

    def test_out_of_range_breakpoint_is_rejected(self, qapp):
        """越界行号必须返回 False（markerAdd 对越界行是静默失败）。"""
        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy
        from ui.editor_view import EditorWidget

        # 空编辑器只有 1 行：行 3 不存在
        editor = EditorWidget()
        try:
            assert editor._toggle_breakpoint_at_line(3) is False
            assert editor.get_breakpoints() == []
            assert editor.proxy.toggle_breakpoint(3) is False
            # 行 0 存在，可以设
            assert editor.proxy.toggle_breakpoint(0) is True
            assert editor.get_breakpoints() == [0]
        finally:
            editor.deleteLater()

        sc = QsciScintilla()
        sc.setText("only\n")
        proxy = EditorProxy(sc, Document())
        lines = sc.lines()
        assert proxy.toggle_breakpoint(lines) is False, "行号 == lines() 越界"
        assert proxy.add_breakpoint(lines + 5) is False
        assert proxy.get_breakpoints() == []

    def test_editor_widget_proxy_round_trip(self, qapp):
        from ui.editor_view import EditorWidget

        editor = EditorWidget()
        try:
            editor.setText("a\nb\nc\n")
            editor.proxy.toggle_breakpoint(1)
            assert editor.get_breakpoints() == [1]
            assert editor.proxy.get_breakpoints() == [1]
            editor.clear_breakpoints()
            assert editor.proxy.get_breakpoints() == []
        finally:
            editor.deleteLater()

    def test_margin_click_toggles_breakpoint(self, qapp):
        """装订线（margin 1）单击切换断点；其它边距不动它。

        行号边距（margin 0）刻意保持不可点 —— 那里已有"双击切换书签"。
        """
        from ui.editor_view import EditorWidget

        editor = EditorWidget()
        try:
            editor.setText("a\nb\nc\nd\ne\nf\ng\n")
            editor._on_margin_clicked(0, 2, None)   # 行号边距：不动断点
            assert editor.get_breakpoints() == [], (
                "行号边距不应切换断点（会与双击加书签冲突）"
            )
            editor._on_margin_clicked(1, 5, None)   # 断点装订线
            assert editor.get_breakpoints() == [5]
            editor._on_margin_clicked(1, 5, None)
            assert editor.get_breakpoints() == []
            editor._on_margin_clicked(2, 7, None)   # 折叠边距
            assert editor.get_breakpoints() == []
            editor._on_margin_clicked(1, 999, None)  # 越界行
            assert editor.get_breakpoints() == []
        finally:
            editor.deleteLater()

    def test_f9_key_toggles_breakpoint(self, qapp):
        from ui.editor_view import EditorWidget

        editor = EditorWidget()
        try:
            event = QKeyEvent(QEvent.KeyPress, Qt.Key_F9, Qt.NoModifier)
            editor.keyPressEvent(event)
            assert editor.get_breakpoints() == [0]
            editor.keyPressEvent(
                QKeyEvent(QEvent.KeyPress, Qt.Key_F9, Qt.NoModifier)
            )
            assert editor.get_breakpoints() == []
        finally:
            editor.deleteLater()

    def test_debug_line_highlight(self, qapp):
        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy
        from ui.editor_view import MARKER_DEBUG_LINE

        sc = QsciScintilla()
        sc.setText("a\nb\nc\nd\ne\n")
        proxy = EditorProxy(sc, Document())

        assert proxy.highlight_debug_line(3) is True
        assert sc.markersAtLine(3) & (1 << MARKER_DEBUG_LINE)
        proxy.clear_debug_line()
        assert not (sc.markersAtLine(3) & (1 << MARKER_DEBUG_LINE))


# ============================================================
# 2. 会话命令构造（不真起进程）
# ============================================================
class TestSessionCommands:
    def test_build_driver_command(self, plugin_module, tmp_path):
        mod = plugin_module._session_module
        script = tmp_path / "demo.py"
        script.write_text("print(1)\n", encoding="utf-8")

        command = mod.build_driver_command(
            str(script), ["a", "b"], python="PY", driver="DRV"
        )
        assert command == ["PY", "-u", "DRV", str(script), "a", "b"]

        default = mod.build_driver_command(str(script))
        assert default[1] == "-u"
        assert default[2].endswith("driver.py")
        assert default[3] == str(script)

    def test_line_number_conversion(self, plugin_module):
        mod = plugin_module._session_module
        # 编辑器 0 基 → Python 1 基
        assert mod.to_python_lines([0, 2, 2, -1, "x"]) == [1, 3]
        # Python 1 基 → 编辑器 0 基
        assert mod.to_editor_line(1) == 0
        assert mod.to_editor_line(5) == 4
        assert mod.to_editor_line(0) == 0
        assert mod.to_editor_line("bad") == 0

    def test_set_breakpoints_payload(self, session):
        fake = FakeProcess()
        session._proc = fake
        assert session.set_breakpoints({"/tmp/a.py": [0, 4], "/tmp/b.py": []})
        payload = json.loads(fake.stdin.getvalue().strip())
        assert payload == {
            "cmd": "set_breakpoints",
            "files": {"/tmp/a.py": [1, 5]},
        }

    @pytest.mark.parametrize("method,expected", [
        ("continue_", "continue"),
        ("step_over", "step_over"),
        ("step_into", "step_into"),
        ("step_out", "step_out"),
        ("pause", "pause"),
        ("request_stack", "stack"),
        ("request_locals", "locals"),
        ("quit", "quit"),
    ])
    def test_command_wrappers(self, session, method, expected):
        fake = FakeProcess()
        session._proc = fake
        assert getattr(session, method)() is True
        assert json.loads(fake.stdin.getvalue().strip()) == {"cmd": expected}

    def test_evaluate_command(self, session):
        fake = FakeProcess()
        session._proc = fake
        session.evaluate("a + b")
        assert json.loads(fake.stdin.getvalue().strip()) == {
            "cmd": "eval", "expr": "a + b"
        }

    def test_send_without_process_fails_cleanly(self, session):
        errors = []
        session.failed.connect(errors.append)
        assert session.send({"cmd": "continue"}) is False
        assert session.last_error
        assert errors == []

    def test_start_refuses_bad_backend(self, session, monkeypatch,
                                       plugin_module, tmp_path):
        """后端不可用 → 不启动进程，给出**用户可见**提示。"""
        errors = []
        session.failed.connect(errors.append)
        monkeypatch.setattr(
            plugin_module._session_module,
            "check_backend",
            lambda **_kw: (False, "调试后端不可用：未找到 Python 解释器"),
        )
        script = tmp_path / "a.py"
        script.write_text("print(1)\n", encoding="utf-8")

        assert session.start(str(script)) is False
        assert session._proc is None
        assert errors and "调试后端不可用" in errors[0]
        assert errors[0] == session.last_error

    def test_start_rejects_missing_script(self, session, tmp_path):
        errors = []
        session.failed.connect(errors.append)
        assert session.start(str(tmp_path / "nope.py")) is False
        assert errors and "找不到要调试的脚本" in errors[0]


# ============================================================
# 3. 协议解析
# ============================================================
class TestSessionProtocol:
    def test_ready_event_sets_running(self, session):
        payload = session.handle_line(
            json.dumps({"event": "ready", "file": "/a.py"})
        )
        assert payload["event"] == "ready"
        assert session.state == "running"

    def test_break_event_reports_editor_line(self, session):
        hits = []
        events = []
        session.break_hit.connect(lambda f, line: hits.append((f, line)))
        session.event_received.connect(events.append)

        session.handle_line(json.dumps({
            "event": "break",
            "reason": "breakpoint",
            "file": "C:/p/a.py",
            "line": 7,
            "locals": {"a": "1"},
            "stack": [{"name": "add", "file": "C:/p/a.py", "line": 7}],
        }))

        assert hits == [("C:/p/a.py", 6)], "break_hit 必须给出 0 基行号"
        assert session.state == "paused"
        assert session.last_paused["line"] == 7
        assert len(events) == 1

    def test_output_event(self, session):
        outputs = []
        session.output_received.connect(
            lambda stream, text: outputs.append((stream, text))
        )
        session.handle_line(json.dumps({
            "event": "output", "stream": "stdout", "text": "hello\n"
        }))
        assert outputs == [("stdout", "hello\n")]

    def test_error_event_is_user_visible(self, session):
        errors = []
        session.failed.connect(errors.append)
        session.handle_line(json.dumps({
            "event": "error", "message": "未知命令: xxx"
        }))
        assert errors == ["未知命令: xxx"]
        assert session.last_error == "未知命令: xxx"

    def test_exit_event_finishes_once(self, session):
        codes = []
        session.finished.connect(codes.append)
        session.handle_line(json.dumps({"event": "exit", "code": 3}))
        session.handle_line(json.dumps({"event": "exit", "code": 3}))
        assert codes == [3], "finished 只应发一次"
        assert session.state == "stopped"

    def test_malformed_line_does_not_crash(self, session):
        outputs = []
        session.output_received.connect(
            lambda stream, text: outputs.append((stream, text))
        )
        assert session.handle_line("这不是 JSON") is None
        assert session.handle_line("[1, 2, 3]") is None
        assert outputs and all(stream == "stderr" for stream, _ in outputs)

    def test_exception_event_marks_paused(self, session):
        errors = []
        session.failed.connect(errors.append)
        session.handle_line(json.dumps({
            "event": "exception",
            "type": "ZeroDivisionError",
            "message": "division by zero",
        }))
        assert session.state == "paused"
        assert errors and "ZeroDivisionError" in errors[0]


# ============================================================
# 4. 终止：优雅退出 / terminate / kill —— 不留孤儿
# ============================================================
class TestSessionStop:
    def test_graceful_quit(self, session):
        fake = FakeProcess(returncode=None, wait_plan=["exit"])
        session._proc = fake

        assert session.stop() is True
        assert fake.terminate_calls == 0
        assert fake.kill_calls == 0
        assert fake.wait_calls, "必须 wait 确认退出"
        assert fake.stdin.closed and fake.stdout.closed and fake.stderr.closed
        assert session.state == "stopped"
        assert session._proc is None

    def test_terminate_then_kill_when_stubborn(self, session):
        """quit 无效 → terminate；terminate 也无效 → kill（杜绝孤儿）。"""
        fake = FakeProcess(returncode=None, wait_plan=["timeout", "timeout"])
        session._proc = fake

        finished = []
        session.finished.connect(finished.append)

        assert session.stop() is True
        assert fake.terminate_calls == 1
        assert fake.kill_calls == 1, "必须调用 kill，否则留下孤儿进程"
        assert session._proc is None
        assert finished, "强制终止后也要发 finished"

    def test_broken_stdin_still_terminates(self, session):
        fake = FakeProcess(returncode=None, wait_plan=["timeout"])
        fake.stdin = BrokenStdin()
        session._proc = fake
        assert session.stop() is True
        assert fake.terminate_calls == 1

    def test_stop_without_process(self, session):
        assert session.stop() is True
        assert session.state == "stopped"

    def test_stop_on_already_exited_process(self, session):
        fake = FakeProcess(returncode=5)
        session._proc = fake
        assert session.stop() is True
        assert fake.kill_calls == 0
        assert fake.terminate_calls == 0

    def test_is_running_tracks_poll(self, session):
        fake = FakeProcess(returncode=None)
        session._proc = fake
        assert session.is_running is True
        fake._returncode = 0
        assert session.is_running is False


# ============================================================
# 5. 驱动内部（不真起进程）
# ============================================================
def _capture_frame(marker=7, text="hi"):
    """返回自身帧，用于测试帧内省。"""
    return sys._getframe()   # noqa: SLF001 - 测试取帧的标准做法


class TestDriverInternals:
    def test_emit_never_exits_the_host_process_in_tests(self, driver,
                                                        monkeypatch):
        """单测进程里 emit 写失败**不得** os._exit（否则会杀掉 pytest）。

        驱动脚本用"协议流断开 → os._exit(0)"做孤儿防护；该行为只在
        main() 真正跑起来后才启用（`_EXIT_ON_BROKEN_PIPE`）。
        """
        assert driver._EXIT_ON_BROKEN_PIPE is False, (
            "默认必须是 False，否则 import 本模块的测试进程可能被误杀"
        )

        class _Boom:
            def write(self, _data):
                raise OSError("broken pipe")

            def flush(self):
                raise OSError("broken pipe")

        monkeypatch.setattr(driver, "_REAL_STDOUT", _Boom())
        driver.emit({"event": "test"})   # 不得抛异常、不得退出进程

    def test_format_value(self, driver):
        assert driver.format_value(1) == "1"
        assert driver.format_value("hi") == "'hi'"
        long_text = driver.format_value("x" * 500)
        assert long_text.endswith("…")
        assert len(long_text) <= 201

    def test_frame_locals_and_stack(self, driver):
        debugger = driver.JsonDebugger(queue.Queue())
        frame = _capture_frame(marker=42, text="hello")

        values = debugger.frame_locals(frame)
        assert values["marker"] == "42"
        assert values["text"] == "'hello'"

        stack = debugger.stack_frames(frame)
        assert stack, "调用栈不能为空"
        assert stack[0]["name"] == "_capture_frame"
        assert all("file" in item and "line" in item for item in stack)

    def test_safe_eval(self, driver):
        debugger = driver.JsonDebugger(queue.Queue())
        frame = _capture_frame(marker=42)
        assert debugger.safe_eval(frame, "marker + 1") == "43"
        assert debugger.safe_eval(frame, "") == ""
        assert debugger.safe_eval(frame, "boom").startswith("<错误")

    def test_set_breaks_records_only_successful_lines(self, driver, tmp_path):
        """回归：`bdb.set_break` 的返回语义是"**None = 成功**、字符串 = 失败"。

        早先写成 `if bp is not None` 时只记录了失败的行、丢掉了成功的行，
        导致**所有断点在真实运行里失效**（Lead 实测确认）。本用例直接卡住
        这个方向：生效的行必须在 `applied` 里，不存在的行/文件必须不在。
        """
        script = tmp_path / "ok.py"
        script.write_text("a = 1\nb = 2\n", encoding="utf-8")
        missing = tmp_path / "missing.py"

        debugger = driver.JsonDebugger(queue.Queue())
        applied = debugger.set_breaks({
            str(script): [1, 999],
            str(missing): [1],
        })

        canonical = debugger.canonic(str(script))
        assert applied == {canonical: [1]}, (
            "只应记录真正生效的断点；实际 %r" % (applied,)
        )
        assert 999 not in debugger.breaks.get(canonical, [])
        assert debugger.canonic(str(missing)) not in debugger.breaks

    def test_set_breaks_filters_missing_lines(self, driver, tmp_path):
        script = tmp_path / "target.py"
        script.write_text("a = 1\nb = 2\n", encoding="utf-8")
        debugger = driver.JsonDebugger(queue.Queue())

        applied = debugger.set_breaks({
            str(script): [1, 2, 999],
            str(tmp_path / "missing.py"): [1],
        })
        canonical = debugger.canonic(str(script))
        assert applied.get(canonical) == [1, 2]
        assert len(applied) == 1, "不存在的文件不得进入生效列表"
        assert debugger.breakpoints_at(_capture_frame()) is False

    def test_pause_flag_is_one_shot(self, driver):
        """暂停请求只生效一次，随后自动清除"""
        debugger = driver.JsonDebugger(queue.Queue())
        frame = _capture_frame()

        assert debugger._should_stop(frame) is False

        debugger._pause_requested = True
        assert debugger._should_stop(frame) is True
        assert debugger._forced_reason == "pause"
        # 一次性：消费后不再因为 pause 停下
        assert debugger._pause_requested is False
        assert debugger._should_stop(frame) is False

    def test_stepping_modes(self, driver):
        debugger = driver.JsonDebugger(queue.Queue())
        frame = _capture_frame()
        debugger._mode = driver.JsonDebugger.MODE_NEXT
        debugger._step_frame = frame
        assert debugger._should_stop(frame) is True
        assert debugger._should_stop(object()) is False

        debugger._mode = driver.JsonDebugger.MODE_STEP
        assert debugger._should_stop(object()) is True

        debugger._mode = driver.JsonDebugger.MODE_CONTINUE
        assert debugger._should_stop(frame) is False


# ============================================================
# 6. 后端探测（"未安装依赖"这一类失败）
# ============================================================
class TestBackendProbe:
    def test_real_backend_is_available(self, plugin_module):
        ok, message = plugin_module.check_backend()
        assert ok is True, message
        assert message == ""

    def test_missing_interpreter_and_driver_reported(self, plugin_module):
        ok, message = plugin_module.check_backend(
            python="/definitely/not/python", driver="/definitely/not/driver.py"
        )
        assert ok is False
        assert "调试后端不可用" in message
        assert "/definitely/not/python" in message
        assert "/definitely/not/driver.py" in message
        assert "标准库 bdb" in message, "应说明本后端无需第三方依赖"

    def test_driver_path_points_to_real_file(self, plugin_module):
        mod = plugin_module._session_module
        assert os.path.isfile(mod.driver_path())
        assert mod.driver_path().endswith("driver.py")


# ============================================================
# 7. 插件层：错误场景用户可见
# ============================================================
class TestPluginGuards:
    def test_menus_are_registered(self, plugin_module):
        api = FakeApi()
        plugin = make_plugin(plugin_module, api)
        plugin.on_activate()

        paths = api.menu_paths()
        for expected in (
            "工具/Python 调试/调试当前文件",
            "工具/Python 调试/继续",
            "工具/Python 调试/单步跳过 (over)",
            "工具/Python 调试/单步进入 (into)",
            "工具/Python 调试/单步跳出 (out)",
            "工具/Python 调试/切换断点（F9 或单击行号）",
            "工具/Python 调试/终止调试",
        ):
            assert expected in paths, f"缺少菜单项 {expected}"

    def test_shortcuts_do_not_collide_with_host(self, plugin_module):
        """插件快捷键不得占用宿主的 F5 / F9 / F11 / F12。"""
        api = FakeApi()
        plugin = make_plugin(plugin_module, api)
        plugin.on_activate()

        used = {e["shortcut"] for e in api.menus if e["shortcut"]}
        assert used, "插件应当注册快捷键"
        assert used.isdisjoint({"F5", "F9", "F11", "Shift+F11", "F12"})
        assert len(used) == len([e for e in api.menus if e["shortcut"]]), (
            "插件内部快捷键也不允许重复"
        )

    def test_no_editor(self, plugin_module):
        api = FakeApi()
        plugin = make_plugin(plugin_module, api)
        assert plugin.debug_current() is False
        assert "没有打开的编辑器" in api.status_text() + api.message_text()

    def test_non_python_file_is_rejected(self, plugin_module):
        api = FakeApi()
        api.filepath = os.path.join(ROOT, "README.md")
        api.editors = [FakeProxy(filepath=api.filepath)]
        plugin = make_plugin(plugin_module, api)

        assert plugin.debug_current() is False
        text = api.status_text() + api.message_text()
        assert "只有 Python 文件" in text

    def test_unsaved_file_is_rejected_when_save_fails(self, plugin_module,
                                                     tmp_path):
        script = tmp_path / "demo.py"
        script.write_text("print(1)\n", encoding="utf-8")
        api = FakeApi()
        api.filepath = str(script)
        api.save_result = False
        api.editors = [FakeProxy(filepath=str(script), modified=True)]
        plugin = make_plugin(plugin_module, api)

        assert plugin.debug_current() is False
        assert api.save_calls == 1, "应先尝试自动保存"
        text = api.status_text() + api.message_text()
        assert "Ctrl+S" in text

    def test_untitled_buffer_is_rejected(self, plugin_module):
        api = FakeApi()
        api.filepath = None
        api.editors = [FakeProxy(filepath=None)]
        plugin = make_plugin(plugin_module, api)
        assert plugin.debug_current() is False
        assert "请先保存文件" in api.status_text() + api.message_text()

    def test_backend_failure_is_user_visible(self, plugin_module, monkeypatch,
                                             tmp_path):
        script = tmp_path / "demo.py"
        script.write_text("print(1)\n", encoding="utf-8")
        api = FakeApi()
        api.filepath = str(script)
        api.editors = [FakeProxy(filepath=str(script))]
        plugin = make_plugin(plugin_module, api)

        monkeypatch.setattr(
            plugin_module, "check_backend",
            lambda **kw: (False, "调试后端不可用：未找到 Python 解释器"),
        )
        assert plugin.debug_current() is False
        text = api.status_text() + api.message_text()
        assert "调试后端不可用" in text
        assert any(level == "error" for level, _ in api.statuses)

    def test_modified_file_is_autosaved_before_debug(self, plugin_module,
                                                    monkeypatch, tmp_path):
        script = tmp_path / "demo.py"
        script.write_text("print(1)\n", encoding="utf-8")
        api = FakeApi()
        api.filepath = str(script)
        api.save_result = True
        api.editors = [FakeProxy(filepath=str(script), modified=True)]

        plugin = make_plugin(plugin_module, api)
        monkeypatch.setattr(plugin_module, "DebugSession", FakeSession)
        monkeypatch.setattr(
            plugin_module, "check_backend", lambda **kw: (True, "")
        )
        monkeypatch.setattr(plugin, "show_panel", lambda: None)

        assert plugin.debug_current() is True
        assert api.save_calls == 1


# ============================================================
# 8. 插件层：调试控制与断点下发
# ============================================================
class TestPluginDebugFlow:
    def _plugin_with_session(self, plugin_module, monkeypatch, tmp_path,
                             breakpoints=None):
        script = tmp_path / "demo.py"
        script.write_text("print(1)\n", encoding="utf-8")
        api = FakeApi()
        api.filepath = str(script)
        proxy = FakeProxy(filepath=str(script), breakpoints=breakpoints)
        api.editors = [proxy]
        plugin = make_plugin(plugin_module, api)

        monkeypatch.setattr(plugin_module, "DebugSession", FakeSession)
        monkeypatch.setattr(
            plugin_module, "check_backend", lambda **kw: (True, "")
        )
        monkeypatch.setattr(plugin, "show_panel", lambda: None)
        return plugin, api, proxy, script

    def test_start_pushes_breakpoints(self, plugin_module, monkeypatch,
                                      tmp_path):
        plugin, _api, _proxy, script = self._plugin_with_session(
            plugin_module, monkeypatch, tmp_path, breakpoints=[1, 4]
        )
        assert plugin.debug_current() is True
        session = plugin._session
        assert session.started == [str(script)]
        assert session.breakpoint_updates[-1] == {str(script): [1, 4]}

    def test_break_highlights_line_and_focuses(self, plugin_module, monkeypatch,
                                               tmp_path):
        plugin, _api, proxy, script = self._plugin_with_session(
            plugin_module, monkeypatch, tmp_path, breakpoints=[2]
        )
        assert plugin.debug_current() is True
        session = plugin._session

        session.break_hit.emit(str(script), 3)
        assert proxy.highlighted == [3]
        assert proxy.cleared >= 1, "高亮新行前应先清掉旧高亮"

    def test_step_commands_reach_session(self, plugin_module, monkeypatch,
                                         tmp_path):
        plugin, api, _proxy, _script = self._plugin_with_session(
            plugin_module, monkeypatch, tmp_path
        )
        assert plugin.debug_current() is True
        session = plugin._session

        assert plugin.debug_continue() is True
        assert plugin.debug_step_over() is True
        assert plugin.debug_step_into() is True
        assert plugin.debug_step_out() is True
        assert session.commands == [
            "continue", "step_over", "step_into", "step_out"
        ]

        assert plugin.show_locals() is True
        assert plugin.show_stack() is True
        assert session.commands[-2:] == ["locals", "stack"]

    def test_control_without_session_is_reported(self, plugin_module):
        api = FakeApi()
        plugin = make_plugin(plugin_module, api)
        assert plugin.debug_continue() is False
        assert "没有正在进行的调试会话" in api.status_text()

    def test_finished_clears_highlight(self, plugin_module, monkeypatch,
                                       tmp_path):
        plugin, api, proxy, _script = self._plugin_with_session(
            plugin_module, monkeypatch, tmp_path, breakpoints=[1]
        )
        assert plugin.debug_current() is True
        session = plugin._session
        session.finished.emit(0)
        assert proxy.cleared >= 1
        assert plugin._session is None
        assert "调试结束" in api.status_text()

    def test_stop_debug_calls_session_stop(self, plugin_module, monkeypatch,
                                           tmp_path):
        plugin, _api, _proxy, _script = self._plugin_with_session(
            plugin_module, monkeypatch, tmp_path
        )
        assert plugin.debug_current() is True
        session = plugin._session
        assert plugin.stop_debug() is True
        assert "stop" in session.commands
        assert plugin._session is None

    def test_breakpoint_change_is_pushed_live(self, plugin_module, monkeypatch,
                                              tmp_path):
        plugin, _api, proxy, script = self._plugin_with_session(
            plugin_module, monkeypatch, tmp_path, breakpoints=[1]
        )
        assert plugin.debug_current() is True
        session = plugin._session
        updates_before = len(session.breakpoint_updates)

        proxy.breakpoint_lines = [1, 5]
        proxy.breakpoints_changed.emit([1, 5])
        assert len(session.breakpoint_updates) > updates_before
        assert session.breakpoint_updates[-1] == {str(script): [1, 5]}

    def test_toggle_and_clear_breakpoints_from_menu(self, plugin_module):
        api = FakeApi()
        proxy = FakeProxy(filepath="/tmp/a.py")
        api.editors = [proxy]
        plugin = make_plugin(plugin_module, api)

        assert plugin.toggle_breakpoint() is True
        assert proxy.toggled == [0]
        proxy.breakpoint_lines = [1, 2, 3]
        assert plugin.clear_breakpoints() == 3
        assert "已清除 3 个断点" in api.status_text()

    def test_run_current_requires_python_file(self, plugin_module):
        api = FakeApi()
        api.filepath = os.path.join(ROOT, "README.md")
        api.editors = [FakeProxy(filepath=api.filepath)]
        plugin = make_plugin(plugin_module, api)
        assert plugin.run_current() is False
        assert "只有 Python 文件" in api.status_text() + api.message_text()

    def test_on_deactivate_stops_session(self, plugin_module, monkeypatch,
                                         tmp_path):
        plugin, _api, _proxy, _script = self._plugin_with_session(
            plugin_module, monkeypatch, tmp_path
        )
        assert plugin.debug_current() is True
        session = plugin._session
        plugin.on_deactivate()
        assert "stop" in session.commands
        assert plugin._session is None


# ============================================================
# 9. 调试面板
# ============================================================
class TestPanel:
    def test_show_paused_fills_tree(self, qapp, plugin_module):
        panel = plugin_module.DebuggerPanel(session=FakeSession())
        try:
            panel.show_paused({
                "reason": "breakpoint",
                "file": "C:/p/a.py",
                "line": 7,
                "stack": [
                    {"name": "add", "file": "C:/p/a.py", "line": 7},
                    {"name": "<module>", "file": "C:/p/a.py", "line": 12},
                ],
                "locals": {"a": "1", "b": "2"},
            })
            assert "命中断点" in panel.status_label.text()
            assert panel.tree.topLevelItemCount() == 3   # 2 帧 + 局部变量
            locals_item = panel.tree.topLevelItem(0)
            assert "局部变量" in locals_item.text(0)
            assert locals_item.childCount() == 2
            names = {locals_item.child(i).text(0)
                     for i in range(locals_item.childCount())}
            assert names == {"a", "b"}
        finally:
            panel.deleteLater()

    def test_buttons_call_session(self, qapp, plugin_module):
        session = FakeSession()
        panel = plugin_module.DebuggerPanel(session=session)
        try:
            panel.continue_btn.click()
            panel.step_over_btn.click()
            panel.step_into_btn.click()
            panel.step_out_btn.click()
            panel.locals_btn.click()
            panel.stack_btn.click()
            assert session.commands == [
                "continue", "step_over", "step_into", "step_out",
                "locals", "stack",
            ]
        finally:
            panel.deleteLater()

    def test_buttons_without_session_do_not_crash(self, qapp, plugin_module):
        panel = plugin_module.DebuggerPanel(session=None)
        try:
            panel.continue_btn.click()
            panel.stop_btn.click()
        finally:
            panel.deleteLater()

    def test_output_and_results(self, qapp, plugin_module):
        panel = plugin_module.DebuggerPanel(session=None)
        try:
            panel.append_output("hello\n")
            panel.append_output("world\n")
            assert "hello" in panel.output_view.toPlainText()
            assert "world" in panel.output_view.toPlainText()

            panel.show_result("stack", [
                {"name": "f", "file": "a.py", "line": 3}
            ])
            assert panel.tree.topLevelItemCount() == 1

            panel.show_result("eval", "42")
            assert "42" in panel.output_view.toPlainText()
        finally:
            panel.deleteLater()


# ============================================================
# 10. 真实端到端：真起驱动子进程，真的停/单步/继续/退出
# ============================================================
class _LineReader:
    """带超时的行读取（Windows 上 select 对管道无效，用线程 + 队列）。"""

    def __init__(self, stream):
        self._queue = queue.Queue()
        self._thread = threading.Thread(
            target=self._run, args=(stream,), daemon=True
        )
        self._thread.start()

    def _run(self, stream):
        try:
            for line in stream:
                self._queue.put(line)
        except Exception:
            pass
        finally:
            self._queue.put(None)

    def next_event(self, timeout=15.0):
        try:
            line = self._queue.get(timeout=timeout)
        except queue.Empty:
            raise AssertionError("等待调试器事件超时")
        if line is None:
            raise AssertionError("调试器进程已退出（管道关闭）")
        return json.loads(line)

    def expect(self, event, timeout=15.0):
        deadline = time.time() + timeout
        while True:
            remaining = max(0.1, deadline - time.time())
            payload = self.next_event(remaining)
            if payload.get("event") == event:
                return payload


SOURCE = (
    "def add(a, b):\n"
    "    total = a + b\n"
    "    return total\n"
    "\n"
    "print(\"start\")\n"
    "result = add(1, 2)\n"
    "print(\"result\", result)\n"
)


@pytest.mark.skipif(
    not os.path.isfile(sys.executable), reason="需要可用的 Python 解释器"
)
class TestRealDebugRun:
    """真实子进程联调：证明驱动**真的**能停、能单步、能退出。"""

    def _spawn(self, script):
        return subprocess.Popen(
            [sys.executable, "-u", DRIVER_PATH, str(script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

    def test_breakpoint_step_continue_and_exit(self, tmp_path):
        script = tmp_path / "target.py"
        script.write_text(SOURCE, encoding="utf-8")
        proc = self._spawn(script)
        reader = _LineReader(proc.stdout)
        try:
            ready = reader.expect("ready")
            assert os.path.normcase(ready["file"]) == os.path.normcase(
                str(script)
            )

            # 第 2 行：total = a + b
            self._send(proc, {
                "cmd": "set_breakpoints",
                "files": {str(script): [2]},
            })
            applied = reader.expect("breakpoints")
            canonical = os.path.normcase(os.path.abspath(str(script)))
            assert any(
                os.path.normcase(k) == canonical
                for k in applied["files"]
            ), f"断点未生效: {applied}"

            self._send(proc, {"cmd": "continue"})
            hit = reader.expect("break")
            assert hit["reason"] == "breakpoint"
            assert hit["line"] == 2, f"应停在断点行，实际 {hit}"
            assert hit["locals"].get("a") == "1"
            assert hit["locals"].get("b") == "2"
            assert hit["stack"], "break 事件必须带调用栈"

            # 单步跳过（over）→ 同一帧的下一行（第 3 行）
            self._send(proc, {"cmd": "step_over"})
            step = reader.expect("break")
            assert step["reason"] == "step"
            assert step["line"] == 3, f"单步应到第 3 行，实际 {step}"

            # 查看局部变量（不恢复执行）
            self._send(proc, {"cmd": "locals"})
            result = reader.expect("result")
            assert result["kind"] == "locals"
            assert "total" in result["value"]

            # 继续到程序结束
            self._send(proc, {"cmd": "continue"})
            outputs = []
            while True:
                payload = reader.next_event()
                if payload.get("event") == "output":
                    outputs.append(payload.get("text", ""))
                if payload.get("event") in ("exit", "exception"):
                    assert payload.get("event") == "exit", payload
                    assert payload.get("code") == 0
                    break
            assert any("result" in text for text in outputs), outputs

            # 不留孤儿：进程确实退出了
            assert proc.wait(timeout=10) == 0
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)

    def test_quit_terminates_process(self, tmp_path):
        script = tmp_path / "loop.py"
        script.write_text(
            "import time\n"
            "for i in range(100):\n"
            "    time.sleep(0.05)\n",
            encoding="utf-8",
        )
        proc = self._spawn(script)
        reader = _LineReader(proc.stdout)
        try:
            reader.expect("ready")
            self._send(proc, {
                "cmd": "set_breakpoints", "files": {str(script): [2]}
            })
            reader.expect("breakpoints")
            self._send(proc, {"cmd": "continue"})
            hit = reader.expect("break")
            assert hit["line"] == 2

            self._send(proc, {"cmd": "quit"})
            # 不留孤儿：quit 后进程必须自己退出
            assert proc.wait(timeout=10) is not None
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)

    def test_syntax_error_is_reported(self, tmp_path):
        script = tmp_path / "broken.py"
        script.write_text("def f(:\n    pass\n", encoding="utf-8")
        proc = self._spawn(script)
        reader = _LineReader(proc.stdout)
        try:
            first = reader.next_event()
            assert first["event"] == "exception"
            assert first["type"] == "SyntaxError"
            second = reader.next_event()
            assert second["event"] == "exit"
            assert proc.wait(timeout=10) is not None
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)

    @staticmethod
    def _send(proc, payload):
        proc.stdin.write(json.dumps(payload) + "\n")
        proc.stdin.flush()


# ============================================================
# 11. Lead 追加：external_change_detected 接线
# ============================================================
class TestExternalChangeWiring:
    def test_document_signal_is_connected_and_forwarded(self, qapp):
        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy

        sc = QsciScintilla()
        doc = Document()
        proxy = EditorProxy(sc, doc)

        forwarded = []
        proxy.external_change_detected.connect(forwarded.append)

        # 1) 行为断言：Document 发出后，proxy 会转发（这是真正的接线证据）
        doc.external_change_detected.emit("C:/p/changed.py")
        assert forwarded == ["C:/p/changed.py"]

        # 2) 同时确认确实建立了连接（receivers 计数）
        try:
            count = doc.receivers(doc.external_change_detected)
        except TypeError:
            count = None
        if count is not None:
            assert count > 0, "Document.external_change_detected 没有接收者"

    def test_connection_survives_missing_document(self, qapp):
        """document 为 None 时 _connect_signals 不应抛异常。"""
        from PyQt5.Qsci import QsciScintilla

        from core.editor import EditorProxy

        sc = QsciScintilla()
        proxy = EditorProxy(sc, None)
        assert proxy.external_change_detected is not None
