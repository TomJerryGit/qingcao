# -*- coding: utf-8 -*-
"""P8 回归测试：快捷键冲突与语义修复

本文件针对 task-3 第 1 步（P8），覆盖：

1. **核心防线** —— 遍历主窗口所有 QAction，断言非空快捷键**唯一**。
   P8-1 的根因就是 Alt+C 同时绑在"视图 → 列模式"菜单项和工具栏
   按钮两个 QAction 上，Qt 判定 ambiguous shortcut overload，
   按 Alt+C **两个都不触发**。这条断言让同类回归无法再悄悄发生。
2. P8-2 —— F5 = 运行当前文件（不再绑定"插入日期时间"），
   "插入日期时间"改绑 Ctrl+Alt+D。
3. P8-3 —— "粘贴为纯文本"存在、绑定 Ctrl+Alt+Shift+V，
   且不与 Vim 模式（Ctrl+Shift+V）/ 被 AltGr 吞掉的 Ctrl+Alt+V 冲突。
4. P8-1 —— 列模式在菜单与工具栏里是**同一个** QAction 实例。
5. P8-5 —— `_add_action()` 的运行时重复检测会 logging.warning
   而**不抛异常**（不能因为一个冲突打断启动）。
6. P8-4 —— 文档（tips / help_browser）与实际快捷键一致。
"""
import datetime
import logging
import os
import re

import pytest
from PyQt5.QtWidgets import QAction, QToolBar


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ============================================================
# 工具
# ============================================================
def iter_action_shortcuts(window):
    """遍历窗口下所有 QAction，返回 [(快捷键字符串, QAction), ...]。

    只包含**非空**快捷键。这是"无重复快捷键"断言的唯一数据来源。
    """
    pairs = []
    for action in window.findChildren(QAction):
        try:
            seq = action.shortcut()
        except Exception:
            continue
        if seq is None or seq.isEmpty():
            continue
        key = seq.toString()
        if not key:
            continue
        pairs.append((key, action))
    return pairs


def actions_with_shortcut(window, key):
    return [act for k, act in iter_action_shortcuts(window) if k == key]


def actions_with_text(window, needle):
    return [a for a in window.findChildren(QAction) if needle in a.text()]


def shortcut_of(action):
    return action.shortcut().toString()


# ============================================================
# fixture
# ============================================================
@pytest.fixture
def window(qapp):
    import ui.main_window as mw

    win = mw.MainWindow()
    try:
        yield win
    finally:
        try:
            win.close()
        except Exception:
            pass


# ============================================================
# 1. 核心防线：快捷键唯一
# ============================================================
class TestNoDuplicateShortcuts:
    def test_no_duplicate_non_empty_shortcuts(self, window):
        """任何非空快捷键只能绑定到一个 QAction。"""
        seen = {}
        duplicates = []
        for key, action in iter_action_shortcuts(window):
            previous = seen.get(key)
            if previous is not None and previous is not action:
                duplicates.append(
                    (key, previous.text(), action.text())
                )
            else:
                seen[key] = action

        assert not duplicates, (
            "存在重复快捷键（Qt 会报 ambiguous shortcut 并导致按键失效）: "
            + "; ".join(
                "{}: 「{}」 vs 「{}」".format(k, a, b)
                for k, a, b in duplicates
            )
        )

    def test_scan_is_not_vacuous(self, window):
        """防止断言因"扫不到任何快捷键"而假通过。"""
        pairs = iter_action_shortcuts(window)
        assert len(pairs) >= 30, (
            "只扫描到 %d 个快捷键，说明 findChildren(QAction) 失效或"
            "菜单未构建，断言会假通过" % len(pairs)
        )

    def test_expected_shortcuts_present(self, window):
        """抽查：修复后的关键快捷键确实都绑上了。"""
        keys = {k for k, _ in iter_action_shortcuts(window)}
        for expected in (
            "Ctrl+N", "Ctrl+S", "Ctrl+F", "Ctrl+Shift+P",
            "Alt+C", "F5", "F12",
            "Ctrl+Alt+D", "Ctrl+Alt+Shift+V", "Ctrl+Shift+V",
        ):
            assert expected in keys, "缺少快捷键 %s（现有: %s）" % (
                expected, sorted(keys)
            )

    def test_shortcut_registry_covers_menu_actions(self, window):
        """P8-5: 关键动作必须经过 _register_action_shortcut 登记。"""
        registry = getattr(window, "_shortcut_owners", {})
        for key in (
            "Ctrl+N", "Ctrl+S", "Alt+C", "F5", "F12",
            "Ctrl+Alt+D", "Ctrl+Alt+Shift+V", "Ctrl+Shift+V", "Ctrl+V",
        ):
            assert key in registry, (
                "%s 未登记到 _shortcut_owners，重复检测覆盖不到它" % key
            )


