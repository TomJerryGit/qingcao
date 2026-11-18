# -*- coding: utf-8 -*-
"""字数统计（沙箱试点插件）。

宿主通过 RPC 传入当前文本，插件只返回状态栏文本。
"""


class Plugin:
    NAME = "wordcount_sandbox"
    VERSION = "1.0.3"

    def on_activate(self):
        return True

    def on_deactivate(self):
        return True

    def status_text(self, text=""):
        text = text or ""
        cfg = getattr(self, "_config", {})
        max_chars = int(cfg.get("max_chars") or 200000)
        if len(text) > max_chars:
            text = text[:max_chars]
        chars = len(text)
        words = len([w for w in text.replace("\n", " ").split(" ") if w.strip()])
        lines = text.count("\n") + 1 if text else 0
        mode = str(cfg.get("count_mode") or "chars")
        if mode == "words":
            return "词数: %d | 行: %d" % (words, lines)
        return "字数: %d | 字符: %d | 行: %d" % (words, chars, lines)

    def menu_items(self):
        return []

    def config_schema(self):
        return {
            "count_mode": {"type": "str", "label": "统计口径", "default": "chars"},
            "max_chars": {"type": "int", "label": "最大统计字符", "default": 200000},
        }

    def on_config(self, values):
        self._config = dict(values or {})
        return True
