# -*- coding: utf-8 -*-
"""GUI 冒烟：插件面板主题切换截图对比

用法: python tools/smoke_plugin_theme.py
输出: docs/smoke_plugin_theme_<theme>.png
"""
import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.03)


def find_plugin_dock(win):
    from PyQt5.QtWidgets import QDockWidget
    for d in win.findChildren(QDockWidget):
        title = d.windowTitle() or ""
        name = d.objectName() or ""
        widget_cls = type(d.widget()).__name__ if d.widget() else ""
        if "插件" in title or "plugin" in name.lower() or "Plugin" in widget_cls:
            return d
    return None


def pick_themes():
    from infrastructure.theme_loader import ThemeLoader
    loader = ThemeLoader()
    try:
        names = [n for n, _ in loader.list_themes()]
    except Exception:
        names = []
    if not names:
        try:
            names = list(loader.get_theme_names())
        except Exception:
            names = []
    light = next((n for n in names if "light" in n.lower()), names[0] if names else "")
    dark = next((n for n in names if "dark" in n.lower()), names[-1] if names else "")
    return light, dark, names


def main():
    from PyQt5.QtWidgets import QApplication

    from ui.main_window import MainWindow
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.resize(1280, 800)
    win.show()
    pump(app, 4.0)  # 等延迟插件加载

    dock = find_plugin_dock(win)
    if dock is not None:
        dock.show()
        dock.raise_()
        pump(app, 1.0)
        print("[smoke] 插件面板:", dock.windowTitle())
    else:
        print("[smoke] 未找到插件面板 dock")

    light, dark, names = pick_themes()
    eye = next((n for n in names if "eye" in n.lower()), None)
    print("[smoke] 主题列表:", names[:10], "... light=%r dark=%r" % (light, dark))
    out = []
    targets = [("light", light), ("dark", dark)]
    if eye:
        targets.append(("eye", eye))
    for label, name in targets:
        if not name:
            continue
        try:
            win._apply_theme_by_name(name)
        except Exception as e:
            print("[smoke] 应用主题失败:", name, e)
            continue
        pump(app, 1.5)
        path = os.path.join(ROOT, "docs", "smoke_plugin_theme_%s.png" % label)
        pix = win.grab()
        pix.save(path)
        if dock is not None:
            panel = dock.widget()
            if panel is not None:
                panel.grab().save(os.path.join(
                    ROOT, "docs", "smoke_plugin_panel_%s.png" % label))
        out.append((label, name, path, pix.width(), pix.height()))
        print("[smoke] 已截图:", path, "%dx%d" % (pix.width(), pix.height()))

    # 简单像素差异（证明主题确实变化）
    if len(out) >= 2:
        try:
            from PyQt5.QtGui import QImage
            img1 = QImage(out[0][2])
            img2 = QImage(out[1][2])
            pts = [(img1.width() // 2, img1.height() // 3),
                   (img1.width() // 4, img1.height() // 2),
                   (img1.width() // 2, img1.height() - 30)]
            diffs = []
            for x, y in pts:
                c1 = img1.pixelColor(x, y)
                c2 = img2.pixelColor(x, y)
                diffs.append(abs(c1.red() - c2.red()) + abs(c1.green() - c2.green())
                             + abs(c1.blue() - c2.blue()))
            print("[smoke] 采样点 RGB 差异:", diffs, "平均:", sum(diffs) / len(diffs))
        except Exception as e:
            print("[smoke] 像素对比失败:", e)

    win.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())