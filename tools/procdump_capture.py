# -*- coding: utf-8 -*-
"""ProcDump 崩溃取证（WER 不可用时的替代）。

依赖：tools/procdump/procdump64.exe（Sysinternals 官方）。
用法：python tools/procdump_capture.py --dump-dir data/crash_dumps -- python -c "..."
"""

import argparse
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_procdump():
    for name in ("procdump64.exe", "procdump.exe"):
        p = os.path.join(ROOT, "tools", "procdump", name)
        if os.path.isfile(p):
            return p
    return None


def capture(dump_dir, command):
    exe = find_procdump()
    if exe is None:
        return (False, "缺少 ProcDump：请放到 tools/procdump/（Sysinternals）")
    os.makedirs(dump_dir, exist_ok=True)
    cmd = [exe, "-accepteula", "-ma", "-e", "1", "-x", dump_dir] + list(command)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    dumps = [f for f in os.listdir(dump_dir) if f.lower().endswith(".dmp")]
    if not dumps:
        return (False, (proc.stdout or "") + (proc.stderr or ""))
    return (True, os.path.join(dump_dir, sorted(dumps)[-1]))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump-dir", default="data/crash_dumps")
    ap.add_argument("target", nargs=argparse.REMAINDER)
    args = ap.parse_args(argv)
    target = args.target
    if target and target[0] == "--":
        target = target[1:]
    if not target:
        ap.error("需要目标命令")
    ok, result = capture(args.dump_dir, target)
    print(("[procdump] " + ("OK " if ok else "FAIL ")) + str(result))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
