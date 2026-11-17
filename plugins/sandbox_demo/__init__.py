# -*- coding: utf-8 -*-
"""沙箱示例插件（B-4）：只实现只读 symbols 扩展点。"""


class Plugin:
    NAME = "sandbox_demo"
    VERSION = "1.0.0"

    def on_activate(self):
        """沙箱模式下由宿主代理调用，空实现以过 conformance。"""
        pass

    def on_deactivate(self):
        pass

    def symbols(self, text, filepath="", language=""):
        """仅对 .sdemo 文件返回大纲符号。"""
        if not (filepath or "").endswith(".sdemo"):
            return []
        items = []
        for idx, line in enumerate((text or "").splitlines()):
            s = line.strip()
            if s.startswith("## "):
                items.append({"name": s[3:].strip(), "type": "namespace", "line": idx})
        return items

    def status_text(self, text=""):
        return str(getattr(self, "_config", {}).get("message") or "sandbox-demo")

    def config_schema(self):
        return {
            "message": {"type": "str", "label": "示例消息", "default": "sandbox-demo"},
        }

    def on_config(self, values):
        self._config = dict(values or {})
        return True
