# -*- coding: utf-8 -*-
"""回归测试：插件命令注册不能依赖 ActionManager 的真值

## 为什么单独建这个文件

本轮实测发现一个**首次运行 100% 复现**的隐蔽缺陷：

    `app/actions.py::ActionManager` 定义了 `__len__`（返回已注册动作数），
    因此**空的 ActionManager 是 falsy**。而插件正是在**激活时**注册命令 ——
    那一刻 `act_mgr` 里几乎还是空的，于是原来的

        if hasattr(self.win, 'act_mgr') and self.win.act_mgr:

    直接短路，**13 个插件命令一个都没注册**：

      * 命令面板的「插件」分类永远是空的；
      * 「⭐ 特色功能」聚合入口只能显示"未注册命令"。

    第二次启动（动作已被上一次填过）反而正常 —— 这类"只在首次运行出现"
    的缺陷靠人工点测极难发现，必须用测试锁住。

同时锁住同族风险：`QMenuBar.insertMenu()` 返回的是 **QAction**（不是
QMenu），以及 `_add_action(slot=None)` 会 `connect(None)` 抛 TypeError。
"""
import os
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


# ============================================================
# 1. ActionManager 空实例为假 —— 这是缺陷的**根因**，必须显式锁住
# ============================================================
def test_empty_action_manager_is_falsy(qapp):
    """锁住根因：空 ActionManager 为 falsy（所以不能用真值判定）

    这条断言不是"期望行为"，而是**记录一个会咬人的事实**。
    如果哪天 `__len__` 被去掉，本测试会失败并提醒：
    "真值判定现在安全了，可以简化 plugins.py 的写法"。
    """
    from app.actions import ActionManager
    mgr = ActionManager()
    assert len(mgr) == 0
    assert not mgr, (
        "预期空 ActionManager 为 falsy（因为它定义了 __len__）。"
        "若此断言失败，说明 __len__ 已移除，"
        "可考虑简化 app/plugins.py 里的 is-not-None 判定。"
    )


def test_action_manager_is_truthy_once_populated(qapp):
    """有动作后为真 —— 解释为什么缺陷只在**首次运行**出现"""
    from PyQt5.QtWidgets import QAction

    from app.actions import ActionManager

    mgr = ActionManager()
    mgr.register("__probe__", QAction("探针"))
    assert len(mgr) == 1
    assert bool(mgr) is True


# ============================================================
# 2. PluginAPI.register_command 必须在空 act_mgr 上也能注册成功
# ============================================================
def test_register_command_works_on_empty_action_manager(qapp):
    """核心回归：**全新的空 ActionManager** 上注册插件命令必须成功

    这正是首次运行的场景（此前会静默丢失全部命令）。
    """
    from PyQt5.QtWidgets import QAction, QMainWindow

    from app.actions import ActionManager
    from app.plugins import PluginAPI

    win = QMainWindow()
    win.act_mgr = ActionManager()
    assert not win.act_mgr, "前置条件：act_mgr 应为空（首次运行场景）"

    api = PluginAPI(win, permissions=["dialog"], plugin_name="probe_plugin")
    api.register_command("do_thing", lambda: None, description="做点事")

    keys = list(getattr(win.act_mgr, 'actions', {}) or {})
    assert "plugin.probe_plugin.do_thing" in keys, (
        "空 ActionManager 上注册插件命令失败 —— 又回到了"
        "「首次运行命令面板为空」的缺陷。已注册键：%r" % (keys,)
    )
    action = win.act_mgr.actions["plugin.probe_plugin.do_thing"]
    assert isinstance(action, QAction)
    # 命令面板按 plugin.* 前缀取，必须能搜到
    assert action.text() == "做点事"


def test_registered_command_is_reachable_by_classification(qapp):
    """命令面板的分类逻辑（`startswith("plugin.")`）能取到刚注册的命令"""
    from PyQt5.QtWidgets import QMainWindow

    from app.actions import ActionManager
    from app.plugins import PluginAPI

    win = QMainWindow()
    win.act_mgr = ActionManager()
    api = PluginAPI(win, permissions=[], plugin_name="p2")
    for name in ("a", "b", "c"):
        api.register_command(name, (lambda n: (lambda: None))(name))

    plugin_names = [k for k in win.act_mgr.actions
                    if str(k).startswith("plugin.")]
    assert len(plugin_names) == 3, plugin_names


# ============================================================
# 3. 同族风险：insertMenu 返回 QAction；slot=None 不得抛异常
# ============================================================
def test_menubar_insert_menu_returns_action_not_menu(qapp):
    """记录 Qt 事实：`insertMenu()` 返回 QAction（混淆会崩整个窗口）"""
    from PyQt5.QtWidgets import QAction, QMainWindow, QMenu

    win = QMainWindow()
    mb = win.menuBar()
    first = mb.addMenu("A")
    menu = QMenu("B", win)
    ret = mb.insertMenu(first.menuAction(), menu)
    assert isinstance(ret, QAction), type(ret).__name__
    assert not isinstance(ret, QMenu)


def test_add_action_accepts_none_slot_as_disabled_placeholder(qapp):
    """`_add_action(slot=None)` 应产出禁用项，而不是 connect(None) 崩溃

    实测：占位菜单项传 None 时，`action.triggered.connect(None)` 抛
    `TypeError: argument 1 has unexpected type 'NoneType'`，
    一个占位项就能让整个 MainWindow 构造失败。
    """
    from ui.main_window import MainWindow

    win = MainWindow()
    menu = win.menuBar().addMenu("测试")
    act = win._add_action(menu, "占位", None, None)
    assert act is not None
    assert act.isEnabled() is False, "slot=None 的占位项应被禁用"
