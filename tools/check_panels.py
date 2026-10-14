# -*- coding: utf-8 -*-
"""逐个启用视图菜单里的面板，验证每个都能真正创建并显示

目的：区分"功能缺失"与"默认不显示"。全新启动时面板是**延迟创建**的，
只有被显式打开才会构造。本工具逐个打开并记录结果。
"""
import io
import os
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

OUT = []


def log(s=""):
    OUT.append(str(s))
    try:
        print(s, flush=True)
    except Exception:
        pass


def main():
    from PyQt5.QtGui import QFontDatabase
    from PyQt5.QtWidgets import QApplication, QDockWidget

    app = QApplication.instance() or QApplication([])
    for p in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\msyh.ttc"):
        if os.path.exists(p):
            QFontDatabase.addApplicationFont(p)

    from ui.main_window import MainWindow
    w = MainWindow()
    end = time.time() + 30
    while time.time() < end:
        app.processEvents()
        pm = getattr(w, "plugin_manager", None)
        if pm and len(getattr(getattr(pm, "loader", None), "specs", {}) or {}) >= 10:
            break
        time.sleep(0.05)
    for _ in range(40):
        app.processEvents()
        time.sleep(0.02)

    log("=" * 74)
    log("面板可用性验证（逐个启用）")
    log("=" * 74)

    log()
    log("启动时（全新状态）:")
    docks = w.findChildren(QDockWidget)
    log("  停靠面板数量: %d -> %s"
        % (len(docks), [d.windowTitle() for d in docks]))
    log("  工具栏可见: %s" % getattr(w, "toolbar", None) is not None)
    log("  状态栏可见: %s" % (getattr(w, "status_bar", None) is not None))

    # 找到"视图 -> 面板"子菜单
    panels_menu = None
    for act in w.menuBar().actions():
        if "视图" in act.text() and act.menu():
            for sub in act.menu().actions():
                if sub.text().replace("&", "").strip() == "📊 面板" and sub.menu():
                    panels_menu = sub.menu()
                    break
    if panels_menu is None:
        for act in w.menuBar().actions():
            if "视图" in act.text() and act.menu():
                for sub in act.menu().actions():
                    if "面板" in sub.text() and sub.menu():
                        panels_menu = sub.menu()
                        break
    if panels_menu is None:
        log("  未找到「面板」子菜单")
        return 1

    log()
    log("=" * 74)
    log("逐个开启「视图 -> 面板」里的每一项")
    log("=" * 74)
    results = []
    for act in panels_menu.actions():
        if act.isSeparator():
            continue
        name = act.text().replace("&", "").strip()
        if not name:
            continue
        try:
            if act.isCheckable():
                act.setChecked(True)
            else:
                act.trigger()
        except Exception as e:
            log("  %-16s 触发异常: %s" % (name, e))
            results.append((name, "触发异常"))
            continue
        for _ in range(30):
            app.processEvents()
            time.sleep(0.02)
        # 找出对应的 dock
        found = []
        for d in w.findChildren(QDockWidget):
            if d.isVisible():
                found.append(d.windowTitle())
        ok = bool(found)
        results.append((name, "OK 已显示" if ok else "未创建"))
        log("  %-16s %s   （当前可见面板: %s）"
            % (name, "OK 已显示" if ok else "未创建", found))

    log()
    log("=" * 74)
    log("汇总")
    log("=" * 74)
    ok_cnt = sum(1 for _, s in results if s.startswith("OK"))
    log("  共 %d 项，成功 %d 项" % (len(results), ok_cnt))
    for name, s in results:
        log("    %-16s %s" % (name, s))

    log()
    log("最终可见面板: %s"
        % [d.windowTitle() for d in w.findChildren(QDockWidget)
           if d.isVisible()])

    with io.open(os.path.join(ROOT, "panel_check.txt"), "w",
                 encoding="utf-8") as f:
        f.write("\n".join(OUT))
    print("[panels] 已写出 panel_check.txt", flush=True)
    w.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        log("验证失败:")
        log(traceback.format_exc())
        with io.open(os.path.join(ROOT, "panel_check.txt"), "w",
                     encoding="utf-8") as f:
            f.write("\n".join(OUT))
        sys.exit(1)
