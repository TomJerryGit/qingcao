# -*- coding: utf-8 -*-
"""v2.19 P2：插件未启用时隐藏「特色功能」占位子菜单"""

from PyQt5.QtWidgets import QAction, QMessageBox

from ui.main_window import MainWindow


PLACEHOLDER = "（该插件未注册命令，或未启用）"
TITLES = ("🤖 AI 助手（ai_assistant）", "🔀 Git（git_deep）")


def _make_window(qapp, monkeypatch, commands=None):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    if commands is not None:
        monkeypatch.setattr(
            MainWindow, "_plugin_commands", lambda self, name: commands.get(name, []), raising=True
        )
    return MainWindow()


def test_inactive_plugin_submenus_hidden(qapp, monkeypatch):
    win = _make_window(qapp, monkeypatch, commands={})
    try:
        menus = getattr(win, "_feature_plugin_menus", {})
        assert set(TITLES).issubset(menus), "应记录两个插件子菜单"
        for title in TITLES:
            assert menus[title].menuAction().isVisible() is False, title
        # 不再出现禁用占位项
        texts = []
        for menu in menus.values():
            texts.extend(a.text() for a in menu.actions())
        assert PLACEHOLDER not in texts
    finally:
        try:
            win.session.save = lambda *a, **k: None
        except Exception:
            pass
        win.close()


def test_refresh_shows_and_hides(qapp, monkeypatch):
    win = _make_window(qapp, monkeypatch, commands={})
    try:
        qa = QAction("示例命令", win)
        win._plugin_commands = lambda name: [("plugin.demo", qa)] if name == "ai_assistant" else []
        win.refresh_feature_menu()
        menus = win._feature_plugin_menus
        ai = menus[TITLES[0]]
        assert ai.menuAction().isVisible() is True
        assert [a.text() for a in ai.actions()] == ["示例命令"]
        assert menus[TITLES[1]].menuAction().isVisible() is False

        # 插件卸载/禁用后再次刷新 → 重新隐藏
        win._plugin_commands = lambda name: []
        win.refresh_feature_menu()
        for title in TITLES:
            assert menus[title].menuAction().isVisible() is False
    finally:
        try:
            win.session.save = lambda *a, **k: None
        except Exception:
            pass
        win.close()
