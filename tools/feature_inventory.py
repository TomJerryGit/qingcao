# -*- coding: utf-8 -*-
"""功能清单：导出程序能提供的**全部**功能点

用途：核对"打包版是否全功能"。逐项列出：
  * 菜单栏所有菜单与条目（含插件注册的）
  * 工具栏动作
  * 停靠面板
  * 命令面板命令
  * 全局快捷键
  * 插件提供的 API 能力

与 `plugin_report.txt` 的区别：后者只导出"工具"菜单，本工具覆盖全部
位置（视图菜单里的 Markdown 预览/TODO/字数统计也能看到）。

用法：
    python tools/feature_inventory.py
输出：
    feature_inventory.txt
"""
import io
import os
import sys


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
    from PyQt5.QtGui import QFontDatabase, QKeySequence
    from PyQt5.QtWidgets import (
        QAction,
        QApplication,
        QDockWidget,
        QToolBar,
    )

    app = QApplication.instance() or QApplication([])
    for p in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\msyh.ttc"):
        if os.path.exists(p):
            QFontDatabase.addApplicationFont(p)

    from ui.main_window import MainWindow
    w = MainWindow()
    import time
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
    log("青草编辑器 功能清单")
    log("=" * 74)

    # ---- 1. 菜单栏全部条目 ----
    log()
    log("=" * 74)
    log("1) 菜单栏完整结构")
    log("=" * 74)
    total_menu_items = 0

    def walk(menu, depth, counter):
        for act in menu.actions():
            counter[0] += 1
            nm = act.text().replace("&", "")
            sc = act.shortcut().toString()
            if act.isSeparator():
                continue
            tag = ""
            if act.isCheckable():
                tag = "  [可勾选]"
            if sc:
                tag += "  (%s)" % sc
            log("  " * (depth + 1) + "- " + nm + tag)
            if act.menu():
                walk(act.menu(), depth + 1, counter)

    for act in w.menuBar().actions():
        nm = act.text().replace("&", "")
        if act.isSeparator():
            continue
        log()
        log("[菜单] %s" % nm)
        if act.menu():
            c = [0]
            walk(act.menu(), 0, c)
            total_menu_items += c[0]
            log("        （本菜单 %d 项）" % c[0])
    log()
    log("菜单条目合计: %d" % total_menu_items)

    # ---- 2. 工具栏 ----
    log()
    log("=" * 74)
    log("2) 工具栏动作")
    log("=" * 74)
    for tb in w.findChildren(QToolBar):
        acts = [a.text().replace("&", "") for a in tb.actions()
                if not a.isSeparator() and a.text()]
        log("  [%s] %d 项: %s" % (tb.windowTitle(), len(acts), acts))

    # ---- 3. 停靠面板 ----
    log()
    log("=" * 74)
    log("3) 停靠面板")
    log("=" * 74)
    docks = w.findChildren(QDockWidget)
    log("  数量: %d" % len(docks))
    for d in docks:
        log("    - %s  (visible=%s)" % (d.windowTitle(), d.isVisible()))

    # ---- 4. 命令面板命令 ----
    log()
    log("=" * 74)
    log("4) 命令面板命令")
    log("=" * 74)
    pm = getattr(w, "plugin_manager", None)
    api = None
    specs = getattr(getattr(pm, "loader", None), "specs", None) or {}
    for name, sp in specs.items():
        inst = getattr(sp, "instance", None)
        if inst is not None and getattr(inst, "api", None) is not None:
            api = inst.api
            break
    if api is not None:
        try:
            cmds = api.list_commands()
            log("  数量: %d" % len(cmds))
            for c in sorted(cmds):
                log("    - %s" % c)
        except Exception as e:
            log("  读取命令失败: %s" % e)
    else:
        log("  无可用 API")

    # ---- 5. 快捷键 ----
    log()
    log("=" * 74)
    log("5) 全局快捷键（QAction 绑定）")
    log("=" * 74)
    seqs = {}
    for a in w.findChildren(QAction):
        s = a.shortcut().toString()
        if s:
            seqs.setdefault(s, []).append(a.text().replace("&", "") or "(无标题)")
    for s in sorted(seqs):
        names = seqs[s]
        dup = "  ⚠ 重复绑定" if len(names) > 1 else ""
        log("  %-18s -> %s%s" % (s, names, dup))
    log("  合计 %d 个快捷键" % len(seqs))

    # ---- 6. 插件能力 ----
    log()
    log("=" * 74)
    log("6) 插件能力")
    log("=" * 74)
    for name in sorted(specs):
        inst = getattr(specs[name], "instance", None)
        if inst is None:
            log("  %-18s 未激活" % name)
            continue
        ms = [m for m in dir(inst)
              if not m.startswith("_") and callable(getattr(inst, m, None))]
        log("  %-18s 公开方法 %d 个: %s" % (name, len(ms), ms[:10]))

    log()
    log("=" * 74)
    log("完成")
    log("=" * 74)

    with io.open(os.path.join(ROOT, "feature_inventory.txt"), "w",
                 encoding="utf-8") as f:
        f.write("\n".join(OUT))
    print("[inventory] 已写出 feature_inventory.txt", flush=True)
    w.close()
    return 0


if __name__ == "__main__":
    import time  # noqa: E402
    try:
        sys.exit(main())
    except Exception:
        import traceback
        log("清单生成失败:")
        log(traceback.format_exc())
        with io.open(os.path.join(ROOT, "feature_inventory.txt"), "w",
                     encoding="utf-8") as f:
            f.write("\n".join(OUT))
        sys.exit(1)
