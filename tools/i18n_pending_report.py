# -*- coding: utf-8 -*-
"""i18n 剩余语料分类（v2.19 B1/B2 批次清单）

    python tools/i18n_pending_report.py
输出:
    data/i18n_pending_b1.json  长对话框/说明文案（人工润色批次）
    data/i18n_pending_b2.json  其余短句/错误详情
"""

import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EN = os.path.join(ROOT, "locale", "en_US", "strings.json")
CORPUS = os.path.join(ROOT, "locale", "zh_CN", "translatable.json")


def hit(s, en):
    if s in en:
        return True
    for suf in ("：", ":", "..."):
        if s.endswith(suf) and s[: -len(suf)].strip() in en:
            return True
    return False


def classify(s):
    long = len(s) >= 40 or "\n" in s
    dialog = any(
        k in s
        for k in (
            "请",
            "是否",
            "将",
            "建议",
            "注意",
            "向导",
            "帮助",
            "说明",
            "失败",
            "无法",
            "设置",
        )
    )
    return "b1" if (long and dialog) else "b2"


def main():
    en = json.load(io.open(EN, encoding="utf-8"))
    corpus = json.load(io.open(CORPUS, encoding="utf-8"))
    pending = [s for s in corpus if not hit(s, en)]
    b1 = sorted(s for s in pending if classify(s) == "b1")
    b2 = sorted(s for s in pending if classify(s) == "b2")
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    for name, rows in (("b1", b1), ("b2", b2)):
        io.open(
            os.path.join(ROOT, "data", "i18n_pending_%s.json" % name),
            "w",
            encoding="utf-8",
            newline="\n",
        ).write(json.dumps(rows, ensure_ascii=False, indent=2))
    print("[i18n] 剩余语料=%d  B1(长对话框)=%d  B2(短句)=%d" % (len(pending), len(b1), len(b2)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
