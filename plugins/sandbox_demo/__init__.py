# -*- coding: utf-8 -*-
"""沙箱示例插件（B-4）：只实现只读 symbols 扩展点

manifest 中 "sandbox": true → 主进程不导入本文件；宿主通过子进程 RPC
调用 symbols()。默认 enabled=false，启用方式：把 manifest 的 enabled
改为 true（或插件管理器里启用后重启）。
"""


class Plugin:
    NAME = "sandbox_demo"
    VERSION = "1.0.0"

    def on_activate(self):
        """沙箱模式下由宿主代理调用，这里保留空实现以过 conformance"""
        pass

    def on_deactivate(self):
        pass

    def symbols(self, text, filepath="", language=""):
        """仅对 .sdemo 文件返回大纲符号（避免影响其它文档）"""
        if not (filepath or "").endswith(".sdemo"):
            return []
        items = []
        for idx, line in enumerate((text or "").splitlines()):
            s = line.strip()
            if s.startswith("## "):
                items.append({"name": s[3:].strip(),
                              "type": "namespace", "line": idx})
        return items