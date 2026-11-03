# -*- coding: utf-8 -*-
"""v2.19 P1-2：i18n 首批（语言菜单 / 菜单 / 欢迎页）"""

import io
import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_tr_and_tr_menu(monkeypatch):
    monkeypatch.setenv("QINGCAO_LANG", "en_US")
    from core.i18n_json import clear_cache, current_language, tr, tr_menu

    clear_cache()
    assert current_language() == "en_US"
    assert tr("保存") == "Save"
    assert tr("不存在的键") == "不存在的键"
    assert tr_menu("📄 新建文件") == "📄 New File"
    assert tr_menu("文件(&F)") == "File(&F)"


def test_zh_default(monkeypatch):
    monkeypatch.setenv("QINGCAO_LANG", "zh_CN")
    from core.i18n_json import clear_cache, tr, tr_menu

    clear_cache()
    assert tr("保存") == "保存"
    assert tr_menu("文件(&F)") == "文件(&F)"


def test_menu_and_welcome_english(qapp, monkeypatch):
    from PyQt5.QtWidgets import QAction, QLabel, QMessageBox

    monkeypatch.setenv("QINGCAO_LANG", "en_US")
    from core.i18n_json import clear_cache

    clear_cache()
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    from ui.main_window import MainWindow

    win = MainWindow()
    try:
        top = [a.text() for a in win.menuBar().actions() if a.menu()]
        assert "File(&F)" in top, top
        assert "Settings(&O)" in top, top
        assert win._ui_language_menu is not None
        texts = [a.text() for a in win.findChildren(QAction)]
        assert any("Save" in t for t in texts), texts[:20]
        labels = [w.text() for w in win.findChildren(QLabel)]
        assert any("QingCao Editor" in t for t in labels), labels[:20]
    finally:
        try:
            win.session.save = lambda *a, **k: None
        except Exception:
            pass
        win.close()


def test_dictionary_exists():
    path = os.path.join(ROOT, "locale", "en_US", "strings.json")
    assert os.path.isfile(path)
    data = io.open(path, encoding="utf-8").read()
    assert '"保存"' in data
