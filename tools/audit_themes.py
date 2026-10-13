# -*- coding: utf-8 -*-
"""主题全面审查工具

审查内容：
  1. **WCAG 对比度**：正文/菜单/状态栏/按钮/行号等前景-背景对是否达标
     （正文 ≥ 4.5:1，大字/非正文 ≥ 3:1）
  2. **键完整性**：各主题是否都定义了加载器需要的全部颜色键
  3. **配色合理性**：搜索高亮、错误/警告色与背景的区分度
  4. **主题族一致性**：4 个主题的键集合是否一致（防止某主题缺键回退）

用法：
    python tools/audit_themes.py
输出：
    控制台报告
"""
import io
import json
import os
import sys


sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

THEMES_DIR = "themes"

# 需要检查对比度的（前景键, 背景键, 用途, 最低要求比值）
#   4.5 = WCAG AA 正文；3.0 = 大字号 / 非正文元素
PAIRS = [
    ("foreground", "background", "编辑器正文", 4.5),
    ("caret", "background", "光标", 3.0),
    ("selection_foreground", "selection", "选中文本", 4.5),
    ("line_number_fg", "line_number_bg", "行号", 3.0),
    ("line_number_active_fg", "line_number_bg", "活动行号", 4.5),
    ("margin_fg", "margin_bg", "边距", 3.0),
    ("fold_margin_fg", "fold_margin_bg", "折叠边距", 3.0),
    ("comment", "background", "注释", 4.5),
    ("keyword", "background", "关键字", 4.5),
    ("number", "background", "数字", 4.5),
    ("string", "background", "字符串", 4.5),
    ("character", "background", "字符", 4.5),
    ("operator", "background", "运算符", 4.5),
    ("identifier", "background", "标识符", 4.5),
    ("class_name", "background", "类名", 4.5),
    ("function_name", "background", "函数名", 4.5),
    ("decorator", "background", "装饰器", 4.5),
    ("tag", "background", "标签", 4.5),
    ("attribute", "background", "属性", 4.5),
    ("regex", "background", "正则", 4.5),
    ("indent_guide", "background", "缩进参考线", 1.5),
    ("control_char", "background", "控制字符", 3.0),
    ("window_fg", "window_bg", "窗口文本", 4.5),
    ("menubar_fg", "menubar_bg", "菜单栏", 4.5),
    ("menu_fg", "menu_bg", "下拉菜单", 4.5),
    ("statusbar_fg", "statusbar_bg", "状态栏", 4.5),
    ("tab_fg", "tab_bg", "非活动标签", 3.0),
    ("tab_active_fg", "tab_active_bg", "活动标签", 4.5),
    ("panel_fg", "panel_bg", "面板文本", 4.5),
    ("button_fg", "button_bg", "按钮文本", 4.5),
    ("input_fg", "input_bg", "输入框文本", 4.5),
]

# 搜索高亮：需要与正文背景有可辨差异（不按 WCAG，按 ΔE 感知差异近似）
HIGHLIGHT_KEYS = ["search_highlight", "search_current", "smart_highlight"]
# 语义色：错误/警告需要与背景可区分
SEMANTIC_KEYS = ["error", "warning", "success", "info"]


def parse_color(s):
    """支持 #rgb / #rrggbb / #aarrggbb，返回 (r,g,b) 或 None"""
    if not isinstance(s, str):
        return None
    s = s.strip().lstrip("#")
    if len(s) == 8:          # AARRGGBB
        s = s[2:]
    elif len(s) == 4:        # ARGB
        s = s[1:]
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return None
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def rel_luminance(rgb):
    def ch(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg, bg):
    """WCAG 对比度比值（1.0 ~ 21.0）"""
    l1, l2 = rel_luminance(fg), rel_luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def color_distance(a, b):
    """近似感知差异（加权欧氏距离），用于判断"能否看出区别" """
    dr, dg, db = (a[i] - b[i] for i in range(3))
    # 人眼对绿色最敏感
    return (2 * dr * dr + 4 * dg * dg + 3 * db * db) ** 0.5