# ============================================================
# 2. P8-1 列模式：菜单与工具栏共用同一个 QAction
# ============================================================
class TestColumnModeShortcut:
    def test_alt_c_bound_exactly_once(self, window):
        acts = actions_with_shortcut(window, "Alt+C")
        assert len(acts) == 1, (
            "Alt+C 绑定了 %d 个 QAction: %s —— 这会触发 Qt 的 "
            "ambiguous shortcut overload，按键将完全无响应"
            % (len(acts), [a.text() for a in acts])
        )
        assert acts[0] is window.column_mode_action

    def test_column_action_shared_by_menu_and_toolbar(self, window):
        """同一个 QAction 实例同时出现在视图菜单和主工具栏。"""
        action = window.column_mode_action
        assert action in window.view_menu.actions(), (
            "列模式 QAction 不在视图菜单里"
        )

        toolbar = window.findChild(QToolBar, "MainToolBar")
        assert toolbar is not None, "找不到主工具栏"
        assert action in toolbar.actions(), (
            "列模式 QAction 不在主工具栏里（P8-1 要求共用同一个实例）"
        )


# ============================================================
# 3. P8-2 F5 语义
# ============================================================
class TestF5Semantics:
    def test_f5_is_run_current_file(self, window):
        acts = actions_with_shortcut(window, "F5")
        assert len(acts) == 1, (
            "F5 应且只应绑定 1 个动作，实际: %s" % [a.text() for a in acts]
        )
        text = acts[0].text()
        assert "运行" in text, "F5 应绑定「运行当前文件」，实际是 %r" % text
        assert "日期" not in text and "时间" not in text, (
            "F5 不得再绑定「插入日期时间」（实际 %r）" % text
        )

    def test_insert_datetime_moved_to_ctrl_alt_d(self, window):
        acts = actions_with_text(window, "插入日期时间")
        assert acts, "「插入日期时间」菜单项必须仍然存在"
        keys = {shortcut_of(a) for a in acts if not a.shortcut().isEmpty()}
        assert keys == {"Ctrl+Alt+D"}, (
            "「插入日期时间」应绑定 Ctrl+Alt+D，实际 %s" % sorted(keys)
        )

    def test_f5_not_owned_by_datetime_action(self, window):
        """直接对着"插入日期时间"断言，防止有人只改了另一处。"""
        for act in actions_with_text(window, "插入日期时间"):
            assert shortcut_of(act) != "F5"


# ============================================================
# 4. P8-3 粘贴为纯文本
# ============================================================
class TestPastePlain:
    def test_paste_plain_exists(self, window):
        acts = actions_with_text(window, "粘贴为纯文本")
        assert acts, (
            "「粘贴为纯文本」必须存在于菜单中（P8-3：它曾被 Vim 模式的"
            "Ctrl+Shift+V 挤掉，功能完全丢失）"
        )

    def test_paste_plain_shortcut(self, window):
        acts = actions_with_text(window, "粘贴为纯文本")
        keys = {shortcut_of(a) for a in acts if not a.shortcut().isEmpty()}
        assert keys == {"Ctrl+Alt+Shift+V"}, (
            "「粘贴为纯文本」应绑定 Ctrl+Alt+Shift+V，实际 %s" % sorted(keys)
        )

    def test_paste_plain_does_not_conflict_with_vim(self, window):
        acts = actions_with_text(window, "粘贴为纯文本")
        plain_key = shortcut_of(acts[0])

        vim = getattr(window, "vim_mode_action", None)
        assert vim is not None, "Vim 模式动作不存在"
        vim_key = shortcut_of(vim)

        assert plain_key != vim_key, (
            "「粘贴为纯文本」(%s) 与 Vim 模式 (%s) 冲突" % (plain_key, vim_key)
        )
        assert vim_key == "Ctrl+Shift+V"
        assert plain_key != "Ctrl+Alt+V", (
            "Ctrl+Alt+V 在 Windows 上被 AltGr 吞掉，不能再用"
        )

    def test_clipboard_binding_is_idempotent(self, window):
        """回归：同一快捷键被两个动作占用时必然被扫描出来。"""
        conflicts = [
            (k, a.text())
            for k, a in iter_action_shortcuts(window)
            if k == "Ctrl+Alt+Shift+V"
        ]
        assert len(conflicts) == 1, conflicts


# ============================================================
# 5. P8-5 运行时重复检测
# ============================================================
class TestDuplicateDetection:
    def test_add_action_warns_on_duplicate(self, window, caplog):
        caplog.set_level(logging.WARNING)

        action = window._add_action(
            window.tools_menu, "测试重复绑定动作", "Ctrl+N", lambda: None
        )

        assert action is not None, "_add_action 不应因冲突而失败"
        assert "快捷键冲突" in caplog.text, (
            "重复绑定必须写 logging.warning，实际日志: %r" % caplog.text
        )
        assert "Ctrl+N" in caplog.text

    def test_add_action_does_not_raise(self, window):
        """冲突时不得抛异常打断启动。"""
        try:
            window._add_action(
                window.tools_menu, "再一个冲突动作", "Ctrl+S", lambda: None
            )
        except Exception as e:  # pragma: no cover - 失败时给出清晰信息
            pytest.fail("重复绑定抛出了异常: %r" % (e,))

    def test_duplicate_does_not_steal_first_owner(self, window):
        """冲突时保留**首个**绑定（后者的快捷键失效但登记表不被覆盖）。"""
        original = window._shortcut_owners.get("Ctrl+F")
        assert original is not None

        window._add_action(
            window.tools_menu, "冲突的查找动作", "Ctrl+F", lambda: None
        )
        assert window._shortcut_owners.get("Ctrl+F") is original


