# -*- coding: utf-8 -*-
"""测试辅助：读取 MainWindow 相关全部源码（v2.18 重构后方法分散到 mixins）"""

import io
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_main_ui_source() -> str:
    paths = [os.path.join(ROOT, "ui", "main_window.py")]
    mixin_dir = os.path.join(ROOT, "ui", "mixins")
    if os.path.isdir(mixin_dir):
        paths.extend(
            os.path.join(mixin_dir, n) for n in sorted(os.listdir(mixin_dir)) if n.endswith(".py")
        )
    return "\n".join(io.open(p, encoding="utf-8").read() for p in paths)


def read_market_source() -> str:
    """读取插件市场拆分后的三个模块源码（v2.23 D3）。"""
    paths = [
        os.path.join(ROOT, "ui", "plugin_store.py"),
        os.path.join(ROOT, "ui", "plugin_client.py"),
        os.path.join(ROOT, "ui", "plugin_detail.py"),
    ]
    return "\n".join(io.open(p, encoding="utf-8").read() for p in paths)
