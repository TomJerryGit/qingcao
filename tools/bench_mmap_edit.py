# -*- coding: utf-8 -*-
"""mmap 增量编辑可行性基准（v2.18.x P3）

对比 20MB 文本中修改一行：
  1) 全量重写（读写整文件）
  2) mmap 原地补丁（仅写该行范围）
输出 JSON 与建议阈值。
"""

import argparse
import io
import json
import os
import sys
import tempfile
import time


def _make_file(path, lines=1_000_000):
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        for i in range(lines):
            f.write("row %08d abcdefghij\n" % i)


def _rewrite(path, lineno, new_text):
    t0 = time.perf_counter()
    data = io.open(path, encoding="utf-8").read().split("\n")
    old = data[lineno]
    data[lineno] = new_text
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(data))
    return time.perf_counter() - t0, len(old)


def _mmap_patch(path, lineno, new_text):
    import mmap

    t0 = time.perf_counter()
    with io.open(path, "r+b") as f:
        mm = mmap.mmap(f.fileno(), 0)
        try:
            pos = 0
            for _ in range(lineno):
                nl = mm.find(b"\n", pos)
                if nl < 0:
                    raise ValueError("line out of range")
                pos = nl + 1
            nl = mm.find(b"\n", pos)
            end = nl if nl >= 0 else len(mm)
            old = bytes(mm[pos:end])
            cr = old.endswith(b"\r")
            old_clean = old[:-1] if cr else old
            newb = new_text.encode("utf-8")
            if len(newb) != len(old_clean):
                raise ValueError("mmap patch requires equal byte length")
            mm[pos:end] = newb + (b"\r" if cr else b"")
            mm.flush()
        finally:
            mm.close()
    return time.perf_counter() - t0, len(old_clean)


def run(repeats=3):
    tmp = tempfile.mkdtemp(prefix="qc_mmap_bench_")
    path = os.path.join(tmp, "big.txt")
    try:
        _make_file(path)
        size = os.path.getsize(path)
        old_line = "row 00050000 abcdefghij"
        new_line = old_line.replace("abcdefghij", "ABCDEFGHIJ")
        best_rewrite = min(_rewrite(path, 50000, new_line)[0] for _ in range(repeats))
        best_mmap = min(_mmap_patch(path, 50000, new_line)[0] for _ in range(repeats))
        return {
            "size_bytes": size,
            "rewrite_s": round(best_rewrite, 4),
            "mmap_s": round(best_mmap, 4),
            "speedup": round(best_rewrite / max(best_mmap, 1e-9), 1),
        }
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args()
    result = run()
    print("[mmap-bench] %s" % result)
    if args.json:
        io.open(args.json, "w", encoding="utf-8", newline="\n").write(
            json.dumps(result, ensure_ascii=False, indent=2)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
