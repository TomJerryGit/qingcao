# -*- coding: utf-8 -*-
"""Lite 模式功能开关：默认隐藏市场/评分/统计等冻结入口。"""
import os


def lite_mode() -> bool:
    """默认 Lite；QINGCAO_LITE=0 可恢复完整入口。"""
    val = (os.environ.get("QINGCAO_LITE", "1") or "1").strip().lower()
    return val not in ("0", "false", "off", "full")


def show_market() -> bool:
    return not lite_mode()
