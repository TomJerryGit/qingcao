# -*- coding: utf-8 -*-
"""测试稳定性检查：反复运行全量测试，捕获偶发崩溃（0xC0000005 等）

用法：
    python tools/verify_test_stability.py            # 默认 2 轮
    python tools/verify_test_stability.py --runs 3
    python tools/verify_test_stability.py --runs 2 --quick  # 只跑核心子集
"""
import argparse
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

QUICK_SUBSET = [
    "tests/test_theme_toplevel.py",
    "tests/test_panel_theme_adapt.py",
    "tests/test_menu_checks.py",
    "tests/test_instance_broadcast.py",
    "tests/test_sandbox_config_hot_update.py",
    "tests/test_sandbox_live_diagnostics.py",
]


def main():
    ap = argparse.ArgumentParser(description="测试稳定性检查")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--quick", action="store_true",
                    help="只跑核心子集（更快）")
    args = ap.parse_args()
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONIOENCODING"] = "utf-8"
    targets = list(QUICK_SUBSET) if args.quick else ["tests"]
    cmd = [sys.executable, "-m", "pytest"] + targets + [
        "-q", "-p", "no:cacheprovider"]
    print("[stability] 运行 %d 轮: %s" % (args.runs, " ".join(targets)))
    results = []
    for i in range(1, args.runs + 1):
        print("[stability] 第 %d/%d 轮 ..." % (i, args.runs))
        proc = subprocess.run(cmd, cwd=ROOT, env=env,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        tail = (proc.stdout or "").strip().splitlines()[-1:] or [""]
        summary = tail[0][:120]
        crash = proc.returncode not in (0, 1) or proc.returncode < 0
        print("   rc=%s %s %s" % (proc.returncode,
                                  "CRASH" if crash else "",
                                  summary))
        results.append((proc.returncode, crash, summary))
    bad = [r for r in results if r[1] or r[0] != 0]
    if bad:
        print("[stability] 失败 %d/%d 轮：见上方输出" % (len(bad), args.runs))
        return 1
    print("[stability] 全部 %d 轮通过" % args.runs)
    return 0


if __name__ == "__main__":
    sys.exit(main())