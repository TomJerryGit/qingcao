# -*- coding: utf-8 -*-
"""PTY 依赖与最小交互会话验证（v2.23 D4）。

python tools/verify_pty.py
"""

import sys
import time


sys.path.insert(
    0,
    __import__("os").path.dirname(
        __import__("os").path.dirname(__import__("os").path.abspath(__file__))
    ),
)


def main():
    try:
        import winpty

        from ui.pty_session import PtySession
    except ImportError as e:
        print("[pty] FAIL 依赖缺失:", e)
        return 1
    print("[pty] pywinpty", getattr(winpty, "__version__", "?"))
    session = None
    try:
        session = PtySession(["cmd.exe", "/Q"])
        time.sleep(0.5)
        session.write("echo qc-pty-ok\r\n")
        ok = session.wait_for("qc-pty-ok", timeout=10)
        print("[pty] 交互输出:", ok)
        print("[pty] alive:", session.is_alive())
        if not ok:
            return 1
        session.write("exit\r\n")
        return 0
    except Exception as e:
        print("[pty] FAIL", e)
        return 1
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    sys.exit(main())
