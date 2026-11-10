# -*- coding: utf-8 -*-
"""应用已填写的批次工作清单（zh/ja/ko TSV）到 locale 字典。

python tools/i18n_apply_batch.py locale/_batch4_worklist.tsv [--check]
校验: ja/ko 非空、不得与中文相同（纯 ASCII 除外）、占位符 {} / %s / %d 数量一致。
"""

import argparse
import io
import json
import os
import re
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALE = os.path.join(ROOT, "locale")

_CJK = re.compile(r"[\u3400-\u9fff]")
_PLACEHOLDER = re.compile(r"\{\w*\}|%[sd]")


def _load(path):
    try:
        return json.load(io.open(path, encoding="utf-8"))
    except Exception:
        return {}


def parse_tsv(path):
    rows = []
    with io.open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.rstrip("\n")
            if not line or line.startswith("zh\t"):
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            rows.append((parts[0], parts[1].strip(), parts[2].strip()))
    return rows


def validate(zh, ja, ko):
    problems = []
    for label, val in (("ja", ja), ("ko", ko)):
        if not val:
            continue
        if val == zh and _CJK.search(zh):
            problems.append("%s 未翻译: %s" % (label, zh))
        if len(_PLACEHOLDER.findall(val)) != len(_PLACEHOLDER.findall(zh)):
            problems.append("%s 占位符数量不匹配: %s" % (label, zh))
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv")
    ap.add_argument("--check", action="store_true", help="只校验不写入")
    ap.add_argument("--locale-dir", default=LOCALE)
    args = ap.parse_args()
    rows = parse_tsv(args.tsv)
    problems = []
    filled = []
    for zh, ja, ko in rows:
        if not ja and not ko:
            continue
        p = validate(zh, ja, ko)
        if p:
            problems.extend(p)
        else:
            filled.append((zh, ja, ko))
    if problems:
        for p in problems:
            print("[apply] ERR", p)
        return 1
    if args.check:
        print("[apply] 校验通过: 可写入 %d 条" % len(filled))
        return 0
    for lang, idx in (("ja_JP", 1), ("ko_KR", 2)):
        path = os.path.join(args.locale_dir, lang, "strings.json")
        data = _load(path)
        for zh, ja, ko in filled:
            val = ja if idx == 1 else ko
            if val:
                data[zh] = val
        os.makedirs(os.path.dirname(path), exist_ok=True)
        io.open(path, "w", encoding="utf-8", newline="\n").write(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        )
        print("[apply] %s 条目 %d" % (lang, len(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
