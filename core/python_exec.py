# -*- coding: utf-8 -*-
"""在独立子进程中执行 Python 代码（插件 run_python 用）。"""

import os
import shutil
import subprocess
import sys


def python_executable() -> str:
    base = os.path.basename(sys.executable or "").lower()
    if base.startswith("python"):
        return sys.executable
    return shutil.which("python") or shutil.which("python3") or "python"


def run_python_code(code: str, timeout: int = 30) -> str:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    try:
        from core.subprocess_utils import hidden_kwargs

        kwargs = hidden_kwargs()
    except Exception:
        kwargs = {}
    try:
        result = subprocess.run(
            [python_executable(), "-c", str(code)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            **kwargs,
        )
        out = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            out += "\n[错误: 进程退出代码 %d]" % result.returncode
        return out
    except subprocess.TimeoutExpired:
        return "错误: 执行超时"
    except Exception as e:
        return "错误: %s" % e
