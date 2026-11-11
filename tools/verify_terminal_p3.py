# -*- coding: utf-8 -*-
"""终端 P3 真机验证：真实 PTY + alt-screen + raw 回显（无 vim 时用 Python 子程序）。"""

import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ui.pty_session import PtySession  # noqa: E402
from ui.terminal_screen import TerminalScreen  # noqa: E402


CHILD = r"""
import os, sys, time
os.write(1, b"\x1b[?1049h\x1b[2J\x1b[HALT-SCREEN-OK\r\n")
os.write(1, b"\x1b[?1049l")
line = sys.stdin.readline()
os.write(1, ("RAW-OK:" + line.strip() + "\r\n").encode())
sys.stdout.flush()
time.sleep(0.2)
"""


def main():
    session = PtySession(argv=[sys.executable, "-c", CHILD])
    screen = TerminalScreen(24, 80)
    seen = ""
    deadline = time.time() + 10
    try:
        while time.time() < deadline:
            data = session.read_available()
            if data:
                seen += data
                screen.feed(data)
            if "RAW-OK" in seen:
                break
            time.sleep(0.02)
        session.write("PING\r\n")
        deadline = time.time() + 5
        while time.time() < deadline and "RAW-OK:PING" not in seen:
            data = session.read_available()
            if data:
                seen += data
                screen.feed(data)
            time.sleep(0.02)
    finally:
        session.close()
    ok1 = "ALT-SCREEN-OK" in seen
    ok2 = "RAW-OK:PING" in seen
    print("[p3] alt-screen 序列:", "PASS" if ok1 else "FAIL")
    print("[p3] raw 输入回显:", "PASS" if ok2 else "FAIL")
    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    sys.exit(main())
