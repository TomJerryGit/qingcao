# -*- coding: utf-8 -*-
"""跨平台交互式 PTY 会话（Windows: pywinpty；POSIX: pty/subprocess）。"""

import os
import sys
import threading
import time


try:
    from winpty import PtyProcess

    HAS_WINPTY = True
except ImportError:  # pragma: no cover - 非 Windows/未安装
    PtyProcess = None
    HAS_WINPTY = False

HAS_PTY = HAS_WINPTY or sys.platform != "win32"


class PtySession:
    """最小交互式 PTY 会话（read/write 非阻塞封装）。"""

    def __init__(self, argv=None, cwd=None, rows=24, cols=120, env=None):
        argv = argv or self.default_shell()
        self._buf = ""
        self._cv = threading.Condition()
        self._closed = False
        self._master = None
        self._proc = None
        self._backend = "posix" if sys.platform != "win32" else "winpty"
        if self._backend == "winpty":
            if not HAS_WINPTY:
                raise RuntimeError("pywinpty 不可用")
            self._proc = PtyProcess.spawn(argv, cwd=cwd, env=env, dimensions=(rows, cols))
        else:
            import pty
            import subprocess

            master, slave = pty.openpty()
            self._master = master
            self._proc = subprocess.Popen(
                argv,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=cwd,
                env=env,
                close_fds=True,
                preexec_fn=os.setsid,
            )
            os.close(slave)
            self.resize(rows, cols)
        self._reader = threading.Thread(target=self._read_loop, name="pty-reader", daemon=True)
        self._reader.start()

    @staticmethod
    def default_shell():
        if sys.platform == "win32":
            return ["cmd.exe"]
        return ["/bin/sh"]

    def _read_once(self):
        if self._backend == "winpty":
            return self._proc.read(4096)
        if self._master is None:
            return ""
        raw = os.read(self._master, 4096)
        if isinstance(raw, bytes):
            return raw.decode("utf-8", "replace")
        return raw

    def _read_loop(self):
        while True:
            try:
                data = self._read_once()
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
        if self._backend == "winpty":
            self._proc.write(text)
        elif self._master is not None:
            os.write(self._master, str(text).encode("utf-8", "replace"))

    def resize(self, rows, cols):
        if self._backend != "posix" or self._master is None:
            return False
        try:
            import fcntl
            import struct
            import termios

            fcntl.ioctl(
                self._master, termios.TIOCSWINSZ, struct.pack("HHHH", int(rows), int(cols), 0, 0)
            )
            return True
        except Exception:
            return False

    def read_available(self):
        with self._cv:
            data, self._buf = self._buf, ""
            return data

    def wait_for(self, text, timeout=10.0):
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
            if self._backend == "winpty":
                return bool(self._proc.isalive())
            return self._proc.poll() is None
        except Exception:
            return False

    def close(self):
        try:
            if self._backend == "winpty":
                self._proc.terminate(force=True)
                self._proc.close(force=True)
            else:
                if self._proc is not None and self._proc.poll() is None:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=2)
                    except Exception:
                        self._proc.kill()
                if self._master is not None:
                    os.close(self._master)
                    self._master = None
        except Exception:
            pass
