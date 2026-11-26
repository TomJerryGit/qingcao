# -*- coding: utf-8 -*-
"""主题颜色对比度工具。"""


def readable_fg(bg: str, light: str = "#ffffff", dark: str = "#000000") -> str:
    """返回在 bg 上可读的前景色（黑/白）。"""
    try:
        h = bg.lstrip("#")
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        return dark if lum > 0.55 else light
    except Exception:
        return light
