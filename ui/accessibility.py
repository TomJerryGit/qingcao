# -*- coding: utf-8 -*-
"""无障碍支持（v2.17）：可访问名称 / 界面字体缩放 / 键盘焦点环

设计原则：
- 不破坏主题 QSS：焦点环通过追加片段实现（边框使用 palette(highlight)）；
- 字体缩放只作用于普通 QWidget，跳过 Scintilla 编辑器（有独立字号设置）；
- 所有操作可重复调用（幂等）。
"""
from PyQt5.QtWidgets import QDockWidget, QWidget


def focus_ring_qss() -> str:
    """键盘焦点可见性 QSS（追加到主题 QSS 末尾）"""
    return """
QLineEdit:focus, QPushButton:focus, QToolButton:focus,
QComboBox:focus, QTreeWidget:focus, QTableWidget:focus,
QTextEdit:focus, QListView:focus, QTabBar:focus {
    border: 2px solid palette(highlight);
}
QMenu::item:selected {
    outline: 2px solid palette(highlight);
}
"""


def apply_accessible_names(root) -> int:
    """为缺少名称的控件补 accessibleName（v2.17）"""
    if root is None:
        return 0
    count = 0
    try:
        widgets = [root] + list(root.findChildren(QWidget))
    except Exception:
        widgets = [root]
    for w in widgets:
        try:
            if w.accessibleName():
                continue
            name = ""
            if isinstance(w, QDockWidget):
                name = w.windowTitle()
            if not name:
                text = getattr(w, "text", None)
                if callable(text):
                    name = str(text() or "").strip()
            if not name:
                tip = getattr(w, "toolTip", None)
                if callable(tip):
                    name = str(tip() or "").strip()
            if not name:
                name = w.objectName() or type(w).__name__
            if name:
                w.setAccessibleName(name[:120])
                count += 1
        except Exception:
            continue
    return count


def apply_font_scale(root, factor: float) -> int:
    """界面字体缩放（0.8~2.0），跳过 Scintilla 编辑器。

    两阶段：先采集所有控件的基准字号，再统一应用，
    避免父控件先缩放导致子控件继承字号被误当基准（v2.17 修复）。
    """
    try:
        factor = float(factor)
    except Exception:
        return 0
    factor = max(0.8, min(2.0, factor))
    if root is None:
        return 0
    try:
        widgets = [root] + list(root.findChildren(QWidget))
    except Exception:
        widgets = [root]

    pairs = []
    for w in widgets:
        try:
            if type(w).__name__.startswith("Qsci"):
                continue
            font = w.font()
            base = getattr(w, "_qc_base_pt", None)
            if base is None:
                base = font.pointSizeF() if font.pointSizeF() > 0 else 9.0
                w._qc_base_pt = base
            pairs.append((w, float(base)))
        except Exception:
            continue

    count = 0
    for w, base in pairs:
        try:
            font = w.font()
            new_pt = max(6.0, round(base * factor, 1))
            if abs(font.pointSizeF() - new_pt) < 0.05:
                continue
            font.setPointSizeF(new_pt)
            w.setFont(font)
            count += 1
        except Exception:
            continue
    return count
