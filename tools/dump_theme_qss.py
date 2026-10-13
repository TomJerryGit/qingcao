# -*- coding: utf-8 -*-
"""导出护眼主题生成的 QSS，检查其语法与工具栏/菜单栏规则"""
import io
import os
import sys


sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\QingCaoEditor")
os.chdir(r"D:\QingCaoEditor")
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtWidgets import QApplication  # noqa: E402


app = QApplication([])

from infrastructure.theme_loader import ThemeLoader  # noqa: E402


loader = ThemeLoader()
theme = loader.load_by_name("eye_protect")
print("主题:", theme.name, "| colors 对象:", type(theme.colors).__name__)

c = theme.colors
print()
print("关键颜色值:")
for k in ("toolbar_bg", "window_fg", "window_bg", "menubar_bg",
          "menubar_fg", "menu_bg", "menu_fg", "statusbar_bg",
          "statusbar_fg", "button_bg", "button_fg"):
    print("  %-16s = %s" % (k, getattr(c, k, "<缺失>")))

qss = theme.qss or loader._generate_qss(c)
out = os.path.join(os.getcwd(), "_gen_theme.qss")
with io.open(out, "w", encoding="utf-8") as f:
    f.write(qss)
print()
print("生成 QSS 长度:", len(qss), "-> 已写出 _gen_theme.qss")

# 检查关键规则是否存在
print()
print("关键规则检查:")
for sel in ("QToolBar", "QToolBar QToolButton", "QMenuBar", "QMenuBar::item",
            "QStatusBar", "QMainWindow", "QWidget"):
    cnt = qss.count(sel)
    print("  %-26s 出现 %d 次" % (sel, cnt))

# 提取 QToolBar 段落
print()
print("QToolBar / QToolButton 段落原文:")
idx = qss.find("QToolBar")
if idx >= 0:
    print(qss[idx:idx + 700])
else:
    print("  !! QSS 中完全没有 QToolBar 规则")

# 花括号平衡（粗略语法检查）
print()
print("花括号平衡: { =", qss.count("{"), "} =", qss.count("}"))
if qss.count("{") != qss.count("}"):
    print("  !! 不平衡 —— 可能导致后续规则被 Qt 丢弃")
    # 找出不平衡位置
    depth = 0
    for i, ch in enumerate(qss):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                print("  多余的 } 在偏移", i, "附近:", repr(qss[max(0, i - 80):i + 20]))
                break
    if depth > 0:
        print("  还有", depth, "个未闭合的 {")
