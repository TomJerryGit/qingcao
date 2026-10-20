# -*- coding: utf-8 -*-
"""高 DPI 缩放 / 多显示器 验证

    python tools\\verify_hidpi_multimonitor.py
    python tools\\verify_hidpi_multimonitor.py --scale 1.5      # 单跑某缩放
    python tools\\verify_hidpi_multimonitor.py --geometry       # 只跑几何恢复

## 环境限制（必须先说明，避免把"没测到"当"没问题"）

本机只有**一台显示器**（物理 1920x1080，系统缩放 125%），且 Windows 的
系统级缩放改动需要注销/重启才生效。因此：

* **高 DPI**：用 Qt 官方的 `QT_SCALE_FACTOR` 环境变量模拟 1.0 / 1.25 /
  1.5 / 2.0 四档。这会真实改变 Qt 的 `devicePixelRatio`、字体度量与
  布局计算 —— 等价于用户在不同缩放档下运行；
* **多显示器**：无法接第二块屏。改为**直接验证多屏相关的代码路径**：
  会话保存的窗口坐标在"显示器被拔掉 / 换到小屏 / 尺寸超出屏幕"时
  是否被正确夹回可见区域。这几条正是多显示器下最容易出现的真实缺陷
  （窗口跑到看不见的地方、或大半个窗口在屏幕外）。

输出：每项 `[OK]/[FAIL]`；退出码 0 = 全通过。
"""
import json
import os
import subprocess
import sys


ROOT = r"D:\QingCaoEditor"
PASS, FAIL = [], []


def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %-56s %s" % ("OK " if cond else "FAIL", name, detail))


# ============================================================
# 单缩放档采集（子进程入口）
# ============================================================
def run_scale_probe(scale: str):
    os.environ["QT_SCALE_FACTOR"] = scale
    os.environ.pop("QT_QPA_PLATFORM", None)
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)

    from PyQt5.QtCore import Qt  # noqa: E402
    from PyQt5.QtWidgets import QApplication  # noqa: E402

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication([])

    from PyQt5.QtGui import QFontDatabase  # noqa: E402
    for p in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\msyh.ttc"):
        if os.path.exists(p):
            QFontDatabase.addApplicationFont(p)

    from ui.main_window import MainWindow  # noqa: E402

    win = MainWindow()
    win.resize(1100, 750)
    win.show()
    app.processEvents()
    win.apply_startup_theme()
    app.processEvents()

    screen = app.primaryScreen()
    dpr = screen.devicePixelRatio()
    sb = win.statusBar()

    # 抓图（物理像素）
    img = win.grab()
    shot = os.path.join(os.environ["TEMP"], "qc_desktop",
                        "hidpi_%s.png" % scale.replace(".", "_"))
    os.makedirs(os.path.dirname(shot), exist_ok=True)
    img.save(shot)

    # 状态栏标签是否在状态栏内、且非零宽
    labels = {}
    for name in ("cursor_label", "encoding_label", "eol_label",
                 "mode_label"):
        w = getattr(win, name, None)
        if w is not None:
            labels[name] = (w.width(), w.height(), w.text())

    # 文字裁切检查（按真实文本宽度，不按 sizeHint）
    #
    # 说明：不能拿 QToolButton.sizeHint() 判断 —— 图标按钮的 sizeHint 是
    # "图标+文字"的推荐尺寸，实际常被 setFixedSize 固定得更小（有意为之）。
    # 这里只检查**确实承载文字**的容器：
    #   * 标签栏：每个 tab 的矩形宽 >= 文本宽
    #   * 菜单栏：每个菜单项的矩形宽 >= 文本宽
    clipped_buttons = []
    fm = win.fontMetrics()
    try:
        from PyQt5.QtWidgets import QTabBar  # noqa: E402
        for bar in win.findChildren(QTabBar):
            if not bar.isVisible():
                continue
            for i in range(bar.count()):
                txt = bar.tabText(i)
                if not txt:
                    continue
                need = bar.fontMetrics().horizontalAdvance(txt) + 8
                got = bar.tabRect(i).width()
                if got < need:
                    clipped_buttons.append(("tab:" + txt, need, got))
    except Exception as e:
        clipped_buttons.append(("tab-scan-error", str(e), 0))
    try:
        mb = win.menuBar()
        for act in mb.actions():
            txt = act.text()
            if not txt:
                continue
            need = fm.horizontalAdvance(txt) + 10
            got = mb.actionGeometry(act).width()
            if got < need:
                clipped_buttons.append(("menu:" + txt, need, got))
    except Exception as e:
        clipped_buttons.append(("menu-scan-error", str(e), 0))

    # 菜单项是否在窗口内（宽度溢出会点不到）
    menu_overflow = []
    try:
        mh = win.menuBar()
        for act in mh.actions():
            geo = mh.actionGeometry(act)
            if geo.right() > mh.width() + 1 or geo.width() <= 0:
                menu_overflow.append((act.text(), geo.width(), geo.right(),
                                      mh.width()))
    except Exception as e:
        menu_overflow.append(("menu-bar-error", str(e), 0, 0))

    data = {
        "scale": scale,
        "dpr": dpr,
        "screen_logical": [screen.geometry().width(),
                           screen.geometry().height()],
        "screen_avail": [screen.availableGeometry().width(),
                         screen.availableGeometry().height()],
        "screen_physical": [screen.geometry().width() * dpr,
                            screen.geometry().height() * dpr],
        "window_logical": [win.width(), win.height()],
        "grab_px": [img.width(), img.height()],
        "default_panels": list(win._default_panels_for_screen()),
        "statusbar_h": sb.height() if sb else -1,
        "menubar_h": win.menuBar().height(),
        "toolbar_h": (win.findChildren(
            __import__("PyQt5.QtWidgets", fromlist=["QToolBar"])
            .QToolBar)[0].height()
            if win.findChildren(
                __import__("PyQt5.QtWidgets",
                           fromlist=["QToolBar"]).QToolBar) else -1),
        "font_pt_statusbar": win.cursor_label.font().pointSizeF(),
        "font_px_statusbar": win.cursor_label.fontMetrics().height(),
        "tab_h": (win.findChildren(
            __import__("PyQt5.QtWidgets", fromlist=["QTabBar"]).QTabBar)[0]
            .height()
            if win.findChildren(
                __import__("PyQt5.QtWidgets",
                           fromlist=["QTabBar"]).QTabBar) else -1),
        "labels": labels,
        "clipped_buttons": clipped_buttons,
        "menu_overflow": menu_overflow,
        "shot": shot,
        "statusbar_visible": bool(sb and sb.isVisible()),
        "statusbar_inside": bool(sb and sb.geometry().bottom()
                                 <= win.height() + 1),
    }
    print("PROBE=" + json.dumps(data, ensure_ascii=False))
    win.close()
    return 0


