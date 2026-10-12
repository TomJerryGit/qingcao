# -*- coding: utf-8 -*-
"""
交互审计：撤销/重做（UndoManager）× 其他功能
==========================================

本文件是"功能交互与状态一致性"审计的一部分，覆盖：

    1. 撤销 × 命令合并   —— 合并路径绕过 redo 栈失效逻辑
    2. 撤销 × 命令组     —— GroupCmd 无时间窗合并，redo 栈残留
    3. 撤销 × Vim 模式   —— VimMode 调用被禁用的 QScintilla 内置撤销栈

每项断言都写明了"期望行为（正确实现应该满足的不变式）"，
因此在缺陷被修复前这些测试应当 **失败**。

断言不变式（核心）：
    INV-1  任何改变缓冲区内容的操作，都必须让 redo 栈失效。
    INV-2  undo / redo 的历史必须是"线性可逆"的：
           任意时刻的内容都必须能由 undo/redo 序列从初始状态到达。

运行方式：
    python -m pytest tests/test_audit_interaction_undo.py -v
"""

import pytest


# ============================================================
# 1. 撤销 × 命令合并：合并路径不清空 redo 栈
# ============================================================
class TestUndoRedoStackInvalidation:
    """UndoManager.record() 的合并分支必须让 redo 栈失效（INV-1）"""

    @pytest.mark.audit_expected_fail
    def test_pending_group_merge_keeps_stale_redo(self, qapp):
        """begin_group 的合并分支返回 True，绕过了 _do_record 里的
        redo_stack.clear()，导致 redo 栈残留过期命令。

        涉及：core/undo.py:242-271（record）
              core/undo.py:261-268（_try_merge 命中即 return）
              core/undo.py:276-277（只有 _do_record 才清 redo）
        """
        from core.commands import InsertCmd
        from core.undo import UndoManager

        mgr = UndoManager(merge_interval=100000)  # 放宽窗口使合并确定发生

        # 两条不可互相合并的命令
        mgr.record(InsertCmd(0, "AAA"))   # stack=[A]
        mgr.record(InsertCmd(0, "Z"))     # 0+3 != 0 -> 不合并，stack=[A, Z]

        assert len(mgr.undo_stack) == 2, "前置条件：应有两条独立命令"

        # 撤销 Z -> redo 栈非空
        assert mgr.undo() is True
        assert mgr.can_redo() is True, "前置条件：撤销后应可重做"

        # 新的编辑动作：走 _pending_group 合并分支
        mgr.begin_group(InsertCmd(0, "P"))
        mgr.record(InsertCmd(1, "Q"))     # 时间窗内 -> 合并，return True

        assert mgr.can_redo() is False, (
            "INV-1 违反：内容已改变（新命令 P/Q 被记录并合并进撤销栈），"
            "但 redo 栈仍残留旧命令 Z。"
            f" can_redo()={mgr.can_redo()}, "
            f"redo_stack={[c.describe() for c in mgr.redo_stack]}"
        )

    @pytest.mark.audit_expected_fail
    def test_group_cmd_merge_keeps_stale_redo(self, qapp):
        """GroupCmd.can_merge 对任何 GroupCmd 都返回 True（无时间窗），
        因此"多光标/列模式编辑"批次之间必然合并，而且合并路径
        不会清空 redo 栈 —— 这是生产代码可复现的路径。

        涉及：core/commands.py:619-629（GroupCmd.can_merge/merge_with）
              core/undo.py:261-268、359-377
              core/editor.py:695-711（多光标 -> GroupCmd -> record）
        """
        from core.commands import GroupCmd, InsertCmd
        from core.undo import UndoManager

        mgr = UndoManager()

        # 多光标编辑批次 1
        mgr.record(GroupCmd([InsertCmd(0, "AAA")]))   # stack=[G1]
        # 一次普通编辑（它会把 editor 侧 pending group 冲刷掉，
        # 也在这里提供一条非 GroupCmd 的栈顶之下内容）
        mgr.record(InsertCmd(0, "X"))                 # stack=[G1, X]

        assert mgr.undo() is True                     # stack=[G1], redo=[X]
        assert mgr.can_redo() is True

        # 多光标编辑批次 2 —— G1.can_merge(G2) 恒为 True
        mgr.record(GroupCmd([InsertCmd(0, "Y")]))

        assert mgr.can_redo() is False, (
            "INV-1 违反：新的多光标编辑已被合并进撤销栈，"
            "redo 栈却仍保留旧命令 X。"
            f" undo_stack={[c.describe() for c in mgr.undo_stack]}, "
            f"redo_stack={[c.describe() for c in mgr.redo_stack]}"
        )

    @pytest.mark.audit_expected_fail
    def test_editor_merge_after_undo_produces_unreachable_state(
            self, qapp, monkeypatch):
        """EditorProxy 级别复现（真实 QScintilla + SCN_MODIFIED 记录）。

        InsertCmd.can_merge 的时间窗是模块常量 core.commands.MERGE_INTERVAL_MS
        （硬编码 200ms，与 UndoManager.merge_interval 无关）。
        为了让它确定性发生，这里把该常量放大；逻辑缺陷本身与被放宽的
        时间窗无关 —— 只影响能否稳定复现。
        """
        import core.commands as commands

        monkeypatch.setattr(commands, "MERGE_INTERVAL_MS", 10 ** 9)

        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy

        sc = QsciScintilla()
        sc.setUtf8(True)
        proxy = EditorProxy(sc, Document())

        # ---- 1) 输入 "AAA" ----
        sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"AAA")
        # ---- 2) 在位置 0 插入 "X"（与栈顶 Insert(0,"AAA") 不相邻 -> 独立成条）----
        sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"X")
        assert sc.text() == "XAAA"
        assert len(proxy.undo_manager.undo_stack) == 2

        # ---- 3) 撤销 -> 回到 "AAA"，redo 栈 = [Insert(0,"X")] ----
        proxy.undo()
        assert sc.text() == "AAA"
        assert proxy.can_redo() is True

        # 记录此刻所有"历史可达状态"
        reachable = {sc.text()}

        # ---- 4) 在位置 3 插入 "BB"：与栈顶 Insert(0,"AAA") 相邻 -> 合并 ----
        sc.SendScintilla(sc.SCI_INSERTTEXT, 3, b"BB")
        assert sc.text() == "AAABB"

        assert proxy.can_redo() is False, (
            "INV-1 违反：编辑器内容已改变，redo 仍被激活。"
            f" redo_stack={[c.describe() for c in proxy.undo_manager.redo_stack]}"
        )

        # ---- 5) 若继续 redo，会得到一个"历史中从未出现过"的状态 ----
        if proxy.can_redo():
            proxy.redo()
            new_state = sc.text()
            assert new_state in reachable or new_state == "AAABB", (
                f"INV-2 违反：redo 产生了历史中不可达的状态 {new_state!r}"
            )

    @pytest.mark.audit_expected_fail
    def test_undo_stack_matches_text_after_mixed_operations(self, qapp):
        """撤销栈 × 实际内容一致性：逐条 undo 后文本必须等于期望。

        这是审计要求的"撤销后 sc.text() 是否等于期望"。
        """
        from PyQt5.Qsci import QsciScintilla

        from core.document import Document
        from core.editor import EditorProxy

        sc = QsciScintilla()
        sc.setUtf8(True)
        proxy = EditorProxy(sc, Document())

        sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"abc")     # state1 = "abc"
        sc.SendScintilla(sc.SCI_INSERTTEXT, 3, b"def")     # state2
        sc.SendScintilla(sc.SCI_DELETERANGE, 0, 1)         # state3

        expected = ["abcde", "abcdef", "abc"]   # 步骤快照（可能因合并而不同）

        states = []
        for _ in range(10):
            if not proxy.can_undo():
                break
            proxy.undo()
            states.append(sc.text())

        # 最终必须能回到空文档
        assert sc.text() == "", (
            f"撤销到底后文本应为空，实际 {sc.text()!r}；"
            f"中间状态={states}；期望快照={expected}"
        )