# ============================================================
# 6. P8-4 文档一致性
# ============================================================
class TestDocumentationConsistency:
    def test_tips_do_not_teach_f5_datetime(self):
        from ui import tips

        text = "\n".join(tips.TIPS)
        assert "F5 在光标处插入" not in text, (
            "每日技巧仍在教 F5 = 插入日期时间"
        )
        assert "Ctrl+Alt+D" in text, "每日技巧应提到新的日期时间快捷键"

    def test_tips_column_mode_still_alt_c(self):
        """列模式快捷键没变（Alt+C），文档必须保持一致。"""
        from ui import tips

        text = "\n".join(tips.TIPS)
        assert "Alt+C 进入列模式" in text

    def test_help_browser_documents_new_shortcuts(self):
        from ui.help_browser import HELP_TOPICS

        text = "\n".join(HELP_TOPICS.values())
        assert "Alt+C" in text, "帮助里必须仍然说明列模式 = Alt+C"
        assert "Ctrl+Alt+Shift+V" in text, "帮助里缺少「粘贴为纯文本」"
        assert "Ctrl+Alt+D" in text, "帮助里缺少「插入日期时间」"
        assert re.search(r"\|\s*F12\s*\|", text), "帮助里缺少 F12 = 转到定义"

    def test_help_browser_does_not_claim_f5_datetime(self):
        from ui.help_browser import HELP_TOPICS

        text = "\n".join(HELP_TOPICS.values())
        assert not re.search(r"\|\s*F5\s*\|\s*插入日期时间", text), (
            "帮助里仍把 F5 写成插入日期时间"
        )


# ============================================================
# 7. P7/P8 「插入日期时间」真正读取 Preferences
# ============================================================
class TestInsertDatetimeWiring:
    """菜单入口必须走到唯一读取 date_format/time_format 的实现。

    背景：`ui/mixins/edit_ops_mixin.py:139` 另有一份
    `_insert_datetime`，把格式硬编码为 "%Y-%m-%d %H:%M:%S"。
    编辑菜单原先调用的是它 → Preferences 的 date_format /
    time_format 对用户完全无效（"假开关"）。
    """

    def test_menu_path_goes_through_proxy(self, window, monkeypatch):
        calls = []

        class FakeProxy:
            def insert_datetime(self):
                calls.append(True)

        monkeypatch.setattr(window.tabs, "current_proxy", lambda: FakeProxy())
        window._insert_datetime()

        assert calls == [True], (
            "编辑菜单的「插入日期时间」没有走 EditorProxy.insert_datetime，"
            "date_format / time_format 的接线对用户无效"
        )

    def test_no_editor_is_reported(self, window, monkeypatch):
        monkeypatch.setattr(window.tabs, "current_proxy", lambda: None)
        window._insert_datetime()   # 不得抛异常

    def test_proxy_insert_datetime_honors_preferences(self, qapp, monkeypatch):
        """运行时验证：改掉 Preferences 里的格式，插入的文本随之变化。

        硬编码实现无法通过这一条（它永远输出 %Y-%m-%d %H:%M:%S）。
        """
        from PyQt5.Qsci import QsciScintilla

        import app.preferences as prefs_mod
        from core.document import Document
        from core.editor import EditorProxy

        class FakePrefs:
            def get(self, key, default=None):
                values = {"date_format": "%Y!%m!%d", "time_format": "%H"}
                return values.get(key, default)

        monkeypatch.setattr(
            prefs_mod, "get_preferences", lambda: FakePrefs()
        )

        sc = QsciScintilla()
        proxy = EditorProxy(sc, Document())
        proxy.insert_datetime()

        inserted = sc.text()
        expected_date = datetime.datetime.now().strftime("%Y!%m!%d")
        assert inserted.startswith(expected_date), (
            "插入的日期时间没有遵循 Preferences.date_format：%r" % inserted
        )
        assert "!" in inserted, (
            "仍在使用硬编码格式（date_format 未生效）：%r" % inserted
        )

    def test_proxy_insert_datetime_defaults_without_prefs(
        self, qapp, monkeypatch
    ):
        """Preferences 不可用时回退到历史默认格式，且不抛异常。"""
        from PyQt5.Qsci import QsciScintilla

        import app.preferences as prefs_mod
        from core.document import Document
        from core.editor import EditorProxy

        def _boom():
            raise RuntimeError("preferences unavailable")

        monkeypatch.setattr(prefs_mod, "get_preferences", _boom)

        sc = QsciScintilla()
        proxy = EditorProxy(sc, Document())
        proxy.insert_datetime()

        assert sc.text() == datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
