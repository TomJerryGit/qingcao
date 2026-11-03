# -*- coding: utf-8 -*-
"""v2.19 长尾 2：状态栏/消息框/对话框自动翻译 + 欢迎页"""

import io
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _install(qapp, monkeypatch):
    monkeypatch.setenv("QINGCAO_LANG", "en_US")
    from core.i18n_json import clear_cache

    clear_cache()
    from ui.i18n_widgets import install_ui_translators

    return install_ui_translators(qapp)


def test_translate_text_and_install(qapp, monkeypatch):
    n = _install(qapp, monkeypatch)
    assert n in (0, 1)
    from ui.i18n_widgets import translate_text

    assert translate_text("保存成功") == "Saved"
    assert translate_text("最近文件") == "Recent Files"
    assert translate_text("不存在的消息") == "不存在的消息"


def test_status_bar_message(qapp, monkeypatch):
    _install(qapp, monkeypatch)
    from PyQt5.QtWidgets import QStatusBar

    bar = QStatusBar()
    bar.showMessage("已保存")
    assert bar.currentMessage() == "Saved"
    bar.showMessage("就绪")
    assert bar.currentMessage() == "Ready"
    bar.close()


def test_message_box_args(qapp, monkeypatch):
    from PyQt5.QtWidgets import QMessageBox

    import ui.i18n_widgets as iw

    monkeypatch.setenv("QINGCAO_LANG", "en_US")
    from core.i18n_json import clear_cache

    clear_cache()
    captured = []
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: captured.append(a))
    )
    iw._installed = False  # 重新安装以包裹当前（测试用）实现
    iw.install_ui_translators(qapp)
    QMessageBox.information(None, "保存成功", "已保存")
    assert captured, "未捕获消息框调用"
    assert captured[0][1] == "Saved"
    assert captured[0][2] == "Saved"


def test_dialog_auto_translate(qapp, monkeypatch):
    _install(qapp, monkeypatch)
    from PyQt5.QtWidgets import QDialog, QLabel, QVBoxLayout

    from ui.i18n_widgets import translate_widgets

    dlg = QDialog()
    layout = QVBoxLayout(dlg)
    label = QLabel("最近文件", dlg)
    layout.addWidget(label)
    translate_widgets(dlg)  # 等价于 Show 过滤器内的处理
    assert label.text() == "Recent Files"
    dlg.close()


def test_welcome_page_strings(qapp, monkeypatch):
    from PyQt5.QtWidgets import QLabel, QMessageBox, QPushButton

    monkeypatch.setenv("QINGCAO_LANG", "en_US")
    from core.i18n_json import clear_cache

    clear_cache()
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    from ui.i18n_widgets import translate_widgets
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        translate_widgets(win)
        texts = [b.text() for b in win.findChildren(QPushButton)] + [
            l.text() for l in win.findChildren(QLabel)
        ]
        for expected in ("New File", "Open File", "Open Folder", "Quick Start"):
            assert any(expected in t for t in texts), (expected, texts[:10])
    finally:
        try:
            win.session.save = lambda *a, **k: None
        except Exception:
            pass
        win.close()


def test_dictionary_batch2():
    import json

    en = json.load(io.open(os.path.join(ROOT, "locale", "en_US", "strings.json"), encoding="utf-8"))
    for k in ("保存成功", "最近文件", "就绪", "安装", "主题市场"):
        assert k in en
