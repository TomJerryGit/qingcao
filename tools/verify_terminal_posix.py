# -*- coding: utf-8 -*-
"""R4：POSIX PTY 验证（macOS/Linux）。"""

import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ui.pty_session import PtySession  # noqa: E402
from ui.terminal_screen import TerminalScreen  # noqa: E402


def main():
    if sys.platform == "win32":
        print("[posix-pty] SKIP: Windows")
        return 0
    session = PtySession(["/bin/sh"])
    screen = TerminalScreen(24, 80)
    try:
        session.write("echo qc-posix-ok\r")
        deadline = time.time() + 10
        text = ""
        while time.time() < deadline:
            data = session.read_available()
            if data:
                text += data
                screen.feed(data)
            if "qc-posix-ok" in text:
                break
            time.sleep(0.05)
        echo_ok = "qc-posix-ok" in text
        session.write("printf '\\033[?1049h'\r")
        time.sleep(0.5)
        data = session.read_available()
        if data:
            screen.feed(data)
        alt_ok = "\\x1b[?1049h" in (text + (data or "")) or screen.alt
        print(
            "[posix-pty] echo=%s alt-screen=%s"
            % ("PASS" if echo_ok else "FAIL", "PASS" if alt_ok else "FAIL")
        )
        return 0 if (echo_ok and alt_ok) else 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
