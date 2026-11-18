# -*- coding: utf-8 -*-
"""AI 自动调试：安全子进程运行器（超时/输出/内存/CPU/网络限制）。"""

import os
import subprocess
import sys
import threading
import time


MAX_OUTPUT = 100_000

_NET_BLOCK = r"""
import socket, runpy, sys
_orig = socket.socket
class _BlockedSocket(_orig):
    def __init__(self, *a, **k):
        raise OSError("network disabled by AI runner")
socket.socket = _BlockedSocket
def _blocked_conn(*a, **k):
    raise OSError("network disabled by AI runner")
socket.create_connection = _blocked_conn
runpy.run_path(%r, run_name="__main__")
"""


def _truncate(text):
    text = text or ""
    if len(text) <= MAX_OUTPUT:
        return text
    return text[:MAX_OUTPUT] + "\n...[输出已截断]"


def _kill(proc):
    try:
        proc.kill()
    except Exception:
        pass


def run_python_file(
    path,
    args=None,
    timeout=15,
    cwd=None,
    max_output=MAX_OUTPUT,
    max_memory_mb=512,
    max_cpu_seconds=None,
    allow_network=False,
):
    path = os.path.abspath(str(path))
    if not os.path.isfile(path) or not path.lower().endswith(".py"):
        return {"ok": False, "error": "仅支持运行存在的 .py 文件"}
    wd = os.path.abspath(str(cwd)) if cwd else os.path.dirname(path)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["QINGCAO_AI_RUN_ALLOW_NET"] = "1" if allow_network else "0"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if allow_network:
        cmd = [sys.executable, path] + [str(a) for a in (args or [])]
    else:
        cmd = [sys.executable, "-c", _NET_BLOCK % path]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=wd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}

    state = {"memory_exceeded": False, "cpu_exceeded": False}
    stop = threading.Event()

    def _watch():
        try:
            import psutil
        except Exception:
            return
        try:
            p = psutil.Process(proc.pid)
        except Exception:
            return
        start = time.time()
        while not stop.is_set() and proc.poll() is None:
            try:
                rss = p.memory_info().rss / (1024 * 1024)
                if max_memory_mb and rss > float(max_memory_mb):
                    state["memory_exceeded"] = True
                    _kill(proc)
                    return
                cpu = sum(p.cpu_times()[:2])
                if max_cpu_seconds and cpu > float(max_cpu_seconds):
                    state["cpu_exceeded"] = True
                    _kill(proc)
                    return
                if time.time() - start > max(1, int(timeout)) + 2:
                    return
            except Exception:
                pass
            time.sleep(0.05)

    watcher = threading.Thread(target=_watch, daemon=True)
    watcher.start()
    timed_out = False
    try:
        out, err = proc.communicate(timeout=max(1, int(timeout)))
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill(proc)
        out, err = proc.communicate()
    finally:
        stop.set()
        watcher.join(timeout=1)

    out = (out or "")[:max_output]
    err = (err or "")[:max_output]
    reason = ""
    if state["memory_exceeded"]:
        reason = "内存超过限制（%sMB）" % max_memory_mb
    elif state["cpu_exceeded"]:
        reason = "CPU 时间超过限制"
    elif timed_out:
        reason = "运行超时"
    return {
        "ok": (
            not timed_out
            and not state["memory_exceeded"]
            and not state["cpu_exceeded"]
            and proc.returncode == 0
        ),
        "exit_code": proc.returncode,
        "stdout": _truncate(out),
        "stderr": _truncate(err),
        "timed_out": timed_out,
        "memory_exceeded": state["memory_exceeded"],
        "cpu_exceeded": state["cpu_exceeded"],
        "network_allowed": bool(allow_network),
        "error": reason,
    }
