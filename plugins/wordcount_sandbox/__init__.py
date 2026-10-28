# -*- coding: utf-8 -*-
"""字数统计（沙箱试点插件）

宿主通过 RPC 传入当前文本，插件只返回状态栏文本。
"""


class Plugin:
    NAME = "wordcount_sandbox"
    VERSION = "1.0.0"

    def on_activate(self):
        return True

    def on_deactivate(self):
        return True

    def status_text(self, text=""):
        text = text or ""
        chars = len(text)
        words = len([w for w in text.replace("\n", " ").split(" ") if w.strip()])
        lines = text.count("\n") + 1 if text else 0
        return "字数: %d | 字符: %d | 行: %d" % (words, chars, lines)

    def menu_items(self):
        return []