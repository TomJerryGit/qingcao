# -*- coding: utf-8 -*-
"""空白符只读检查（沙箱试点插件，v2.16 P3）。"""

MAX_LINE = 120


class Plugin:
    NAME = "whitespace_sandbox"
    VERSION = "1.0.1"

    def on_activate(self):
        return True

    def on_deactivate(self):
        return True

    def status_text(self, text=""):
        text = text or ""
        lines = len(text.split("\n")) if text else 0
        return "空白符检查: %d 行" % lines

    def diagnostics(self, text=""):
        items = []
        max_line = int(getattr(self, "_config", {}).get("max_line_length", MAX_LINE) or MAX_LINE)
        for i, line in enumerate((text or "").split("\n")):
            if line.rstrip() != line:
                items.append(
                    {
                        "line": i,
                        "col": max(0, len(line.rstrip())),
                        "severity": "warning",
                        "message": "行尾存在空白",
                        "code": "trailing-ws",
                    }
                )
            if line.startswith("\t"):
                items.append(
                    {
                        "line": i,
                        "col": 0,
                        "severity": "info",
                        "message": "使用 Tab 缩进",
                        "code": "tab-indent",
                    }
                )
            if len(line) > max_line:
                items.append(
                    {
                        "line": i,
                        "col": max_line,
                        "severity": "info",
                        "message": "行过长（>%d）" % max_line,
                        "code": "long-line",
                    }
                )
        return items

    def menu_items(self):
        return []

    def config_schema(self):
        return {
            "max_line_length": {"type": "int", "label": "最大行宽", "default": 120},
            "ignore_glob": {"type": "str", "label": "忽略 glob", "default": ""},
        }

    def on_config(self, values):
        self._config = dict(values or {})
        return True
