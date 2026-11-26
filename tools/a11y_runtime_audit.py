# -*- coding: utf-8 -*-
"""运行时无障碍审计：可见按钮/输入缺少名称或提示。"""

import argparse
import sys


def audit(window):
    from PyQt5.QtWidgets import (
        QAbstractButton,
        QComboBox,
        QLineEdit,
    )

    issues = []
    for w in window.findChildren(QAbstractButton):
        try:
            if not w.isVisible():
                continue
            if (
                not (w.text() or "").strip()
                and not (w.accessibleName() or "").strip()
                and not (w.toolTip() or "").strip()
            ):
                issues.append(("button", w.objectName(), w.__class__.__name__))
        except Exception:
            pass
    for w in window.findChildren((QLineEdit, QComboBox)):
        try:
            if not w.isVisible():
                continue
            name = (w.accessibleName() or "").strip()
            tip = (w.toolTip() or "").strip()
            ph = (w.placeholderText() or "").strip() if hasattr(w, "placeholderText") else ""
            if not name and not tip and not ph:
                issues.append(("input", w.objectName(), w.__class__.__name__))
        except Exception:
            pass
    return issues


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    args = ap.parse_args(argv)
    from PyQt5.QtWidgets import QApplication

    sys.path.insert(0, ".")
    from ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.resize(1100, 780)
    win.show()
    for _ in range(20):
        app.processEvents()
    issues = audit(win)
    win.hide()
    for kind, name, cls in issues:
        print("[a11y] %s %s (%s)" % (kind, name or "<unnamed>", cls))
    print("[a11y] issues=%d" % len(issues))
    if args.json:
        import io
        import json

        io.open(args.json, "w", encoding="utf-8", newline="\n").write(
            json.dumps(issues, ensure_ascii=False, indent=2)
        )
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