# ============================================================
# 几何恢复 / 多显示器代码路径
# ============================================================
def run_geometry_checks():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)

    from PyQt5.QtWidgets import QApplication  # noqa: E402

    app = QApplication.instance() or QApplication([])
    from PyQt5.QtGui import QFontDatabase  # noqa: E402
    for p in (r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\msyh.ttc"):
        if os.path.exists(p):
            QFontDatabase.addApplicationFont(p)

    from app.session import SessionManager  # noqa: E402
    from ui.main_window import MainWindow  # noqa: E402

    print("== 屏幕信息 ==")
    for s in app.screens():
        print("  screen %r geo=%s avail=%s dpr=%.2f"
              % (s.name(), s.geometry(), s.availableGeometry(),
                 s.devicePixelRatio()))
    primary = app.primaryScreen()
    avail = primary.availableGeometry()
    print("  primary available:", avail)

    win = MainWindow()
    sess = SessionManager()
    print()
    print("== 窗口几何恢复（模拟显示器变化）==")

    def restore(geo):
        """调真实恢复逻辑，返回最终 window geometry"""
        win.setGeometry(0, 0, 400, 300)
        sess._restore_geometry(win, geo)
        app.processEvents()
        return win.geometry()

    # 用「相对屏幕」的尺寸构造用例 —— offscreen 平台屏幕只有 800x600，
    # 若写死 900x600，窗口本就应该被缩到屏幕内（那是正确行为）。
    inner_w = max(200, avail.width() - 200)
    inner_h = max(150, avail.height() - 150)

    # 1) 完全在屏幕内 → 必须原样
    g = restore({"x": avail.left() + 10, "y": avail.top() + 10,
                 "w": inner_w, "h": inner_h})
    ok("G1 屏幕内坐标保持原样",
       (g.x(), g.y(), g.width(), g.height())
       == (avail.left() + 10, avail.top() + 10, inner_w, inner_h),
       "geo=%s avail=%s" % (g, avail))

    # 2) 坐标为"第二块显示器"（主屏右侧，已拔掉）→ 必须可见
    g = restore({"x": avail.right() + 1500, "y": avail.top() + 120,
                 "w": inner_w, "h": inner_h})
    ok("G2 已拔掉的右侧显示器坐标被夹回可见区（不消失）",
       avail.intersects(g), "geo=%s avail=%s" % (g, avail))

    # 3) 坐标为"左侧显示器"（负坐标）→ 必须可见
    g = restore({"x": avail.left() - 1600, "y": avail.top() + 120,
                 "w": inner_w, "h": inner_h})
    ok("G3 负坐标（左侧显示器已拔）被夹回可见区",
       avail.intersects(g), "geo=%s" % (g,))

    # 4) 窗口尺寸超出当前屏幕（大屏换小屏）→ 必须能完整显示
    g = restore({"x": avail.left() + 20, "y": avail.top() + 20,
                 "w": avail.width() + 1000, "h": avail.height() + 800})
    ok("G4 超大窗口（大屏→小屏）被缩到屏幕内",
       avail.contains(g), "geo=%s avail=%s" % (g, avail))

    # 5) 坐标在屏幕右下角边缘（大部分窗口在屏幕外）
    g = restore({"x": avail.right() - 40, "y": avail.bottom() - 40,
                 "w": inner_w, "h": inner_h})
    ok("G5 贴右下角的窗口被拉回可见区",
       avail.contains(g), "geo=%s avail=%s" % (g, avail))

    # 6) 最大化标志 → 应最大化
    win.setGeometry(0, 0, 400, 300)
    sess._restore_geometry(win, {"x": 50, "y": 50, "w": 400, "h": 300,
                                 "maximized": True})
    app.processEvents()
    ok("G6 maximized 标志生效", win.isMaximized(),
       "isMaximized=%r" % win.isMaximized())

    # 7) 屏幕选择：远离所有屏幕的坐标 → 主屏
    scr = sess._pick_screen_for_geometry(avail.right() + 5000, 5000,
                                        inner_w, inner_h)
    ok("G7 远离所有屏幕的坐标 → 选主屏",
       scr is not None and scr is primary, str(scr))

    # 8) 屏幕选择：屏幕内坐标 → 同一块屏
    scr = sess._pick_screen_for_geometry(avail.left() + 10,
                                        avail.top() + 10,
                                        inner_w, inner_h)
    ok("G8 屏幕内坐标 → 选中该屏幕",
       scr is not None and scr is primary, str(scr))

    print()
    print("== 多显示器相关静态检查 ==")
    import io as _io
    src = _io.open(os.path.join(ROOT, "app", "session.py"),
                   encoding="utf-8").read()
    ok("G9 几何恢复使用 availableGeometry（避开任务栏）",
       "availableGeometry" in src, "")
    ok("G10 几何恢复考虑多屏（screenAt + screens 遍历）",
       ("screenAt(" in src) and ("app.screens()" in src), "")
    ok("G11 窗口尺寸会被夹到屏幕内",
       "min(w, avail.width())" in src and "min(h, avail.height())" in src,
       "")
    ok("G12 位置按 right-w / bottom-h 夹取（非 right-100 近似）",
       "avail.right() - w + 1" in src
       and "avail.bottom() - h + 1" in src, "")

    main_src = _io.open(os.path.join(ROOT, "main.py"),
                        encoding="utf-8").read()
    i_attr = main_src.find("AA_EnableHighDpiScaling")
    i_app = main_src.find("app = QApplication(")
    ok("G13 AA_EnableHighDpiScaling 在 QApplication 创建之前",
       i_attr > 0 and i_app > 0 and i_attr < i_app,
       "attr@%d app@%d" % (i_attr, i_app))
    ok("G14 启用了 AA_UseHighDpiPixmaps",
       "AA_UseHighDpiPixmaps" in main_src, "")

    win.close()

    return 0


# ============================================================
# 主流程
# ============================================================
def run_scaling_matrix():
    print("=" * 96)
    print("高 DPI 缩放矩阵（QT_SCALE_FACTOR 模拟；本机物理 1920x1080 @125%）")
    print("=" * 96)
    scales = ["1", "1.25", "1.5", "2"]
    base = None
    results = []
    for sc in scales:
        env = os.environ.copy()
        env.pop("QT_QPA_PLATFORM", None)
        env["QT_SCALE_FACTOR"] = sc
        env["PYTHONIOENCODING"] = "utf-8"
        cp = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--scale", sc],
            cwd=ROOT, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace")
        line = ""
        for ln in (cp.stdout or "").splitlines():
            if ln.startswith("PROBE="):
                line = ln[len("PROBE="):]
        if not line:
            ok("S%s 采集成功" % sc, False,
               (cp.stdout or "")[-200:] + (cp.stderr or "")[-200:])
            continue
        d = json.loads(line)
        results.append(d)
        print()
        print("  --- scale=%s  dpr=%.2f  window=%s  grab=%s  "
              "statusbar_h=%d menubar_h=%d toolbar_h=%d"
              % (sc, d["dpr"], d["window_logical"], d["grab_px"],
                 d["statusbar_h"], d["menubar_h"], d["toolbar_h"]))
        print("      状态栏标签: %s"
              % {k: v[2] for k, v in d["labels"].items()})
        ok("S%s 抓图物理尺寸 = 逻辑尺寸 x dpr" % sc,
           abs(d["grab_px"][0] - round(d["window_logical"][0] * d["dpr"])) <= 2
           and abs(d["grab_px"][1]
                   - round(d["window_logical"][1] * d["dpr"])) <= 2,
           "grab=%s logical=%s dpr=%.3f"
           % (d["grab_px"], d["window_logical"], d["dpr"]))
        ok("S%s 状态栏可见且在窗口内" % sc,
           d["statusbar_visible"] and d["statusbar_inside"], "")
        ok("S%s 状态栏标签非零宽" % sc,
           all(v[0] > 0 for v in d["labels"].values()),
           str({k: v[0] for k, v in d["labels"].items()}))
        ok("S%s 工具栏按钮无裁切" % sc, not d["clipped_buttons"],
           str(d["clipped_buttons"][:3]))
        ok("S%s 菜单项未溢出窗口" % sc, not d["menu_overflow"],
           str(d["menu_overflow"][:3]))
        # 高缩放 ≈ 小屏：逻辑可用区域不足时应只开目录树，
        # 否则编辑器会被 4 个面板挤到只剩 2~3 行（真实桌面 200% 实测）
        dp = d["default_panels"]
        # 用**可用区域**判断（要扣掉任务栏；产品逻辑也是用
        # availableGeometry，用全屏几何会在 1.5x 这种边界档误判）
        small = (d["screen_avail"][0] < 1280
                 or d["screen_avail"][1] < 720)
        ok("S%s 默认面板按逻辑分辨率自适应（%s）"
           % (sc, "仅目录树" if small else "完整 4 个"),
           (dp == ["dir_tree"]) if small else (len(dp) == 4),
           "逻辑可用=%s 面板=%s" % (d["screen_avail"], dp))
    if results:
        base = results[0]
        print()
        print("  --- 高 DPI 语义正确性（逻辑尺寸不变 / 物理像素放大）---")
        base_sb = max(1, base["statusbar_h"])
        base_menu = max(1, base["menubar_h"])
        for d in results[1:]:
            exp = float(d["scale"])
            # 1) 逻辑尺寸应**基本不变**（Qt 高 DPI 的核心语义）
            ok("S%s 状态栏逻辑高度保持（%d vs 基准 %d）"
               % (d["scale"], d["statusbar_h"], base_sb),
               abs(d["statusbar_h"] - base_sb) <= 3, "")
            ok("S%s 菜单栏逻辑高度保持（%d vs 基准 %d）"
               % (d["scale"], d["menubar_h"], base_menu),
               abs(d["menubar_h"] - base_menu) <= 3, "")
            # 2) 物理高度 = 逻辑 × dpr，随缩放增大
            sb_phys = d["statusbar_h"] * d["dpr"]
            ok("S%s 状态栏物理高度随缩放增大（%.0fpx）"
               % (d["scale"], sb_phys),
               sb_phys >= base_sb * 0.9 * exp,
               "logical=%d dpr=%.2f" % (d["statusbar_h"], d["dpr"]))
            # 3) 抓图物理尺寸 == 逻辑 × dpr（布局没被裁/被截断）
            ok("S%s 抓图 = 逻辑×dpr（无裁切）" % d["scale"],
               abs(d["grab_px"][0]
                   - round(d["window_logical"][0] * d["dpr"])) <= 2
               and abs(d["grab_px"][1]
                       - round(d["window_logical"][1] * d["dpr"])) <= 2,
               "grab=%s logical=%s dpr=%.2f"
               % (d["grab_px"], d["window_logical"], d["dpr"]))
            # 4) 字体逻辑字号不变（不能在高 DPI 下变小）
            ok("S%s 字体逻辑字号保持（%.1fpt）"
               % (d["scale"], d["font_pt_statusbar"]),
               abs(d["font_pt_statusbar"]
                   - base["font_pt_statusbar"]) <= 1.5, "")
            # 5) 文字无裁切
            ok("S%s 标签/菜单文字无裁切" % d["scale"],
               not d["clipped_buttons"],
               str(d["clipped_buttons"][:3]))


def main():
    os.environ["PYTHONIOENCODING"] = "utf-8"
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if "--scale" in sys.argv:
        return run_scale_probe(sys.argv[sys.argv.index("--scale") + 1])
    if "--geometry" in sys.argv:
        return run_geometry_checks()

    run_scaling_matrix()
    print()
    print("=" * 96)
    print("多显示器相关代码路径（本机单屏，验证「显示器变化」时的恢复逻辑）")
    print("=" * 96)
    run_geometry_checks()

    print()
    print("=" * 96)
    print("结果：通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    print("=" * 96)
    if FAIL:
        print("失败项：")
        for n in FAIL:
            print("  - " + n)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
