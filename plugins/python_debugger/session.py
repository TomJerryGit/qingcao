# -*- coding: utf-8 -*-
"""调试会话：子进程 + JSON 行协议（D3）。

本模块被 `plugins/python_debugger/__init__.py` 通过**文件路径**加载
（PluginLoader 用 `spec_from_file_location` 以合成模块名加载插件，插件
包没有包上下文，`from .session import ...` 会失败），因此这里**不要**
使用相对导入；加载方式见 `__init__.py::_load_sibling()`。

职责
----
* `check_backend()` —— "调试后端是否可用"的探测（**用户可见**提示）
* `build_driver_command()` —— 构造子进程命令行（纯函数，可单测）
* `to_python_lines()` / `to_editor_line()` —— 0 基/1 基行号互转
* `DebugSession` —— 生命周期（启动/收发/终止）+ 协议解析

孤儿进程
--------
`stop()` 的顺序是「quit 命令 → wait → terminate → wait → kill → wait」，
并且**关闭管道**；驱动脚本自身在 stdin EOF（宿主崩溃）时会 `os._exit`。
两边合起来保证不会留下孤儿调试进程。
"""
import json
import os
import subprocess
import sys
import threading

from PyQt5.QtCore import QObject, pyqtSignal


#: 驱动脚本文件名（与本模块同目录）
DRIVER_FILENAME = "driver.py"

#: 协议编码（两端都强制 UTF-8，避免中文变量值乱码）
PROTOCOL_ENCODING = "utf-8"

#: 默认优雅退出等待时间（秒）
GRACEFUL_EXIT_TIMEOUT = 1.0

#: 强制退出（terminate/kill）等待时间（秒）
FORCE_EXIT_TIMEOUT = 2.0


# ============================================================
# 纯函数工具
# ============================================================
def driver_path():
    """调试驱动脚本的绝对路径。"""
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), DRIVER_FILENAME
    )


def to_python_lines(lines):
    """编辑器行号（0 基）→ Python 行号（1 基），去重升序。

    bdb 与 Python 的 traceback 都用 1 基行号，编辑器用 0 基；协议层
    统一传 1 基，避免两端各自猜。
    """
    result = set()
    for line in lines or []:
        try:
            value = int(line)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            result.add(value + 1)
    return sorted(result)


def to_editor_line(line):
    """Python 行号（1 基）→ 编辑器行号（0 基）。"""
    try:
        return max(0, int(line) - 1)
    except (TypeError, ValueError):
        return 0


def build_driver_command(script, args=None, python=None, driver=None):
    """构造调试子进程的命令行（纯函数，便于单测）。"""
    return [
        python or sys.executable,
        "-u",
        driver or driver_path(),
        os.path.abspath(str(script)),
    ] + [str(a) for a in (args or [])]


def check_backend(python=None, driver=None):
    """探测调试后端是否可用。

    返回:
        (ok, message)。message 是**用户可见**的中文提示（ok 时为空串）。

    说明（D3）:
        本实现使用 Python **标准库** `bdb`，没有任何第三方依赖 ——
        因此"依赖未安装"这一类失败在这里具体化为两个必要条件：
          1) 当前解释器能 `import bdb`；
          2) 调试驱动脚本 `driver.py` 存在；
        另外要求可用于子进程的 Python 解释器路径。
    """
    problems = []

    try:
        import bdb  # noqa: F401  仅用于探测标准库是否完整
    except Exception as exc:  # pragma: no cover - 标准库缺失属极端环境
        problems.append(f"标准库 bdb 不可用：{exc}")

    interpreter = python or sys.executable or ""
    if not interpreter or not os.path.isfile(interpreter):
        problems.append(f"未找到 Python 解释器：{interpreter or '(空)'}")

    script = driver or driver_path()
    if not os.path.isfile(script):
        problems.append(f"调试驱动脚本缺失：{script}")

    if not problems:
        return True, ""

    return False, (
        "调试后端不可用：\n  - "
        + "\n  - ".join(problems)
        + "\n\n本调试器使用 Python 标准库 bdb，**不需要**安装第三方包；"
        '请确认 Python 安装完整（python -c "import bdb"）后重试。'
    )


def _creation_flags():
    """Windows 下不弹控制台黑框；其它平台返回 0。"""
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


# ============================================================
# 调试会话
# ============================================================
def validate_eval_expression(expression):
    """RPC 层校验表达式（v2.15.x P3）：空/超长直接拒绝，避免下发子进程"""
    expr = str(expression or "")
    if not expr.strip():
        return (False, "表达式为空")
    if len(expr) > 4000:
        return (False, "表达式过长（>4000 字符）")
    return (True, expr)


