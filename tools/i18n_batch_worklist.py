# -*- coding: utf-8 -*-
"""生成 ja/ko 批次工作清单（key 驱动）。

python tools/i18n_batch_worklist.py --limit 180
输出: locale/_batch4_worklist.tsv（zh / ja / ko / freq；ja/ko 留空待填）
"""

import argparse
import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "locale", "zh_CN", "translatable.json")
JA = os.path.join(ROOT, "locale", "ja_JP", "strings.json")
KO = os.path.join(ROOT, "locale", "ko_KR", "strings.json")
OUT = os.path.join(ROOT, "locale", "_batch4_worklist.tsv")
SCAN_DIRS = ("core", "ui", "app", "infrastructure")


def _load_json(path):
    try:
        return json.load(io.open(path, encoding="utf-8"))
    except Exception:
        return {}


def count_usage(corpus):
    texts = []
    for d in SCAN_DIRS:
        base = os.path.join(ROOT, d)
        for dp, _dn, fn in os.walk(base):
            if "__pycache__" in dp:
                continue
            for f in fn:
                if f.endswith(".py"):
                    try:
                        texts.append(
                            io.open(os.path.join(dp, f), encoding="utf-8", errors="ignore").read()
                        )
                    except OSError:
                        pass
    blob = "\n".join(texts)
    return {s: blob.count(s) for s in corpus}


def build(limit=180):
    corpus = json.load(io.open(CORPUS, encoding="utf-8"))
    ja = _load_json(JA)
    ko = _load_json(KO)
    freq = count_usage(corpus)
    pending = [s for s in corpus if s not in ja or s not in ko]
    pending.sort(key=lambda s: (-freq.get(s, 0), len(s)))
    return pending[:limit], freq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=180)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    rows, freq = build(args.limit)
    with io.open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("zh\tja\tko\tfreq\n")
        for s in rows:
            f.write("%s\t\t\t%d\n" % (s.replace("\t", " "), freq.get(s, 0)))
    print("[worklist] %d 条 -> %s" % (len(rows), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
