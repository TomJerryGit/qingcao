# -*- coding: utf-8 -*-
"""Windows 交互式 PTY 会话封装（v2.23 D4）。

基于 pywinpty（ConPTY）：持续 shell 会话、可读写、可等待输出。
read() 为阻塞调用，因此用后台读线程 + 条件变量提供非阻塞 API。
"""

import sys
import threading
import time


try:
    from winpty import PtyProcess

    HAS_WINPTY = True
except ImportError:  # pragma: no cover - 非 Windows/未安装
    PtyProcess = None
    HAS_WINPTY = False


class PtySession:
    """最小交互式 PTY 会话。"""

    def __init__(self, argv=None, cwd=None, rows=24, cols=120, env=None):
        if not HAS_WINPTY:
            raise RuntimeError("pywinpty 不可用")
        argv = argv or self.default_shell()
        self._proc = PtyProcess.spawn(argv, cwd=cwd, env=env, dimensions=(rows, cols))
        self._buf = ""
        self._cv = threading.Condition()
        self._closed = False
        self._reader = threading.Thread(target=self._read_loop, name="pty-reader", daemon=True)
        self._reader.start()

    @staticmethod
    def default_shell():
        if sys.platform == "win32":
            return ["cmd.exe"]
        return ["/bin/sh"]

    def _read_loop(self):
        while True:
            try:
                data = self._proc.read(4096)
            except (EOFError, OSError, ValueError):
                break
            except Exception:
                break
            if not data:
                continue
            with self._cv:
                self._buf += data
                self._cv.notify_all()
        with self._cv:
            self._closed = True
            self._cv.notify_all()

    def write(self, text):
        self._proc.write(text)

    def read_available(self):
        """取走当前输出（非阻塞）。"""
        with self._cv:
            data, self._buf = self._buf, ""
            return data

    def wait_for(self, text, timeout=10.0):
        """等待输出中出现指定文本。"""
        deadline = time.time() + timeout
        with self._cv:
            while text not in self._buf:
                remain = deadline - time.time()
                if remain <= 0:
                    return False
                if self._closed and not self._buf:
                    return False
                self._cv.wait(min(remain, 0.5))
            return True

    def is_alive(self):
        try:
            return bool(self._proc.isalive())
        except Exception:
            return False

    def close(self):
        try:
            self._proc.terminate(force=True)
        except Exception:
            pass
        try:
            self._proc.close(force=True)
        except Exception:
            pass
