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
    if "\n" in text:
        head, rest = text.split("\n", 1)
        return tr_label(head) + "\n" + rest
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


_installed = False


def translate_text(text: str) -> str:
    """通用文本翻译（消息/状态栏）：先精确，再标签/菜单规则"""
    if not text or current_language() == "zh_CN":
        return text
    exact = tr(text)
    if exact != text:
        return exact
    return tr_label(text)


def _translate_msgbox(title: str, text: str):
    return translate_text(title), translate_text(text)


def install_ui_translators(app=None) -> int:
    """安装全局翻译钩子（v2.19 长尾：状态栏 / 消息框 / 对话框）。

    - QStatusBar.showMessage：动态状态消息翻译；
    - QMessageBox.information/warning/critical/question：标题与正文翻译；
    - QDialog Show 事件：首次显示时自动翻译整个控件树。
    """
    global _installed
    if current_language() == "zh_CN":
        return 0
    if _installed:
        return 0
    from PyQt5.QtCore import QEvent, QObject
    from PyQt5.QtWidgets import QDialog, QMessageBox, QStatusBar

    orig_show = QStatusBar.showMessage

    def _show(self, message, timeout=0):
        return orig_show(self, translate_text(message), timeout)

    QStatusBar.showMessage = _show

    for name in ("information", "warning", "critical", "question"):
        orig = getattr(QMessageBox, name)

        def make(orig_fn):
            def _box(parent, title, text, *args, **kwargs):
                # 仅翻译字符串参数（按钮参数保持原样）
                new_title, new_text = _translate_msgbox(title, text)
                return orig_fn(parent, new_title, new_text, *args, **kwargs)

            return _box

        setattr(QMessageBox, name, staticmethod(make(orig)))

    class _DialogTranslator(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Show:
                try:
                    if isinstance(obj, QDialog) and not getattr(obj, "_qc_i18n_done", False):
                        obj._qc_i18n_done = True
                        translate_widgets(obj)
                except Exception:
                    pass
            return False

    if app is None:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
    if app is not None:
        global _dialog_filter
        _dialog_filter = _DialogTranslator(app)
        app.installEventFilter(_dialog_filter)
    _installed = True
    return 1
