# -*- coding: utf-8 -*-
"""P0 稳定性：连续多次全量分片测试（soak）。崩溃即停并保留日志。"""

import argparse
import os
import subprocess
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--shards", type=int, default=3)
    ap.add_argument("--log-dir", default="data/soak_logs")
    args = ap.parse_args(argv)
    os.makedirs(os.path.join(ROOT, args.log_dir), exist_ok=True)
    results = []
    for i in range(1, max(1, args.runs) + 1):
        log = os.path.join(ROOT, args.log_dir, "run_%02d.log" % i)
        t0 = time.time()
        with open(log, "w", encoding="utf-8") as f:
            rc = subprocess.call(
                [
                    sys.executable,
                    "tools/run_tests_sharded.py",
                    "--shards",
                    str(args.shards),
                    "--retries",
                    "1",
                    "--parallel",
                ],
                cwd=ROOT,
                stdout=f,
                stderr=subprocess.STDOUT,
            )
        dur = round(time.time() - t0, 1)
        results.append((i, rc, dur))
        print("[soak] run %d/%d rc=%d %.1fs -> %s" % (i, args.runs, rc, dur, log), flush=True)
        if rc != 0:
            print("[soak] 失败停止，保留日志", flush=True)
            return rc
    print("[soak] 全部 %d 轮通过 ✅" % len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