# ============================================================
# 2. 撤销 × Vim 模式
# ============================================================
class TestVimUndo:
    """VimMode 的 u / Ctrl+R 必须走自研 UndoManager"""

    @pytest.mark.audit_expected_fail
    def test_vim_u_uses_disabled_builtin_undo_stack(self, qapp):
        """VimMode 调用的是 QScintilla 内置 undo，而 EditorProxy
        在 _connect_signals 里执行了 SCI_SETUNDOCOLLECTION(0)，
        因此 Vim 的 u 是静默无效的。

        涉及：core/vim_mode.py:228-231（u -> self.editor.undo()）
              core/vim_mode.py:85-89（Ctrl+R -> self.editor.redo()）
              core/editor.py:344-346（SCI_SETUNDOCOLLECTION, 0）
              ui/editor_view.py:507-513（Vim 优先处理按键并吞掉）
        """
        from PyQt5.Qsci import QsciScintilla
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QKeyEvent

        from core.document import Document
        from core.editor import EditorProxy
        from core.vim_mode import VimMode, VimState

        sc = QsciScintilla()
        sc.setUtf8(True)
        sc.setText("hello world\n")
        sc.setCursorPosition(0, 0)

        # 关键：先建代理（它会禁用内置撤销栈），再启用 Vim
        proxy = EditorProxy(sc, Document())
        vm = VimMode(sc)          # 生产路径：ui/main_window.py:1539-1544
        vm.set_enabled(True)
        assert vm.state == VimState.NORMAL

        before = sc.text()

        # 'x' 删除光标处字符：走 VimMode -> SCI_DELETERANGE
        # -> SCN_MODIFIED -> 自研 UndoManager 记录
        vm.handle_key(
            QKeyEvent(QKeyEvent.KeyPress, Qt.Key_X, Qt.NoModifier, 'x')
        )
        assert sc.text() != before
        assert len(proxy.undo_manager.undo_stack) >= 1, (
            "前置条件：Vim 的 x 应被自研撤销栈记录"
        )

        # 'u' 撤销
        vm.handle_key(
            QKeyEvent(QKeyEvent.KeyPress, Qt.Key_U, Qt.NoModifier, 'u')
        )
        assert sc.text() == before, (
            "Vim 的 u 未生效。VimMode 调用了 self.editor.undo()（QScintilla "
            "内置撤销），而 EditorProxy 已执行 SCI_SETUNDOCOLLECTION(0) "
            "禁用了内置撤销栈；同时 handle_key 返回 True 吞掉按键，"
            "用户的撤销请求被静默丢弃。"
            f" 文本={sc.text()!r}，期望={before!r}，"
            f"自研撤销栈深度={len(proxy.undo_manager.undo_stack)}"
        )

    @pytest.mark.audit_expected_fail
    def test_vim_ctrl_r_uses_disabled_builtin_redo(self, qapp):
        """Ctrl+R（Normal 模式）同理走内置 redo。"""
        from PyQt5.Qsci import QsciScintilla
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QKeyEvent

        from core.document import Document
        from core.editor import EditorProxy
        from core.vim_mode import VimMode

        sc = QsciScintilla()
        sc.setUtf8(True)
        sc.setText("hello world\n")
        sc.setCursorPosition(0, 0)

        proxy = EditorProxy(sc, Document())
        vm = VimMode(sc)
        vm.set_enabled(True)

        sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"Z")
        proxy.undo()
        after_undo = sc.text()

        vm.handle_key(
            QKeyEvent(QKeyEvent.KeyPress, Qt.Key_R,
                      Qt.ControlModifier, '\x12')
        )
        assert sc.text() != after_undo, (
            "Vim 的 Ctrl+R 未生效：同样调用了被禁用的内置 redo。"
            f" 文本={sc.text()!r}"
        )


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
