# -*- coding: utf-8 -*-
"""计算护眼主题各不达标颜色的最小修正值

对每个不达标的（前景, 背景, 目标比值），沿"远离背景色"的方向调整
前景亮度，找到刚好达标的最小改动 —— 保持原有色相不变，避免"修完
看起来像换了主题"。
"""
import colorsys
import sys


sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def hex2rgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def rgb2hex(t):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(x))) for x in t)


def lum(rgb):
    def ch(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg, bg):
    l1, l2 = lum(fg), lum(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def fix(fg_hex, bg_hex, need):
    """保持色相/饱和度，调整明度直到达标"""
    fg, bg = hex2rgb(fg_hex), hex2rgb(bg_hex)
    cur = ratio(fg, bg)
    if cur >= need:
        return fg_hex, cur, "已达标"

    h, l, s = colorsys.rgb_to_hls(*[x / 255.0 for x in fg])
    # 背景亮 -> 前景要变暗；背景暗 -> 前景要变亮
    darken = lum(bg) > 0.5
    best = None
    steps = 200
    for i in range(1, steps + 1):
        if darken:
            nl = max(0.0, l - (l * i / steps))
        else:
            nl = min(1.0, l + ((1.0 - l) * i / steps))
        r, g, b = colorsys.hls_to_rgb(h, nl, s)
        cand = (r * 255, g * 255, b * 255)
        if ratio(cand, bg) >= need:
            best = (cand, nl)
            break
    if best is None:
        # 极端情况：退到黑白
        cand = (0, 0, 0) if darken else (255, 255, 255)
        return rgb2hex(cand), ratio(cand, bg), "退到极值"
    cand, nl = best
    return rgb2hex(cand), ratio(cand, bg), "明度 %.3f -> %.3f" % (l, nl)


print("=" * 72)
print("护眼主题 对比度修正建议（背景 #c7edcc）")
print("=" * 72)
print()
BG = "#c7edcc"

targets = [
    ("comment", "#6b8e5e", 4.5, "注释"),
    ("button_fg", "#ffffff", 4.5, "按钮文字（背景 button_bg=#4a8f5e）"),
    ("statusbar_fg", "#ffffff", 4.5, "状态栏文字（背景 #4a8f5e）"),
    ("indent_guide", "#9cc9a5", 1.5, "缩进参考线"),
]
for key, val, need, label in targets:
    if key == "button_fg" or key == "statusbar_fg":
        bg = "#4a8f5e"
    else:
        bg = BG
    new, got, how = fix(val, bg, need)
    cur = ratio(hex2rgb(val), hex2rgb(bg))
    flag = "需要修改" if cur < need else "已达标"
    print("  %-14s %s" % (key, label))
    print("      当前 %s  对比度 %.2f:1  %s" % (val, cur, flag))
    if cur < need:
        print("      建议 %s  对比度 %.2f:1  (%s)" % (new, got, how))
    print()

print("=" * 72)
print("其他主题的不达标项")
print("=" * 72)
print()
others = [
    ("light_clean", "#f0f0f0", [
        ("fold_margin_fg", "#a0a0a0", 3.0),
        ("control_char", "#c0c0c0", 3.0),
        ("indent_guide", "#e0e0e0", 1.5),
        ("line_number_fg", "#a0a0a0", 3.0),
        ("margin_fg", "#a0a0a0", 3.0),
    ]),
]
import io
import json


for name, _bg, items in others:
    with io.open("themes/%s.json" % name, encoding="utf-8") as fh:
        data = json.load(fh)
    c = data["colors"]
    print("  【%s】" % name)
    for key, _v, need in items:
        val = c.get(key)
        bg = c.get("background") if key not in (
            "line_number_fg", "margin_fg", "fold_margin_fg") else c.get("line_number_bg")
        if not val or not bg:
            continue
        cur = ratio(hex2rgb(val), hex2rgb(bg))
        if cur < need:
            new, got, how = fix(val, bg, need)
            print("      %-18s %s (对比度 %.2f) -> 建议 %s (%.2f)  bg=%s"
                  % (key, val, cur, new, got, bg))
    print()
