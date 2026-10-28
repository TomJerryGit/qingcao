#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""青草编辑器 —— Python 调试驱动（D3）

用法::

    python -u driver.py <script.py> [脚本参数...]

为什么是"bdb + stdio 管道"而不是 debugpy / DAP
------------------------------------------------
1. `debugpy` 是**第三方依赖**，没装就用不了；`bdb` 是标准库，**开箱即用**。
2. debugpy 走 DAP 需要监听端口/适配器，本插件要的是"编辑器内可控调试"，
   bdb 已足够，且**被调试代码就在本进程里**——宿主 kill 掉本进程即等于
   杀掉被调试程序，不会留下孤儿。
3. 不复用 `python -m pdb` 是因为它的输出是面向人的文本，解析脆弱；
   自写驱动用 JSON 行协议，**主机侧完全可控、可测**。

协议（stdout 每行一个 JSON 对象）
---------------------------------
命令（stdin，逐行 JSON）:
    {"cmd": "set_breakpoints", "files": {"<绝对路径>": [1 基行号, ...]}}
    {"cmd": "continue"} / "step_over" / "step_into" / "step_out" / "pause"
    {"cmd": "stack"} / "locals" / "eval"（带 "expr"）
    {"cmd": "quit"}
事件（stdout）:
    {"event": "ready", "file": ..., "pid": ...}
    {"event": "breakpoints", "files": {...}}        # 实际生效的断点
    {"event": "break", "reason": "breakpoint|step|pause", "file": ...,
     "line": N(1 基), "name": ..., "locals": {...}, "stack": [...]}
    {"event": "result", "kind": "stack|locals|eval", "value": ...}
    {"event": "output", "stream": "stdout|stderr", "text": "..."}
    {"event": "exit", "code": N}
    {"event": "exception", "type": ..., "message": ..., "traceback": ...}
    {"event": "error", "message": "..."}

线程模型
--------
主线程跑 `bdb.Bdb.run()`（= 被调试代码本身）；另有一个守护线程只负责读
stdin 并塞进队列。命中断点/单步时 `user_line()` 在**主线程**里阻塞等待
命令 —— 不做任何跨线程的 bdb 调用，因此没有竞态。

