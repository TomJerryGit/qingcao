# -*- coding: utf-8 -*-
"""验证欢迎页随主题变色（此前硬编码深色，与浅色主题冲突）"""
import os
import sys


sys.path.insert(0, r"D:\QingCaoEditor")
os.chdir(r"D:\QingCaoEditor")
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtGui import QFontDatabase  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402


app = QApplication([])
for p in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\msyh.ttc"):
    if os.path.exists(p):
        QFontDatabase.addApplicationFont(p)

from infrastructure.theme_loader import ThemeLoader  # noqa: E402
from ui.welcome_widget import WelcomeWidget  # noqa: E402


loader = ThemeLoader()
w = WelcomeWidget()

themes = ["dark_night", "eye_protect", "light_clean", "high_contrast"]
print("=" * 70)
print("欢迎页主题跟随验证")
print("=" * 70)

for name in themes:
    theme = loader.load_by_name(name)
    if theme is None:
        print("  %s: 主题加载失败" % name)
        continue
    c = theme.colors
    w.refresh_theme(theme)
    app.processEvents()

    own = w.styleSheet()
    content = getattr(w, "_content_widget", None)
    content_ss = content.styleSheet() if content is not None else ""
    header_ss = w.header.title_label.styleSheet()
    qa_btn = None
    for b in w.quick_actions.findChildren(type(w.quick_actions)):
        pass
    # 取一个快捷操作按钮
    btn_ss = ""
    try:
        from PyQt5.QtWidgets import QPushButton
        for b in w.quick_actions.findChildren(QPushButton):
            if b.objectName() == "quick_action_button":
                btn_ss = b.styleSheet()
                break
    except Exception:
        pass
    tip_ss = w.tips_panel.tip_label.styleSheet()

    def has(ss, color):
        return color.lower() in ss.lower()

    print()
    print("  【%s】window_bg=%s  panel_bg=%s  success=%s"
          % (name, c.window_bg, c.panel_bg, c.success))
    print("    自身背景用 window_bg      : %s" % has(own, c.window_bg))
    print("    content 用 window_bg     : %s" % has(content_ss, c.window_bg))
    print("    头部标题用 success        : %s" % has(header_ss, c.success))
    print("    快捷按钮用 panel_fg/panel_bg: %s"
          % (has(btn_ss, c.panel_fg) or has(btn_ss, c.menu_bg)))
    print("    技巧卡片用 panel_bg       : %s" % has(tip_ss, c.panel_bg))
    # 关键：绝不能出现暗色主题的 #1e1e1e（浅色主题下）
    print("    残留暗色 #1e1e1e         : %s"
          % (has(own + content_ss + tip_ss, "#1e1e1e")))
    print("    残留暗色 #2d2d2d         : %s"
          % (has(own + content_ss + tip_ss + btn_ss, "#2d2d2d")))

print()
print("=" * 70)
print("完成")
print("=" * 70)
