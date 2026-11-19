# -*- coding: utf-8 -*-
"""ProcDump 自动附加/启动崩溃取证（Sprint 1）。

用法：
  python tools/crash_attach.py -- python -c "..."
  python tools/crash_attach.py --pid 1234
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


def build_command(exe, dump_dir, target=None, pid=None):
    cmd = [exe, "-accepteula", "-ma", "-e", "1"]
    if pid is not None:
        return cmd + [str(pid), dump_dir]
    if not target:
        raise ValueError("需要 target 命令或 --pid")
    return cmd + ["-x", dump_dir] + list(target)


def _new_dumps(dump_dir, before):
    try:
        names = {f for f in os.listdir(dump_dir) if f.lower().endswith(".dmp")}
    except OSError:
        return []
    return sorted(names - before)


def capture(dump_dir, target=None, pid=None):
    exe = find_procdump()
    if exe is None:
        return (False, "缺少 ProcDump：请放到 tools/procdump/")
    os.makedirs(dump_dir, exist_ok=True)
    before = {f for f in os.listdir(dump_dir) if f.lower().endswith(".dmp")}
    cmd = build_command(exe, dump_dir, target=target, pid=pid)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception as e:
        return (False, str(e))
    new = _new_dumps(dump_dir, before)
    if not new:
        return (False, (proc.stdout or "") + (proc.stderr or ""))
    return (True, os.path.join(dump_dir, new[-1]))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump-dir", default="data/crashes")
    ap.add_argument("--pid", type=int, default=None)
    ap.add_argument("target", nargs=argparse.REMAINDER)
    args = ap.parse_args(argv)
    target = args.target
    if target and target[0] == "--":
        target = target[1:]
    if args.pid is None and not target:
        ap.error("需要目标命令或 --pid")
    ok, result = capture(args.dump_dir, target=target if target else None, pid=args.pid)
    print(("[crash-attach] " + ("OK " if ok else "FAIL ")) + str(result))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