孤儿进程防护
------------
宿主若崩溃/被强杀，stdin 会 EOF；读线程一旦发现 EOF 立即 `os._exit(0)`，
被调试进程随宿主一起消失（Windows 上父进程退出**不会**自动杀子进程，
这一步是必须的兜底）。
"""
import bdb
import builtins
import json
import os
import queue
import sys
import threading
import traceback


#: 协议写出的真实 stdout（被调试代码的 print 会被包装成 output 事件，
#: 因此不会污染协议流）
_REAL_STDOUT = sys.stdout
_WRITE_LOCK = threading.Lock()

#: 只有驱动脚本**真的跑起来**（main() 被调用）之后，写协议流失败才判定为
#: "宿主已死"，从而 `os._exit(0)` 自杀。默认关闭，避免单元测试 import 本
#: 模块后调用 set_breaks/emit 时误杀 pytest 进程。
_EXIT_ON_BROKEN_PIPE = False


def emit(payload):
    """把一个事件写成一行 JSON 到真实 stdout。"""
    try:
        with _WRITE_LOCK:
            _REAL_STDOUT.write(
                json.dumps(payload, ensure_ascii=False) + "\n"
            )
            _REAL_STDOUT.flush()
    except Exception:
        # 宿主已经走了（管道断了）：直接结束，别留孤儿。
        # 非驱动进程（例如单测）里只吞掉异常，不能杀宿主。
        if _EXIT_ON_BROKEN_PIPE:
            os._exit(0)


def format_value(value, limit=200):
    """把任意值转成 JSON 安全的短字符串（用于变量显示）。"""
    try:
        text = repr(value)
    except Exception:
        return "<无法显示>"
    if len(text) > limit:
        return text[:limit] + "…"
    return text


class _ForwardedStream:
    """把被调试代码的 stdout/stderr 包装成 output 事件。"""

    def __init__(self, name):
        self._name = name

    def write(self, text):
        if text:
            emit({
                "event": "output",
                "stream": self._name,
                "text": text,
            })
        return len(text)

    def writelines(self, lines):
        for line in lines:
            self.write(line)

    def flush(self):
        pass

    def isatty(self):
        return False

    @property
    def encoding(self):
        return "utf-8"


class JsonDebugger(bdb.Bdb):
    """基于 `bdb.Bdb` 的受控调试器。

    复用 bdb 的**断点表**（`set_break` / `breaks` / `break_here`）与
    `BdbQuit`，但**刻意不使用** bdb 的 `stopframe/stoplineno/returnframe`
    这套 stopinfo 机制：我们把步进策略显式写在自己的 `dispatch_call` /
    `dispatch_line` / `dispatch_return` 里。

    原因（老实现的两个坑）：
      1. bdb 默认的 `dispatch_call` 在"该帧不需要停"时返回 None，等于
         **放弃该帧的局部跟踪** —— 函数体内部的断点会因此永远不命中
         （调用事件的行号是函数首行，而断点通常在函数体中间某行）。
      2. `set_continue/set_next/set_return` 的行为依赖 `stop_here()` 在
         `stopframe is None` 时的返回值，语义隐晦；自己维护 `_mode`
         就没有这层不确定。

    因此：**调用帧一律继续跟踪**，是否停下由 `_should_stop()` 决定。
    """

    #: 步进模式
    MODE_CONTINUE = "continue"
    MODE_NEXT = "next"       # 单步跳过（同帧下一行）
    MODE_STEP = "step"       # 单步进入（任意帧下一行）
    MODE_OUT = "out"         # 单步跳出（当前帧返回后停在调用者）

    def __init__(self, command_queue):
        super().__init__()
        self._queue = command_queue
        self._pause_requested = False
        self._forced_reason = ""
        self._mode = self.MODE_CONTINUE
        self._step_frame = None

    # --------------------------------------------------------
    # 断点
    # --------------------------------------------------------
    def set_breaks(self, files):
        """整体替换断点集合。

        参数:
            files: {路径: [1 基行号, ...]}

        返回:
            {路径: [真正生效的 1 基行号, ...]}

        ⚠️ 返回值语义（已实测，与直觉相反）:
            `bdb.Bdb.set_break()` **成功返回 None**，失败返回一段错误
            **字符串**（如 ``"Line a.py:999 does not exist"``）。
            早先写成 ``if bp is not None`` 时只记录了失败的、丢掉了成功的，
            于是断点在真实运行里全部失效（Lead 实测确认）。这里以
            ``result is None`` 判定成功，并把未生效的行单独报给宿主。
        """
        self.clear_all_breaks()
        applied = {}
        skipped = {}
        for path, lines in (files or {}).items():
            try:
                canonical = self.canonic(path)
            except Exception:
                continue
            if not os.path.isfile(canonical):
                # bdb 在文件尚未导入时不校验存在性，这里自己先挡掉
                try:
                    skipped[canonical] = [int(x) for x in (lines or [])]
                except (TypeError, ValueError):
                    skipped[canonical] = list(lines or [])
                continue
            for line in lines or []:
                try:
                    line = int(line)
                except (TypeError, ValueError):
                    continue
                try:
                    result = self.set_break(canonical, line)
                except Exception as exc:
                    result = str(exc)
                if result is None:          # None == 成功
                    applied.setdefault(canonical, []).append(line)
                else:
                    skipped.setdefault(canonical, []).append(line)
        for lines in applied.values():
            lines.sort()
        emit({
            "event": "breakpoints",
            "files": applied,
            "skipped": skipped,
        })
        return applied

    def breakpoints_at(self, frame):
        """该帧当前行是否是断点行。"""
        try:
            filename = self.canonic(frame.f_code.co_filename)
            return frame.f_lineno in self.breaks.get(filename, [])
        except Exception:
            return False

    def reset(self):
        """保住断点表。

        `bdb.Bdb.run()` 一进来就会调用 `reset()`。不同 Python 版本的
        `reset()` 实现略有差异，这里显式把断点表存下来再放回去，保证
        "启动前下发的断点"在任何版本上都一定生效。
        """
        breaks = dict(self.breaks)
        super().reset()
        self.breaks = breaks

    # --------------------------------------------------------
    # 跟踪入口（替代 bdb 的 stopinfo 机制）
    # --------------------------------------------------------
    def _should_stop(self, frame):
        """当前行是否需要停下来。"""
        if self._pause_requested:
            self._pause_requested = False
            self._forced_reason = "pause"
            return True
        try:
            if self.break_here(frame):
                return True
        except Exception:
            pass
        if self._mode == self.MODE_STEP:
            return True
        if self._mode == self.MODE_NEXT:
            return frame is self._step_frame
        return False

    def dispatch_line(self, frame):
        if self.quitting:
            raise bdb.BdbQuit
        if self._should_stop(frame):
            self.user_line(frame)
            if self.quitting:
                raise bdb.BdbQuit
        return self.trace_dispatch

    def dispatch_call(self, frame, arg):
        """**所有**调用帧都继续做行跟踪。

        这一点很关键：bdb 默认会在"不需要停"的帧上返回 None，从而
        关掉该帧的局部跟踪，导致函数体内部设置的断点永远不触发。
        """
        if self.botframe is None:
            self.botframe = frame.f_back
        return self.trace_dispatch

    def dispatch_return(self, frame, arg):
        """单步跳出：当前帧返回后，改为"停到调用者的下一行"。"""
        if self._mode == self.MODE_OUT and frame is self._step_frame:
            caller = frame.f_back
            if caller is None:
                self._mode = self.MODE_CONTINUE
            else:
                self._mode = self.MODE_NEXT
                self._step_frame = caller
        if self.quitting:
            raise bdb.BdbQuit
        return self.trace_dispatch

    def user_line(self, frame):
        """停在某一行：发事件 + 阻塞等待宿主命令（主线程内）。"""
        reason = self._forced_reason or (
            "breakpoint" if self.breakpoints_at(frame) else "step"
        )
        self._forced_reason = ""
        emit({
            "event": "break",
            "reason": reason,
            "file": frame.f_code.co_filename,
            "line": frame.f_lineno,
            "name": frame.f_code.co_name,
            "locals": self.frame_locals(frame),
            "stack": self.stack_frames(frame),
        })
        self._command_loop(frame)

    # --------------------------------------------------------
    # 命令循环（在被调试线程里阻塞等待宿主指令）
    # --------------------------------------------------------
    def _command_loop(self, frame):
        while True:
            command = self._queue.get()
            if command is None:
                # EOF：宿主没了
                self.set_quit()
                return
            action = str(command.get("cmd", ""))

            if action == "continue":
                self._mode = self.MODE_CONTINUE
                self._step_frame = None
                return
            if action == "step_over":
                self._mode = self.MODE_NEXT
                self._step_frame = frame
                return
            if action == "step_into":
                self._mode = self.MODE_STEP
                self._step_frame = frame
                return
            if action == "step_out":
                self._mode = self.MODE_OUT
                self._step_frame = frame
                return
            if action == "quit":
                self.set_quit()
                return

            # 以下命令不恢复执行，只回一次结果
            if action == "pause":
                emit({"event": "ack", "cmd": "pause"})
            elif action == "stack":
                emit({
                    "event": "result",
                    "kind": "stack",
                    "value": self.stack_frames(frame),
                })
            elif action == "locals":
                emit({
                    "event": "result",
                    "kind": "locals",
                    "value": self.frame_locals(frame),
                })
            elif action == "eval":
                emit({
                    "event": "result",
                    "kind": "eval",
                    "value": self.safe_eval(frame, command.get("expr", "")),
                })
            elif action == "set_breakpoints":
                self.set_breaks(command.get("files") or {})
            else:
                emit({
                    "event": "error",
                    "message": f"未知命令: {action}",
                })

    def request_pause(self):
        """由读线程调用（只置标志，不碰 bdb 状态）。"""
        self._pause_requested = True

    # --------------------------------------------------------
    # 帧内省
    # --------------------------------------------------------
    def stack_frames(self, frame, limit=20):
        """从内到外的调用栈（含文件名/函数名/行号）。"""
        result = []
        current = frame
        depth = 0
        while current is not None and depth < limit:
            code = current.f_code
            result.append({
                "name": code.co_name,
                "file": code.co_filename,
                "line": current.f_lineno,
            })
            current = current.f_back
            depth += 1
        return result

    def frame_locals(self, frame):
        """当前帧局部变量（名字 → 短 repr 字符串）。"""
        values = {}
        try:
            items = list(frame.f_locals.items())
        except Exception:
            return values
        for name, value in items:
            if name.startswith("__") and name.endswith("__"):
                continue
            values[str(name)] = format_value(value)
        return values

    def safe_eval(self, frame, expression):
        """在被调试帧里求值（失败不抛，返回错误文本）。"""
        if not expression:
            return ""
        try:
            # 安全收敛：限制表达式长度，异常统一格式化（在调试目标子进程内执行）
            if len(expression) > 4000:
                return "<expression too long>"
            return format_value(eval(expression, frame.f_globals, frame.f_locals))
        except Exception as exc:
            return f"<错误: {exc}>"


# ============================================================
# stdin 读线程
# ============================================================
def _reader_loop(command_queue, debugger):
    """逐行读 JSON 命令。EOF 说明宿主已经走了 → 立刻自杀，不留孤儿。"""
    stream = sys.stdin
    while True:
        try:
            line = stream.readline()
        except Exception:
            os._exit(0)
        if not line:
            # EOF：宿主进程已消失
            os._exit(0)
        line = line.strip()
        if not line:
            continue
        try:
            command = json.loads(line)
        except Exception as exc:
            emit({"event": "error", "message": f"命令不是合法 JSON: {exc}"})
            continue
        if not isinstance(command, dict):
            emit({"event": "error", "message": "命令必须是 JSON 对象"})
            continue
        if command.get("cmd") == "pause":
            debugger.request_pause()
        command_queue.put(command)


# ============================================================
# 入口
# ============================================================
def _install_output_forwarding():
    """把被调试代码的 print 变成 output 事件。"""
    sys.stdout = _ForwardedStream("stdout")
    sys.stderr = _ForwardedStream("stderr")


def main(argv=None):
    global _EXIT_ON_BROKEN_PIPE
    # 从这里开始才是"真正的驱动进程"：协议流断开即可判定宿主已死
    _EXIT_ON_BROKEN_PIPE = True

    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 2:
        emit({
            "event": "error",
            "message": "用法: python -u driver.py <script.py> [args...]",
        })
        return 2

    script = os.path.abspath(argv[1])
    script_args = argv[2:]

    if not os.path.isfile(script):
        emit({"event": "error", "message": f"脚本不存在: {script}"})
        return 2

    _install_output_forwarding()

    try:
        with open(script, encoding="utf-8") as fp:
            source = fp.read()
    except Exception as exc:
        emit({"event": "error", "message": f"读取脚本失败: {exc}"})
        return 2

    try:
        code = compile(source, script, "exec")
    except SyntaxError as exc:
        emit({
            "event": "exception",
            "type": "SyntaxError",
            "message": str(exc),
            "line": exc.lineno or 0,
            "file": exc.filename or script,
            "traceback": "".join(
                traceback.format_exception_only(type(exc), exc)
            ),
        })
        emit({"event": "exit", "code": 1})
        return 1

    command_queue = queue.Queue()
    debugger = JsonDebugger(command_queue)

    threading.Thread(
        target=_reader_loop,
        args=(command_queue, debugger),
        name="qingcao-debug-stdin",
        daemon=True,
    ).start()

    emit({
        "event": "ready",
        "file": script,
        "pid": os.getpid(),
        "python": sys.version.split()[0],
    })

    # 等宿主先把断点下发完再开始跑，避免"程序已经跑过断点"的竞态
    while True:
        first = command_queue.get()
        if first is None:
            return 0
        action = str(first.get("cmd", ""))
        if action == "set_breakpoints":
            debugger.set_breaks(first.get("files") or {})
            continue
        if action in (
            "continue", "step_over", "step_into", "step_out", "pause",
        ):
            if action == "pause":
                debugger.request_pause()
            break
        if action == "quit":
            return 0
        emit({"event": "error", "message": f"未知命令: {action}"})

    globs = {
        "__name__": "__main__",
        "__file__": script,
        "__builtins__": builtins,
        "__package__": None,
        "__doc__": None,
    }
    sys.argv = [script] + script_args
    sys.path.insert(0, os.path.dirname(script))

    exit_code = 0
    try:
        debugger.run(code, globs, globs)
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 0
    except bdb.BdbQuit:
        exit_code = 0
    except BaseException as exc:  # noqa: BLE001 - 必须把任何异常报给宿主
        emit({
            "event": "exception",
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
        })
        exit_code = 1

    emit({"event": "exit", "code": exit_code})
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
