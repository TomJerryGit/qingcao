# -*- coding: utf-8 -*-
"""多主题 E2E 截图基线（v2.16 P3）

对 dark/light/eye/high_contrast 逐一切换主题，抓取主窗口与插件面板，
输出到 docs/theme_baseline/。用法:
    python tools/theme_e2e_screenshots.py [--out DIR]
"""
import argparse
import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def find_plugin_dock(win):
    from PyQt5.QtWidgets import QDockWidget
    for d in win.findChildren(QDockWidget):
        title = d.windowTitle() or ""
        cls = type(d.widget()).__name__ if d.widget() else ""
        if "插件" in title or "Plugin" in cls:
            return d
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "docs",
                                                  "theme_baseline"))
    ap.add_argument("--themes", default="dark_night,light_clean,"
                                        "eye_protect,high_contrast")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    from PyQt5.QtWidgets import QApplication

    from ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.resize(1100, 780)
    win.show()
    pump(app, 3.0)
    dock = find_plugin_dock(win)
    if dock is not None:
        dock.show()
        dock.raise_()
        pump(app, 0.6)

    written = []
    for name in [t.strip() for t in args.themes.split(",") if t.strip()]:
        try:
            win._apply_theme_by_name(name)
        except Exception as e:
            print("[theme-e2e] apply failed:", name, e)
            continue
        pump(app, 1.0)
        win_path = os.path.join(args.out, "window_%s.png" % name)
        win.grab().save(win_path)
        written.append(win_path)
        if dock is not None and dock.widget() is not None:
            panel_path = os.path.join(args.out, "panel_%s.png" % name)
            dock.widget().grab().save(panel_path)
            written.append(panel_path)
        print("[theme-e2e] captured:", name)
    win.close()
    print("[theme-e2e] files:", len(written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
