# -*- coding: utf-8 -*-
"""AI 自动调试：安全子进程运行器（阶段 A）。"""

import os
import subprocess
import sys


MAX_OUTPUT = 100_000


def _truncate(text):
    text = text or ""
    if len(text) <= MAX_OUTPUT:
        return text
    return text[:MAX_OUTPUT] + "\n...[输出已截断]"


def run_python_file(path, args=None, timeout=15, cwd=None, max_output=MAX_OUTPUT):
    path = os.path.abspath(str(path))
    if not os.path.isfile(path) or not path.lower().endswith(".py"):
        return {"ok": False, "error": "仅支持运行存在的 .py 文件"}
    wd = os.path.abspath(str(cwd)) if cwd else os.path.dirname(path)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    cmd = [sys.executable, path] + [str(a) for a in (args or [])]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
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
    timed_out = False
    try:
        out, err = proc.communicate(timeout=max(1, int(timeout)))
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            proc.kill()
        except Exception:
            pass
        out, err = proc.communicate()
    out = (out or "")[:max_output]
    err = (err or "")[:max_output]
    return {
        "ok": (not timed_out) and proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": _truncate(out),
        "stderr": _truncate(err),
        "timed_out": timed_out,
        "error": "运行超时" if timed_out else "",
    }
