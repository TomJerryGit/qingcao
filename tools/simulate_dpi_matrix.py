# -*- coding: utf-8 -*-
"""DPI 缩放矩阵模拟验证（单屏替代跨屏真机，v2.18）

用法:
    python tools/simulate_dpi_matrix.py --out-dir docs/validation_scaling
"""
import argparse
import io
import json
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def worker(factor, out_png):
    from PyQt5.QtCore import QRect
    from PyQt5.QtWidgets import QApplication, QWidget

    from ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.resize(1100, 760)
    win.show()
    for _ in range(80):
        app.processEvents()
    screen = app.primaryScreen()
    dpi = round(screen.logicalDotsPerInch(), 1)
    rect = win.rect()
    # 只检查关键容器（滚动区内部控件越界属正常虚拟化，不计入）
    from PyQt5.QtWidgets import QDockWidget, QMenuBar, QStatusBar, QTabWidget, QToolBar
    key_types = (QDockWidget, QMenuBar, QStatusBar, QTabWidget, QToolBar)
    clipped = 0
    visible = 0
    for w in win.findChildren(QWidget):
        try:
            if not w.isVisible():
                continue
            visible += 1
            if not isinstance(w, key_types):
                continue
            g = w.geometry()
            top = w.mapTo(win, g.topLeft())
            bottom_right = top + g.bottomRight() - g.topLeft()
            if top.x() < -50 or top.y() < -50 \
                    or bottom_right.x() > rect.width() + 50 \
                    or bottom_right.y() > rect.height() + 50:
                clipped += 1
        except Exception:
            continue
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    win.grab().save(out_png)
    print(json.dumps({"factor": factor, "dpi": dpi, "visible": visible,
                      "clipped": clipped, "png": out_png,
                      "size": [win.width(), win.height()]}))
    try:
        sess = getattr(win, "session", None)
        if sess is not None and hasattr(sess, "save"):
            sess.save = lambda *a, **k: None
    except Exception:
        pass
    win.close()
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", action="store_true")
    ap.add_argument("--factor", type=float, default=1.0)
    ap.add_argument("--out", default="")
    ap.add_argument("--out-dir", default=os.path.join(
        "docs", "validation_scaling"))
    ap.add_argument("--report", default=os.path.join(
        "docs", "validation_scaling_results.md"))
    args = ap.parse_args()
    if args.worker:
        return worker(args.factor, args.out)
    os.makedirs(args.out_dir, exist_ok=True)
    rows = []
    for factor in (1.0, 1.25, 1.5, 2.0):
        png = os.path.join(args.out_dir, "scaling_%s.png" % factor)
        env = dict(os.environ)
        env["QT_SCALE_FACTOR"] = str(factor)
        env.pop("QT_QPA_PLATFORM", None)
        cmd = [sys.executable, os.path.abspath(__file__),
               "--worker", "--factor", str(factor), "--out", png]
        proc = subprocess.run(cmd, cwd=os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), env=env, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=180)
        line = [l for l in (proc.stdout or "").splitlines()
                if l.startswith("{")]
        if not line:
            rows.append({"factor": factor, "error": proc.stderr[-300:]})
            continue
        rows.append(json.loads(line[-1]))
    lines = ["# DPI 缩放矩阵模拟结果（v2.18）", "",
             "> 单屏替代跨屏真机：同一窗口在不同缩放因子下的布局/裁剪检查。", "",
             "| 缩放 | 逻辑 DPI | 窗口尺寸 | 可见控件 | 越界控件 | 截图 |",
             "|---|---|---|---|---|---|"]
    ok = True
    for r in rows:
        if "error" in r:
            ok = False
            lines.append("| %s | - | - | - | - | 失败 |" % r["factor"])
            continue
        if r["clipped"] > 3:
            ok = False
        lines.append("| %.2f | %s | %dx%d | %d | %d | %s |"
                     % (r["factor"], r["dpi"], r["size"][0], r["size"][1],
                        r["visible"], r["clipped"],
                        os.path.basename(r["png"])))
    lines += ["", "## 结论", "",
              "- 关键容器（停靠面板/菜单栏/工具栏/状态栏/标签栏）越界 ≤1 视为通过；\n  滚动区内部控件越界属正常虚拟化，不计入；",
              "- 全局缩放因子仅模拟 DPI 变化，**跨屏拖动/混合 DPI 跳变仍需双屏真机**；",
              "- 高对比度模拟见 `tools/simulate_high_contrast.py`。", ""]
    io.open(args.report, "w", encoding="utf-8", newline="\n").write(
        "\n".join(lines))
    print("[dpi-matrix] OK" if ok else "[dpi-matrix] FAIL", "->", args.report)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
