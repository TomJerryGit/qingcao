# -*- coding: utf-8 -*-
"""通用控件树翻译（i18n 长尾，v2.19 P1-2）

对已有窗口做**后处理翻译**，无需逐处改 setText：
QLabel / QAbstractButton / QGroupBox / QLineEdit(placeholder)；
支持尾部冒号、省略号、emoji 前缀与 (&X) 加速键。
"""

from PyQt5.QtWidgets import (
    QAbstractButton,
    QGroupBox,
    QLabel,
    QLineEdit,
    QWidget,
)

from core.i18n_json import current_language, tr, tr_menu


_SUFFIXES = ("：", ":", "...")


def tr_label(text: str) -> str:
    """标签翻译：中文冒号/省略号/emoji 前缀安全处理"""
    if not text:
        return text
    if current_language() == "zh_CN":
        return text
    for suffix in _SUFFIXES:
        if text.endswith(suffix):
            base = text[: -len(suffix)].rstrip()
            translated = tr(base)
            if translated != base:
                return translated + suffix
    return tr_menu(text)


def translate_widgets(root) -> int:
    """翻译 root 及其所有子孙控件的文本；返回修改数量"""
    if root is None or current_language() == "zh_CN":
        return 0
    count = 0
    widgets = [root]
    try:
        widgets += list(root.findChildren(QWidget))
    except Exception:
        pass
    for w in widgets:
        try:
            if isinstance(w, QGroupBox):
                old = w.title()
                new = tr_label(old)
                if new != old:
                    w.setTitle(new)
                    count += 1
            elif isinstance(w, (QAbstractButton, QLabel)):
                old = w.text()
                new = tr_label(old)
                if new != old:
                    w.setText(new)
                    count += 1
        except Exception:
            pass
        try:
            if isinstance(w, QLineEdit):
                old = w.placeholderText()
                new = tr_label(old)
                if new != old:
                    w.setPlaceholderText(new)
                    count += 1
        except Exception:
            pass
    return count
