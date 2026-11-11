# -*- coding: utf-8 -*-
"""终端 P7：vim 真机验证（无 vim 时 SKIP 并提示安装）。"""

import os
import shutil
import sys
import tempfile
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ui.pty_session import PtySession  # noqa: E402
from ui.terminal_screen import TerminalScreen  # noqa: E402


def main():
    vim = shutil.which("vim") or shutil.which("nvim")
    if not vim:
        print("[p7] SKIP: 未安装 vim/nvim（Windows: winget install vim.vim 或 gvim）")
        return 0
    tmp = tempfile.mkdtemp(prefix="qc_vim_")
    target = os.path.join(tmp, "hello.txt")
    session = PtySession(argv=[vim, "-u", "NONE", "-N", target])
    screen = TerminalScreen(30, 100)
    seen = ""
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            data = session.read_available()
            if data:
                seen += data
                screen.feed(data)
            if "\x1b[?1049h" in seen:
                break
            time.sleep(0.05)
        session.write("iHello QCP7\x1b:wq\r")
        deadline = time.time() + 15
        while time.time() < deadline:
            data = session.read_available()
            if data:
                seen += data
                screen.feed(data)
            if (
                os.path.isfile(target)
                and "Hello QCP7" in open(target, encoding="utf-8", errors="ignore").read()
            ):
                break
            time.sleep(0.1)
    finally:
        session.close()
    alt = "\x1b[?1049h" in seen
    if os.path.isfile(target):
        content = open(target, encoding="utf-8", errors="ignore").read()
        print(
            "[p7] vim=%s alt-screen=%s 写入内容=%r"
            % (vim, "PASS" if alt else "FAIL", content.strip()[:40])
        )
        return 0 if ("Hello QCP7" in content and alt) else 1
    print("[p7] vim 运行但未生成文件（alt-screen=%s）" % alt)
    return 1


if __name__ == "__main__":
    sys.exit(main())
