# -*- coding: utf-8 -*-
"""计算按钮/状态栏背景色需要多深，才能让白字达到 4.5:1"""
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


def ratio(a, b):
    l1, l2 = lum(a), lum(b)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


WHITE = (255, 255, 255)
for name, cur in (("button_bg / statusbar_bg", "#4a8f5e"),):
    rgb = hex2rgb(cur)
    h, l, s = colorsys.rgb_to_hls(*[x / 255.0 for x in rgb])
    print("%s 当前 %s  白字对比度 %.2f:1" % (name, cur, ratio(rgb, WHITE)))
    print("  色相 h=%.3f 饱和度 s=%.2f 明度 l=%.3f" % (h, s, l))
    for i in range(1, 400):
        nl = max(0.0, l - (l * i / 400))
        r, g, b = colorsys.hls_to_rgb(h, nl, s)
        cand = (r * 255, g * 255, b * 255)
        if ratio(cand, WHITE) >= 4.5:
            print("  建议 %s  白字对比度 %.2f:1  (明度 %.3f -> %.3f)"
                  % (rgb2hex(cand), ratio(cand, WHITE), l, nl))
            # 同时看黑字对比度
            print("        同色配深字 #2c3e2f: %.2f:1"
                  % ratio(cand, hex2rgb("#2c3e2f")))
            break
    print()
    # 另一方案：保持背景，改用深色文字
    print("  备选方案：保持 %s 背景，按钮文字改用深色" % cur)
    for dark in ("#1e2820", "#14261a", "#0f1c13"):
        print("      %s -> 对比度 %.2f:1" % (dark, ratio(rgb, hex2rgb(dark))))
    print()
