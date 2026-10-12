# -*- coding: utf-8 -*-
"""
交互审计：插件 × 生命周期（热重载）
=================================

覆盖的交互：
    1. 热重载 × 菜单注册  —— 新菜单项被加进"待删除的子菜单"里，
                             事件循环处理 DeferredDelete 后菜单项消失
                             （不是重复叠加，而是彻底丢失）
    2. 热重载 × 事件订阅  —— PluginAPI.unsubscribe 的 signal_map 缺少
                             subscribe 支持的一半事件名，取消订阅静默失败

生产调用链（静态定位）：
    infrastructure/plugin_loader.py:1339-1381 _on_directory_changed
      -> 1168-1204 reload_plugin
        -> 1086-1148 unload_plugin   （-> api.cleanup()）
        -> _parse_plugin / _load_plugin / _activate_plugin
    app/plugins.py:1516-1565 cleanup()（对子菜单只做 deleteLater）
    app/plugins.py:592-602  add_menu 里"复用已存在的子菜单"
    app/plugins.py:772-836  subscribe / unsubscribe

运行方式：
    python -m pytest tests/test_audit_interaction_plugin.py -v
"""

import pytest


# ============================================================
# 1. 热重载 × 菜单注册
# ============================================================
class TestHotReloadMenus:

    @staticmethod
    def _host():
        from PyQt5.QtWidgets import QMainWindow
        return QMainWindow()

    @staticmethod
    def _count_leaf(win, top="工具", sub="我的插件", leaf="执行"):
        for act in win.menuBar().actions():
            if act.text().startswith(top) and act.menu():
                for s in act.menu().actions():
                    if s.text() == sub and s.menu():
                        return len([
                            a for a in s.menu().actions()
                            if a.text() == leaf
                        ])
        return 0

    @pytest.mark.audit_expected_fail
    def test_menu_item_survives_one_hot_reload(self, qapp):
        """卸载 -> 重新激活（等价于一次热重载）后，
        插件菜单项必须仍然存在且不重复。
        """
        from PyQt5.QtCore import QEvent

        from app.plugins import PluginAPI

        win = self._host()

        # ---- 第一次加载 ----
        api1 = PluginAPI(win, permissions=[], plugin_name="demo")
        api1.add_menu("工具/我的插件/执行", lambda: None)
        assert self._count_leaf(win) == 1, "前置条件：首次注册应有 1 项"

        # ---- 热重载：unload_plugin -> api.cleanup() ----
        api1.cleanup()

        # ---- 重新激活 ----
        api2 = PluginAPI(win, permissions=[], plugin_name="demo")
        api2.add_menu("工具/我的插件/执行", lambda: None)

        # 让 deleteLater 真正生效
        qapp.sendPostedEvents(None, QEvent.DeferredDelete)

        count = self._count_leaf(win)
        assert count == 1, (
            "热重载后插件菜单项数量错误（期望 1）。\n"
            "  原因：cleanup() 只对子菜单 deleteLater()（延迟删除），"
            "而 add_menu 的 '复用已存在子菜单' 分支按文本找到的仍是那个"
            "待删除的旧子菜单，新动作被加到即将被销毁的容器里，"
            "事件循环处理 DeferredDelete 后整项消失。\n"
            f"  实测数量={count}"
        )

    @pytest.mark.audit_expected_fail
    def test_toolbar_action_survives_one_hot_reload(self, qapp):
        """工具栏按钮同理：QAction 的 parent 是主窗口而不是 QToolBar，
        cleanup 里的 action.parent().removeAction(action) 无法把按钮
        从工具栏移除，只能依赖 deleteLater。"""
        from PyQt5.QtCore import QEvent
        from PyQt5.QtWidgets import QToolBar

        from app.plugins import PluginAPI

        win = self._host()
        win.addToolBar(QToolBar("t", win))     # 保证已存在工具栏

        api1 = PluginAPI(win, permissions=[], plugin_name="demo")
        api1.add_toolbar_action("按钮", lambda: None)

        def count_buttons():
            n = 0
            for tb in win.findChildren(QToolBar):
                n += len([a for a in tb.actions() if a.text() == "按钮"])
            return n

        assert count_buttons() == 1

        api1.cleanup()
        api2 = PluginAPI(win, permissions=[], plugin_name="demo")
        api2.add_toolbar_action("按钮", lambda: None)
        qapp.sendPostedEvents(None, QEvent.DeferredDelete)

        assert count_buttons() == 1, (
            f"热重载后工具栏按钮数量={count_buttons()}（期望 1）"
        )

    @pytest.mark.audit_expected_fail
    def test_shortcut_action_survives_one_hot_reload(self, qapp):
        from PyQt5.QtCore import QEvent

        from app.plugins import PluginAPI

        win = self._host()

        api1 = PluginAPI(win, permissions=[], plugin_name="demo")
        api1.register_shortcut("Ctrl+Alt+M", lambda: None)
        assert len(win.actions()) >= 1

        api1.cleanup()
        api2 = PluginAPI(win, permissions=[], plugin_name="demo")
        api2.register_shortcut("Ctrl+Alt+M", lambda: None)
        qapp.sendPostedEvents(None, QEvent.DeferredDelete)

        # 不允许出现两个同快捷键动作（重复注册）
        same = [a for a in win.actions()
                if a.shortcut().toString() == "Ctrl+Alt+M"]
        assert len(same) == 1, (
            f"热重载后存在 {len(same)} 个相同快捷键的动作（期望 1）"
        )


# ============================================================
# 2. 热重载 × 事件订阅
# ============================================================
class TestPluginEventSubscription:

    @pytest.mark.audit_expected_fail
    def test_unsubscribe_supports_every_subscribable_event(self, qapp):
        """app/plugins.py:817-836 的 unsubscribe 只覆盖 6 个事件，
        而 subscribe（772-815）支持 15 个。对 tab_changed /
        theme_changed / macro_started 等调用 unsubscribe 会静默失败。
        """
        from PyQt5.QtWidgets import QMainWindow

        from app.plugins import PluginAPI

        win = QMainWindow()
        api = PluginAPI(win, permissions=[], plugin_name="demo")

        events = [
            "file_opened", "file_saved", "file_closed", "file_modified",
            "editor_changed", "cursor_moved", "selection_changed",
            "tab_changed", "tab_added", "tab_removed",
            "project_opened", "project_closed",
            "macro_started", "macro_stopped", "theme_changed",
        ]

        def cb(*_a, **_k):
            pass

        for ev in events:
            api.subscribe(ev, cb)

        for ev in events:
            api.unsubscribe(ev, cb)

        left = [c for (_s, c) in api._event_connections]
        assert left == [], (
            "以下事件的 unsubscribe 静默失败（订阅仍然挂着）："
            f"{len(left)}/{len(events)} 条连接未解除。"
            " unsubscribe 的 signal_map 缺少 tab_*、theme_changed、"
            "macro_*、file_modified、project_* 等键。"
        )

    @pytest.mark.audit_expected_fail
    def test_cleanup_releases_event_connections(self, qapp):
        """cleanup() 必须能解除全部订阅（这条应当通过，
        用于证明缺陷只在 unsubscribe 而不在 cleanup）。"""
        from PyQt5.QtWidgets import QMainWindow

        from app.plugins import PluginAPI

        win = QMainWindow()
        api = PluginAPI(win, permissions=[], plugin_name="demo")

        def cb(*_a, **_k):
            pass

        for ev in ["file_opened", "tab_changed", "theme_changed"]:
            api.subscribe(ev, cb)

        api.cleanup()
        assert api._event_connections == []


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-v"]))
