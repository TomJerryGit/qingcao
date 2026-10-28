# -*- coding: utf-8 -*-
"""测试分片 + 重试 + 崩溃定位工具（稳定性专项）

用法：
    python tools/run_tests_sharded.py                  # 2 片，重试 1 次
    python tools/run_tests_sharded.py --shards 3
    python tools/run_tests_sharded.py --localize       # 崩溃后逐文件定位
"""
import argparse
import glob
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(ROOT, "data", "test_shards")


def collect_test_files(root=ROOT):
    return sorted(glob.glob(os.path.join(root, "tests", "test_*.py")))


def make_shards(files, shards):
    """按文件轮转切分；返回非空分片列表"""
    buckets = [[] for _ in range(max(1, shards))]
    for i, f in enumerate(files):
        buckets[i % len(buckets)].append(f)
    return [b for b in buckets if b]


def _env():
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_files(files, timeout=None):
    """运行给定测试文件；返回 (returncode, output, crashed)"""
    cmd = [sys.executable, "-X", "faulthandler", "-m", "pytest"] + files + [
        "-q", "-p", "no:cacheprovider"]
    try:
        proc = subprocess.run(cmd, cwd=ROOT, env=_env(), timeout=timeout,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        rc = proc.returncode
        out = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return -999, "[timeout]", True
    # pytest 退出码 5 = 没有收集到测试（如按条件 deselected），不算崩溃
    crashed = rc < 0
    if rc == 5:
        return rc, out, False
    return rc, out, crashed


def run_shard(files, retries, name, log_dir):
    os.makedirs(log_dir, exist_ok=True)
    log = os.path.join(log_dir, "%s.log" % name)
    last_out = ""
    for attempt in range(1, retries + 1):
        rc, out, crashed = run_files(files)
        last_out = out
        with open(log, "w", encoding="utf-8", newline="\n") as f:
            f.write(out)
        print("[shard %s] attempt %d/%d rc=%s crash=%s files=%d"
              % (name, attempt, retries, rc, crashed, len(files)))
        if rc in (0, 5):
            return True, rc, crashed, attempt
    return False, rc, crashed, retries


def localize(files, log_dir):
    """崩溃定位：逐文件运行，找出崩溃/失败的具体文件"""
    os.makedirs(log_dir, exist_ok=True)
    bad = []
    for f in files:
        rc, out, crashed = run_files([f])
        if rc == 5:
            tag = "skip (no tests)"
        else:
            tag = "CRASH" if crashed else ("FAIL" if rc != 0 else "ok")
        print("[localize] %-60s %s (rc=%s)" % (os.path.basename(f),
                                               tag, rc))
        if rc not in (0, 5):
            bad.append((f, rc, crashed))
            with open(os.path.join(log_dir, "crashed_%s.log"
                                   % os.path.basename(f)), "w",
                      encoding="utf-8", newline="\n") as fh:
                fh.write(out)
    return bad


def main():
    ap = argparse.ArgumentParser(description="分片测试 + 重试 + 崩溃定位")
    ap.add_argument("--shards", type=int, default=2)
    ap.add_argument("--retries", type=int, default=1)
    ap.add_argument("--localize", action="store_true",
                    help="失败/崩溃后逐文件定位")
    ap.add_argument("--parallel", action="store_true",
                    help="并行执行各分片")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--log-dir", default=LOG_DIR)
    args = ap.parse_args()
    files = collect_test_files()
    if not files:
        print("[sharded] 未找到测试文件")
        return 1
    shards = make_shards(files, args.shards)
    print("[sharded] %d 个测试文件 → %d 片" % (len(files), len(shards)))
    failed = []
    if args.parallel and len(shards) > 1:
        from concurrent.futures import ThreadPoolExecutor
        results = {}
        with ThreadPoolExecutor(
                max_workers=max(1, args.workers)) as ex:
            futures = {
                ex.submit(run_shard, shard, max(1, args.retries),
                          "part%d" % (i + 1), args.log_dir): i
                for i, shard in enumerate(shards)}
            for fut, i in futures.items():
                results[i] = fut.result()
        for i in sorted(results):
            ok, rc, crashed, attempts = results[i]
            if not ok:
                failed.append((i + 1, shards[i], rc, crashed))
                print("[shard part%d] FAILED rc=%s crashed=%s"
                      % (i + 1, rc, crashed))
    else:
        for idx, shard in enumerate(shards, 1):
            ok, rc, crashed, attempts = run_shard(
                shard, max(1, args.retries), "part%d" % idx,
                args.log_dir)
            if not ok:
                failed.append((idx, shard, rc, crashed))
                print("[shard part%d] FAILED rc=%s crashed=%s"
                      % (idx, rc, crashed))
    if not failed:
        print("[sharded] 全部 %d 片通过 ✅" % len(shards))
        return 0
    print("[sharded] 失败片数: %d" % len(failed))
    if args.localize:
        for idx, shard, rc, crashed in failed:
            print("[sharded] 定位 part%d ..." % idx)
            bad = localize(shard, args.log_dir)
            for f, frc, fcrash in bad:
                print("   %-60s rc=%s crash=%s"
                      % (os.path.basename(f), frc, fcrash))
    return 1


if __name__ == "__main__":
    sys.exit(main())