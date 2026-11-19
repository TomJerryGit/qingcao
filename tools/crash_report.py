# -*- coding: utf-8 -*-
"""一键导出本地崩溃报告（opt-in，不上传）。"""

import argparse
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.crash_report import build_report, write_report  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump-dir", default="data/crashes")
    ap.add_argument("--out", default="")
    ap.add_argument("--exception", default="")
    args = ap.parse_args(argv)
    report = build_report(args.dump_dir, exception=args.exception)
    out = args.out or os.path.join(ROOT, "data", "crash_report.json")
    write_report(out, report)
    print("[crash-report] OK %s (%d dumps)" % (out, len(report["dumps"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
