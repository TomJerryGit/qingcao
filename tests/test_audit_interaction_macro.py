# -*- coding: utf-8 -*-
"""
交互审计：宏录制 / 回放 × 撤销
=============================

覆盖的交互：
    1. 宏回放 × 撤销栈 —— replay() 用 SCI_SETMODEVENTMASK(0) 关掉了
       Scintilla 修改通知，EditorProxy._on_scintilla_modified 收不到事件，
       自研 UndoManager 里不会有任何回放命令；但回放确实改变了缓冲区。
       结果：Ctrl+Z 弹出的是"回放之前的旧命令"，按旧位置执行 -> 内容损坏。
    2. 宏回放 × 修改标记 —— replay 只改 proxy._modified，不调用
       document.mark_modified()，两处"是否已修改"的真值出现分歧。

断言不变式：
    INV-M1  任何改变缓冲区的操作都必须能通过应用自己的撤销栈撤回。
    INV-M2  回放宏之后按一次 Ctrl+Z，必须回到回放前的内容。
    INV-M3  proxy.is_modified 与 document.is_modified 不得互相矛盾。

运行方式：
    python -m pytest tests/test_audit_interaction_macro.py -v
"""

import pytest


def _fresh(qapp):
    from PyQt5.Qsci import QsciScintilla

    from core.document import Document
    from core.editor import EditorProxy

    sc = QsciScintilla()
    sc.setUtf8(True)
    sc.setText("")
    proxy = EditorProxy(sc, Document())
    proxy.undo_manager.clear()
    return sc, proxy


class TestMacroReplayVsUndo:

    @pytest.mark.audit_expected_fail
    def test_replay_is_not_recorded_in_undo_stack(self, qapp):
        from core.macro import MacroRecorder

        sc, proxy = _fresh(qapp)
        recorder = MacroRecorder(undo_manager=proxy.undo_manager)

        # ---- 录一个"插入 AAA"的宏 ----
        recorder.start("m")
        sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"AAA")
        recorder.stop()

        assert len(recorder.current_macro.commands) >= 1, (
            "前置条件：宏应有至少 1 条命令"
        )

        # ---- 再做一次手工编辑，让撤销栈里除了宏的命令之外还有别的 ----
        sc.SendScintilla(sc.SCI_INSERTTEXT, 3, b"-")
        assert sc.text() == "AAA-"

        # 把录制期间产生的那条命令从撤销栈里移除，
        # 以便单独观察"回放"这一动作是否进栈
        proxy.undo_manager.undo_stack.clear()
        proxy.undo_manager.redo_stack.clear()

        depth_before = len(proxy.undo_manager.undo_stack)
        text_before = sc.text()

        ok = recorder.replay(
            proxy, recorder.current_macro,
            show_progress=False, check_cancel=False
        )
        assert ok is True
        assert sc.text() != text_before, "前置条件：回放应改变内容"

        # ---- INV-M1 ----
        depth_after = len(proxy.undo_manager.undo_stack)
        assert depth_after > depth_before, (
            "INV-M1 违反：宏回放改变了缓冲区，却没有向自研撤销栈写入任何命令。\n"
            "  原因：core/macro.py:702-707 _disable_scintilla_notifications() "
            "执行 SCI_SETMODEVENTMASK=0，"
            "core/editor.py:645-663 的 _on_scintilla_modified 因此不触发，"
            "UndoManager.record() 从未被调用；回放结束后也没有 clear() "
            "或补偿性记录。\n"
            f"  撤销栈深度 {depth_before} -> {depth_after}"
        )

    @pytest.mark.audit_expected_fail
    def test_undo_after_replay_returns_to_pre_replay_state(self, qapp):
        """INV-M2：回放后按一次撤销应回到回放前的内容。"""
        from core.macro import MacroRecorder

        sc, proxy = _fresh(qapp)
        recorder = MacroRecorder(undo_manager=proxy.undo_manager)

        recorder.start("m")
        sc.SendScintilla(sc.SCI_INSERTTEXT, 0, b"AAA")
        recorder.stop()

        proxy.undo_manager.undo_stack.clear()
        proxy.undo_manager.redo_stack.clear()

        sc.SendScintilla(sc.SCI_INSERTTEXT, 3, b"-")
        assert sc.text() == "AAA-"
        text_before = sc.text()
        undo_depth_before = len(proxy.undo_manager.undo_stack)

        recorder.replay(
            proxy, recorder.current_macro,
            show_progress=False, check_cancel=False
        )
        text_after = sc.text()
        assert text_after != text_before

        # 用户按 Ctrl+Z
        proxy.undo()
        result = sc.text()

        assert result == text_before, (
            "INV-M2 违反：回放宏后按一次撤销没有回到回放前的内容。\n"
            f"  回放前={text_before!r} 回放后={text_after!r} "
            f"撤销后={result!r}\n"
            f"  撤销栈深度（回放前）={undo_depth_before}，"
            f"回放未入栈，于是 undo 弹出的是回放之前的旧命令并按其记录的"
            "旧位置执行，产生了一个在线性 undo/redo 历史中不可达的状态。"
        )

    @pytest.mark.audit_expected_fail
    def test_replay_keeps_modified_flags_consistent(self, qapp):
        """INV-M3：proxy 与 document 的修改标记必须一致。"""
        from core.commands import InsertCmd
        from core.macro import Macro, MacroRecorder

        sc, proxy = _fresh(qapp)
        recorder = MacroRecorder(undo_manager=proxy.undo_manager)

        macro = Macro(name="m")
        macro.add_command(InsertCmd(0, "ZZ"))

        assert proxy.is_modified is False
        assert proxy.document.is_modified is False

        recorder.replay(proxy, macro,
                        show_progress=False, check_cancel=False)

        assert sc.text() == "ZZ", "前置条件：回放应写入 ZZ"

        assert bool(proxy.is_modified) == bool(proxy.document.is_modified), (
            "INV-M3 违反：宏回放只设置了 proxy._modified"
            "（core/macro.py:619-626），没有调用 document.mark_modified()，"
            "两处'已修改'状态不一致。\n"
            f"  proxy.is_modified={proxy.is_modified} "
            f"document.is_modified={proxy.document.is_modified}"
        )


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-v"]))
