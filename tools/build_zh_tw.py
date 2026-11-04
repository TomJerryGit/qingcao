# -*- coding: utf-8 -*-
"""生成繁体中文语言包（v2.21 P1-2）

源：locale/zh_CN/strings.json（键=简体原文）
输出：locale/zh_TW/strings.json（键=简体原文，值=繁体译文）

依赖（仅生成时）：pip install opencc-python-reimplemented
    python tools/build_zh_tw.py
"""

import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "locale", "zh_CN", "strings.json")
OUT = os.path.join(ROOT, "locale", "zh_TW", "strings.json")
# 术语级修正（s2twp 已覆盖大部分；个别 UI 术语强制统一）
OVERRIDES = {
    "文件": "檔案",
    "文件夹": "資料夾",
    "默认": "預設",
    "设置": "設定",
    "插件": "外掛",
    "插件市场": "外掛市場",
    "首选项": "偏好設定",
    "界面": "介面",
    "光标": "游標",
    "粘贴": "貼上",
    "复制": "複製",
    "剪切": "剪下",
    "保存": "儲存",
    "另存为": "另存新檔",
    "撤销": "復原",
    "重做": "重做",
    "网络": "網路",
    "信息": "資訊",
    "打印": "列印",
    "打印预览": "預覽列印",
    "视频": "影片",
    "质量": "品質",
    "配置": "設定",
}


def main():
    try:
        import opencc
    except ImportError:
        print("需要 opencc：pip install opencc-python-reimplemented", file=sys.stderr)
        return 1
    conv = opencc.OpenCC("s2twp")
    src = json.load(io.open(SRC, encoding="utf-8"))
    # 合并“可翻译语料”（部分用户可见字符串不在模板提取结果中）
    corpus_path = os.path.join(ROOT, "locale", "zh_CN", "translatable.json")
    keys = list(src)
    if os.path.isfile(corpus_path):
        corpus = json.load(io.open(corpus_path, encoding="utf-8"))
        for s in corpus:
            if s not in src and s not in keys:
                keys.append(s)
    out = {}
    for key in keys:
        tw = conv.convert(key) if any("\u4e00" <= c <= "\u9fff" for c in key) else key
        if key in OVERRIDES:
            tw = OVERRIDES[key]
        out[key] = tw
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(
        json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True)
    )
    print("[zh_TW] 生成 %d 条 -> %s" % (len(out), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