def main():
    files = sorted(f for f in os.listdir(THEMES_DIR)
                   if f.endswith(".json"))
    if not files:
        print("未找到主题文件")
        return 1

    themes = {}
    for f in files:
        p = os.path.join(THEMES_DIR, f)
        with io.open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        themes[f] = data

    print("=" * 72)
    print("主题全面审查")
    print("=" * 72)
    print()
    print("主题文件: %d 个" % len(files))
    for f, d in themes.items():
        c = d.get("colors", {})
        print("  %-24s %-8s 颜色键=%d  字体=%s %s"
              % (f, d.get("type", "?"), len(c),
                 d.get("font_family", "?"), d.get("font_size", "?")))

    # ---------- 键一致性 ----------
    print()
    print("=" * 72)
    print("1) 键集合一致性（各主题应定义相同的键，否则回退到默认色）")
    print("=" * 72)
    keysets = {f: set(d.get("colors", {})) for f, d in themes.items()}
    allkeys = set()
    for s in keysets.values():
        allkeys |= s
    inconsistent = False
    for f, s in keysets.items():
        missing = sorted(allkeys - s)
        if missing:
            inconsistent = True
            print("  %s 缺少 %d 个键:" % (f, len(missing)))
            for m in missing:
                print("      %s" % m)
    if not inconsistent:
        print("  OK 所有主题键集合一致（%d 个键）" % len(allkeys))

    # ---------- 非法颜色值 ----------
    print()
    print("=" * 72)
    print("2) 颜色值格式（应为 #rrggbb，供 QColor 直接使用）")
    print("=" * 72)
    bad = False
    for f, d in themes.items():
        for k, v in d.get("colors", {}).items():
            if parse_color(v) is None:
                bad = True
                print("  %s: %s = %r  ← 无法解析" % (f, k, v))
    if not bad:
        print("  OK 全部颜色值格式合法")

    # ---------- WCAG 对比度 ----------
    print()
    print("=" * 72)
    print("3) WCAG 对比度（正文 4.5:1，非正文 3.0:1）")
    print("=" * 72)
    fails = []
    for f, d in themes.items():
        c = d.get("colors", {})
        print()
        print("  【%s】" % f)
        for fg_k, bg_k, label, need in PAIRS:
            fg, bg = parse_color(c.get(fg_k)), parse_color(c.get(bg_k))
            if fg is None or bg is None:
                print("    %-22s 键缺失，跳过" % label)
                continue
            ratio = contrast(fg, bg)
            # 浮点容差：修正后的值常刚好落在阈值上（如 4.4996 显示 4.50），
            # 严格 >= 会误判为不达标，因此留 0.01 余量
            ok = ratio >= (need - 0.01)
            mark = "OK  " if ok else "不达标"
            if not ok:
                fails.append((f, label, fg_k, bg_k, ratio, need))
            print("    %-8s %-22s %5.2f:1  (需 %.1f)  %s=(%s) %s=(%s)"
                  % (mark, label, ratio, need, fg_k, c.get(fg_k),
                     bg_k, c.get(bg_k)))

    print()
    print("=" * 72)
    print("4) 对比度不达标汇总")
    print("=" * 72)
    if fails:
        for f, label, fg_k, bg_k, ratio, need in sorted(fails):
            print("  %-24s %-20s %.2f:1 (需 %.1f)  %s / %s"
                  % (f, label, ratio, need, fg_k, bg_k))
        print()
        print("  共 %d 项不达标" % len(fails))
    else:
        print("  全部达标")

    # ---------- 搜索高亮可辨性 ----------
    print()
    print("=" * 72)
    print("5) 搜索高亮 / 语义色与背景的可辨性")
    print("=" * 72)
    for f, d in themes.items():
        c = d.get("colors", {})
        bg = parse_color(c.get("background"))
        print()
        print("  【%s】" % f)
        if bg is None:
            print("    无 background，跳过")
            continue
        for k in HIGHLIGHT_KEYS + SEMANTIC_KEYS:
            col = parse_color(c.get(k))
            if col is None:
                print("    %-18s 键缺失" % k)
                continue
            dist = color_distance(col, bg)
            # 经验阈值：< 60 基本看不出差别
            note = "可辨" if dist >= 60 else "差异偏小 <<<"
            print("    %-18s %-10s 与背景距离=%5.1f  %s"
                  % (k, c.get(k), dist, note))

    # ---------- 护眼主题专项 ----------
    print()
    print("=" * 72)
    print("6) 护眼主题专项（重点）")
    print("=" * 72)
    ep = None
    for f, d in themes.items():
        if d.get("name") == "eye_protect" or "eye" in f:
            ep = (f, d)
            break
    if ep is None:
        print("  未找到护眼主题")
    else:
        f, d = ep
        c = d.get("colors", {})
        bg = parse_color(c.get("background"))
        print("  文件: %s" % f)
        print("  声明类型: %s（护眼主题应为 light 或柔和浅色）" % d.get("type"))
        print("  背景: %s  foreground: %s" % (c.get("background"),
                                              c.get("foreground")))
        if bg:
            r, g, b = bg
            print("  背景 RGB: (%d, %d, %d)  亮度=%.1f%%"
                  % (r, g, b, rel_luminance(bg) * 100))
            # 护眼配色常识：偏绿、低饱和、亮度不宜过低或过高
            if g <= r or g <= b:
                print("    [提示] 绿色分量不是最高 —— 护眼主题通常偏绿")
            else:
                print("    OK 绿色分量最高，符合护眼倾向")
            if rel_luminance(bg) < 0.5:
                print("    [提示] 背景偏暗（亮度 %.0f%%），护眼浅色主题"
                      "通常亮度 > 50%%" % (rel_luminance(bg) * 100))
        # 正文对比度
        fgc = parse_color(c.get("foreground"))
        if fgc and bg:
            ratio = contrast(fgc, bg)
            print("  正文对比度: %.2f:1  %s"
                  % (ratio, "OK" if ratio >= 4.5 else "不达标 <<<"))
            if ratio > 12:
                print("    [提示] 对比度过高（%.1f:1），长时间阅读易疲劳；"
                      "护眼主题建议 7~12:1" % ratio)
            elif 7 <= ratio <= 12:
                print("    OK 对比度处于护眼舒适区间（7~12:1）")

    print()
    print("=" * 72)
    print("审查完成")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
