# -*- coding: utf-8 -*-
"""键盘焦点/Tab 顺序审计。"""

import argparse
import sys


def _is_interactive(w):
    from PyQt5.QtWidgets import (
        QAbstractButton,
        QComboBox,
        QLineEdit,
        QPlainTextEdit,
        QTextEdit,
    )

    return isinstance(w, (QAbstractButton, QComboBox, QLineEdit, QTextEdit, QPlainTextEdit))


def audit(window, max_steps=300):
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QAbstractButton, QMenuBar, QToolBar

    issues = []
    seen = set()
    cur = window.focusWidget() or window
    steps = 0
    while steps < max_steps:
        try:
            cur = cur.nextInFocusChain()
        except Exception:
            break
        steps += 1
        if cur is None or cur is window:
            break
        if id(cur) in seen:
            break
        seen.add(id(cur))
        try:
            if not cur.isVisible() or cur.focusPolicy() == Qt.NoFocus:
                continue
            parent = cur.parent()
            while parent is not None:
                if isinstance(parent, (QToolBar, QMenuBar)):
                    break
                parent = parent.parent()
            else:
                if _is_interactive(cur):
                    txt = (getattr(cur, "text", lambda: "")() or "").strip()
                    name = (cur.accessibleName() or "").strip()
                    if not txt and not name:
                        if not (cur.objectName() or "").startswith("qt_"):
                            issues.append(("no-name", cur.__class__.__name__, cur.objectName()))
        except Exception:
            pass
    for w in window.findChildren(QAbstractButton):
        try:
            if not w.isVisible():
                continue
            p = w.parent()
            in_bar = False
            while p is not None:
                if isinstance(p, (QToolBar, QMenuBar)):
                    in_bar = True
                    break
                p = p.parent()
            if in_bar:
                continue
            if w.focusPolicy() == Qt.NoFocus:
                if not (w.objectName() or "").startswith("qt_"):
                    issues.append(("no-focus", w.__class__.__name__, w.objectName()))
        except Exception:
            pass
    return issues


def main(argv=None):
    ap = argparse.ArgumentParser()
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
    for kind, cls, name in issues:
        print("[focus] %s %s (%s)" % (kind, name or "<unnamed>", cls))
    print("[focus] issues=%d" % len(issues))
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
