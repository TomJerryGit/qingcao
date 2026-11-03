# -*- coding: utf-8 -*-
"""提取 UI 中文串生成 i18n 模板（v2.18.x P3）

用法:
    python tools/extract_i18n_strings.py [--out locale/zh_CN/strings.json]
"""

import argparse
import ast
import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _has_cjk(s):
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


def extract_from_source(src):
    out = {}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value.strip()
            if 1 <= len(s) <= 120 and _has_cjk(s):
                out[s] = s
    return out


def extract_tree(root, only_dirs=("ui", "core", "app")):
    out = {}
    for d in only_dirs:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, files in os.walk(base):
            dirnames[:] = [n for n in dirnames if n != "__pycache__"]
            for f in files:
                if not f.endswith(".py"):
                    continue
                try:
                    src = io.open(
                        os.path.join(dirpath, f), encoding="utf-8", errors="replace"
                    ).read()
                except Exception:
                    continue
                out.update(extract_from_source(src))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "locale", "zh_CN", "strings.json"))
    args = ap.parse_args()
    strings = extract_tree(ROOT)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    io.open(args.out, "w", encoding="utf-8", newline="\n").write(
        json.dumps(strings, ensure_ascii=False, indent=2, sort_keys=True)
    )
    print("[i18n] 提取 %d 条中文串 -> %s" % (len(strings), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
