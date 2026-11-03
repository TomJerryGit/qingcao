# -*- coding: utf-8 -*-
"""键盘无障碍审计（v2.17）：快捷键覆盖 / 焦点控件 / 可访问名称

用法: python tools/audit_keyboard_a11y.py [--json OUT] [--strict]
"""

import argparse
import io
import json
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def audit_window(win):
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QAction, QWidget

    actions = []

    def _collect(menu, depth=0):
        out = []
        if menu is None or depth > 6:
            return out
        try:
            menu.show()
        except Exception:
            pass
        for a in menu.actions():
            if (a.text() or "").strip() or a.shortcut().toString():
                out.append(a)
            sub = a.menu()
            if sub is not None:
                out.extend(_collect(sub, depth + 1))
        try:
            menu.hide()
        except Exception:
            pass
        return out

    try:
        bar = win.menuBar()
        for m in bar.findChildren(type(bar.addMenu("_tmp"))):
            actions.extend(_collect(m))
        for m in bar.actions():
            if m.menu() is not None:
                actions.extend(_collect(m.menu()))
        if not actions:
            actions = list(bar.findChildren(QAction))
    except Exception:
        actions = []
    seen = set()
    uniq = []
    for a in actions:
        key = id(a)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(a)
    actions = uniq
    menu_actions = [a for a in actions if (a.text() or "").strip()]
    with_shortcut = [a for a in menu_actions if a.shortcut().toString()]
    without = [a.text() for a in menu_actions if not a.shortcut().toString()]
    focusable = []
    unnamed = []
    try:
        for w in [win] + list(win.findChildren(QWidget)):
            if w.focusPolicy() != Qt.NoFocus:
                focusable.append(type(w).__name__)
                if not w.accessibleName():
                    unnamed.append(type(w).__name__)
    except Exception:
        pass
    return {
        "menu_actions": len(menu_actions),
        "with_shortcut": len(with_shortcut),
        "shortcut_ratio": round(len(with_shortcut) / max(1, len(menu_actions)), 3),
        "without_shortcut": without[:30],
        "focusable_widgets": len(focusable),
        "unnamed_focusable": len(unnamed),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from ui.accessibility import apply_accessible_names
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        apply_accessible_names(win)
        report = audit_window(win)
    finally:
        try:
            sess = getattr(win, "session", None)
            if sess is not None and hasattr(sess, "save"):
                sess.save = lambda *a, **k: None
        except Exception:
            pass
        win.close()

    print(
        "[a11y] 菜单项 %d，有快捷键 %d（%.1f%%）"
        % (report["menu_actions"], report["with_shortcut"], report["shortcut_ratio"] * 100)
    )
    print(
        "[a11y] 可聚焦控件 %d，缺少可访问名称 %d"
        % (report["focusable_widgets"], report["unnamed_focusable"])
    )
    if report["without_shortcut"]:
        print("[a11y] 无快捷键菜单示例:", ", ".join(report["without_shortcut"][:10]))
    if args.json:
        io.open(args.json, "w", encoding="utf-8", newline="\n").write(
            json.dumps(report, ensure_ascii=False, indent=2)
        )
    ok = (
        report["menu_actions"] >= 10
        and report["shortcut_ratio"] >= 0.30
        and report["unnamed_focusable"] <= report["focusable_widgets"] * 0.5
    )
    print("[a11y]", "审计通过" if ok else "审计未达标")
    if args.strict and not ok:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