class DebugSession(QObject):
    """一次调试会话。

    信号:
        event_received(dict): 收到任一协议事件（原始 payload）
        output_received(str, str): 被调试程序的输出（stream, text）
        break_hit(str, int): 停在某文件某行（**0 基**行号，便于直接喂给编辑器）
        finished(int): 调试进程结束（退出码）
        failed(str): 失败原因（**用户可见**文本）
    """

    event_received = pyqtSignal(dict)
    output_received = pyqtSignal(str, str)
    break_hit = pyqtSignal(str, int)
    finished = pyqtSignal(int)
    failed = pyqtSignal(str)

    def __init__(self, parent=None, python=None, driver=None, popen=None):
        super().__init__(parent)
        self._python = python or sys.executable
        self._driver = driver or driver_path()
        #: 可注入，便于单测不真起进程
        self._popen = popen or subprocess.Popen
        self._proc = None
        self._reader_threads = []
        self._state = "idle"          # idle/starting/running/paused/stopped
        self._finished_emitted = False
        self._returncode = None
        self.last_error = ""
        self.last_paused = None       #: 最近一次 break 事件的 payload

    # --------------------------------------------------------
    # 状态
    # --------------------------------------------------------
    @property
    def state(self):
        return self._state

    @property
    def is_running(self):
        proc = self._proc
        if proc is None:
            return False
        try:
            return proc.poll() is None
        except Exception:
            return False

    @property
    def returncode(self):
        return self._returncode

    # --------------------------------------------------------
    # 生命周期
    # --------------------------------------------------------
    def start(self, script, args=None, cwd=None):
        """启动调试子进程。

        返回:
            是否启动成功。失败时 `failed` 信号已携带用户可见原因。
        """
        if self.is_running:
            return False

        ok, message = check_backend(python=self._python, driver=self._driver)
        if not ok:
            self.last_error = message
            self.failed.emit(message)
            return False

        script = os.path.abspath(str(script))
        if not os.path.isfile(script):
            self.last_error = f"找不到要调试的脚本：{script}"
            self.failed.emit(self.last_error)
            return False

        argv = build_driver_command(
            script, args, python=self._python, driver=self._driver
        )
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = PROTOCOL_ENCODING
        env["PYTHONUNBUFFERED"] = "1"

        try:
            self._proc = self._popen(
                argv,
                cwd=cwd or os.path.dirname(script) or None,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding=PROTOCOL_ENCODING,
                errors="replace",
                bufsize=1,
                env=env,
                creationflags=_creation_flags(),
            )
        except Exception as exc:
            self._proc = None
            self._state = "stopped"
            self.last_error = f"启动调试进程失败：{exc}"
            self.failed.emit(self.last_error)
            return False

        self._state = "starting"
        self._finished_emitted = False
        self._returncode = None
        self._ensure_stream_attr(self._proc, "stdin")
        self._ensure_stream_attr(self._proc, "stdout")
        self._ensure_stream_attr(self._proc, "stderr")

        self._start_reader(self._proc.stdout, "protocol")
        self._start_reader(self._proc.stderr, "stderr")
        self._start_waiter(self._proc)
        return True

    @staticmethod
    def _ensure_stream_attr(proc, name):
        """兼容只实现了部分接口的假进程（单测用）。"""
        if not hasattr(proc, name):
            try:
                setattr(proc, name, None)
            except Exception:
                pass

    def _start_reader(self, stream, kind):
        if stream is None:
            return None
        thread = threading.Thread(
            target=self._reader_loop,
            args=(stream, kind),
            name=f"qingcao-debug-{kind}",
            daemon=True,
        )
        thread.start()
        self._reader_threads.append(thread)
        return thread

    def _reader_loop(self, stream, kind):
        try:
            for raw in stream:
                line = (raw or "").strip()
                if not line:
                    continue
                if kind == "stderr":
                    self.output_received.emit("stderr", line + "\n")
                else:
                    self.handle_line(line)
        except Exception:
            # 进程结束/管道关闭都会走到这里，属于正常收尾
            pass

    def _start_waiter(self, proc):
        def _wait():
            try:
                code = proc.wait()
            except Exception:
                code = -1
            self._returncode = code
            if not self._finished_emitted:
                self._finished_emitted = True
                self._state = "stopped"
                self.finished.emit(int(code if code is not None else -1))

        thread = threading.Thread(
            target=_wait, name="qingcao-debug-waiter", daemon=True
        )
        thread.start()
        self._reader_threads.append(thread)

    # --------------------------------------------------------
    # 协议
    # --------------------------------------------------------
    def handle_line(self, line):
        """解析一行协议 JSON（单测可直接调用，无需真起进程）。"""
        try:
            payload = json.loads(line)
        except Exception as exc:
            self.output_received.emit(
                "stderr", f"[协议解析失败: {exc}] {line}\n"
            )
            return None
        if not isinstance(payload, dict):
            return None
        self._observe(payload)
        self.event_received.emit(payload)
        return payload

    def _observe(self, payload):
        event = payload.get("event")
        if event == "ready":
            self._state = "running"
        elif event == "break":
            self._state = "paused"
            self.last_paused = payload
            self.break_hit.emit(
                str(payload.get("file") or ""),
                to_editor_line(payload.get("line", 1)),
            )
        elif event == "output":
            self.output_received.emit(
                str(payload.get("stream") or "stdout"),
                str(payload.get("text") or ""),
            )
        elif event == "exit":
            self._state = "stopped"
            self._emit_finished(int(payload.get("code") or 0))
        elif event == "error":
            self.last_error = str(payload.get("message") or "")
            self.failed.emit(self.last_error)
        elif event == "exception":
            self._state = "paused"
            self.last_error = (
                f"程序抛出 {payload.get('type')}: {payload.get('message')}"
            )
            self.failed.emit(self.last_error)

    def _emit_finished(self, code):
        if self._finished_emitted:
            return
        self._finished_emitted = True
        self.finished.emit(int(code))

    # --------------------------------------------------------
    # 发送命令
    # --------------------------------------------------------
    def send(self, command):
        """向调试进程发送一条 JSON 命令。"""
        proc = self._proc
        if proc is None or not self.is_running:
            self.last_error = "调试进程未在运行"
            return False
        try:
            self._write_line(json.dumps(command, ensure_ascii=False))
            return True
        except Exception as exc:
            self.last_error = f"发送调试命令失败：{exc}"
            self.failed.emit(self.last_error)
            return False

    def _write_line(self, line):
        stdin = getattr(self._proc, "stdin", None)
        if stdin is None:
            raise RuntimeError("调试进程的 stdin 不可用")
        stdin.write(line + "\n")
        stdin.flush()

    # ---- 具体命令 ----
    def set_breakpoints(self, files):
        """下发断点。

        参数:
            files: {文件路径: [**0 基**行号, ...]}（编辑器语义）
        """
        payload = {}
        for path, lines in (files or {}).items():
            converted = to_python_lines(lines)
            if converted:
                payload[str(path)] = converted
        return self.send({"cmd": "set_breakpoints", "files": payload})

    def continue_(self):
        return self.send({"cmd": "continue"})

    def step_over(self):
        return self.send({"cmd": "step_over"})

    def step_into(self):
        return self.send({"cmd": "step_into"})

    def step_out(self):
        return self.send({"cmd": "step_out"})

    def pause(self):
        return self.send({"cmd": "pause"})

    def request_stack(self):
        return self.send({"cmd": "stack"})

    def request_locals(self):
        return self.send({"cmd": "locals"})

    def evaluate(self, expression):
        """在调试目标子进程内求值（RPC cmd=eval，v2.15.x）"""
        ok, expr = validate_eval_expression(expression)
        if not ok:
            return {"error": expr}
        return self.send({"cmd": "eval", "expr": expr})

    def quit(self):
        return self.send({"cmd": "quit"})

    # --------------------------------------------------------
    # 终止（保证不留孤儿）
    # --------------------------------------------------------
    def stop(self, timeout=GRACEFUL_EXIT_TIMEOUT):
        """终止调试：quit → wait → terminate → wait → kill → wait。

        返回:
            进程是否已确实退出。
        """
        proc = self._proc
        if proc is None:
            self._state = "stopped"
            return True

        try:
            if proc.poll() is None:
                # 1) 先礼后兵：请驱动脚本自己退出
                try:
                    self._write_line(json.dumps({"cmd": "quit"}))
                except Exception:
                    pass
                try:
                    proc.wait(timeout=timeout)
                except Exception:
                    # 2) terminate
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    try:
                        proc.wait(timeout=timeout)
                    except Exception:
                        # 3) 最后手段：kill，杜绝孤儿调试进程
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        try:
                            proc.wait(timeout=FORCE_EXIT_TIMEOUT)
                        except Exception:
                            pass
        finally:
            for name in ("stdin", "stdout", "stderr"):
                stream = getattr(proc, name, None)
                try:
                    if stream is not None:
                        stream.close()
                except Exception:
                    pass
            self._state = "stopped"
            try:
                self._returncode = proc.poll()
            except Exception:
                self._returncode = None

        try:
            exited = proc.poll() is not None
        except Exception:
            exited = False
        if exited:
            self._proc = None
            self._emit_finished(
                int(self._returncode) if self._returncode is not None else -1
            )
        return exited

    def __repr__(self):
        return (
            f"<DebugSession state={self._state} "
            f"running={self.is_running} rc={self._returncode}>"
        )
