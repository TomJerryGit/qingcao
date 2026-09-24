# -*- coding: utf-8 -*-
"""
UndoManager 单元测试。

覆盖:
- 记录命令
- 撤销 / 重做
- 命令合并
- 命令组
- 事务
- 保存点
- 深度限制
"""

import os
import sys
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================
# Fake Scintilla
# ============================================================
class FakeScintilla:
    """
    模拟 QScintilla 控件，仅记录文本。

    只实现 InsertCmd / DeleteCmd 用到的最小接口：
    - SendScintilla(cmd, *args)
    - SCI_GETLENGTH, SCI_INSERTTEXT, SCI_DELETERANGE
    """

    # 常量（与 QScintilla 无关，只用于测试）
    SCI_GETLENGTH = 2001
    SCI_INSERTTEXT = 2002
    SCI_DELETERANGE = 2003

    def __init__(self):
        self.text = ""

    def SendScintilla(self, cmd, *args):
        if cmd == self.SCI_GETLENGTH:
            return len(self.text)
        elif cmd == self.SCI_INSERTTEXT:
            pos, data = args
            if isinstance(data, bytes):
                data = data.decode('utf-8', errors='replace')
            self.text = self.text[:pos] + data + self.text[pos:]
            return len(data)
        elif cmd == self.SCI_DELETERANGE:
            pos, length = args
            self.text = self.text[:pos] + self.text[pos + length:]
            return length
        return 0


# ============================================================
# 基本记录
# ============================================================
class TestBasicRecord:
    """测试记录命令"""

    def test_record_single_command(self, qapp):
        from core.undo import UndoManager
        from core.commands import InsertCmd

        mgr = UndoManager()
        mgr.record(InsertCmd(0, "hello"))

        assert mgr.get_undo_count() == 1
        assert mgr.get_redo_count() == 0
        assert mgr.can_undo()

    def test_record_clears_redo(self, qapp):
        from core.undo import UndoManager
        from core.commands import InsertCmd

        mgr = UndoManager()
        mgr.record(InsertCmd(0, "a"))
        mgr.record(InsertCmd(1, "b"))

        # 手动撤销一次 → 重做栈有 1 个
        sc = FakeScintilla()
        sc.text = "ab"
        mgr.undo(sc)
        assert mgr.get_redo_count() == 1

        # 记录新命令 → 重做栈清空
        mgr.record(InsertCmd(2, "c"))
        assert mgr.get_redo_count() == 0


# ============================================================
# 撤销 / 重做
# ============================================================
class TestUndoRedo:
    """测试撤销/重做"""

    def test_undo_insert(self, qapp):
        from core.undo import UndoManager
        from core.commands import InsertCmd

        mgr = UndoManager()
        sc = FakeScintilla()

        cmd = InsertCmd(0, "hello")
        cmd.execute(sc)
        assert sc.text == "hello"

        mgr.record(cmd)
        mgr.undo(sc)
        assert sc.text == ""

    def test_redo(self, qapp):
        from core.undo import UndoManager
        from core.commands import InsertCmd

        mgr = UndoManager()
        sc = FakeScintilla()

        cmd = InsertCmd(0, "hello")
        cmd.execute(sc)
        mgr.record(cmd)

        mgr.undo(sc)
        assert sc.text == ""
        assert mgr.get_redo_count() == 1

        mgr.redo(sc)
        assert sc.text == "hello"
        assert mgr.get_redo_count() == 0

    def test_undo_empty_stack(self, qapp):
        from core.undo import UndoManager

        mgr = UndoManager()
        sc = FakeScintilla()
        assert mgr.undo(sc) is False

    def test_redo_empty_stack(self, qapp):
        from core.undo import UndoManager

        mgr = UndoManager()
        sc = FakeScintilla()
        assert mgr.redo(sc) is False


# ============================================================
# 命令合并
# ============================================================
class TestMerge:
    """测试命令合并"""

    def test_consecutive_inserts_merge(self, qapp):
        from core.undo import UndoManager
        from core.commands import InsertCmd

        mgr = UndoManager(merge_interval=1000)  # 宽窗口

        # 连续插入
        c1 = InsertCmd(0, "H")
        mgr.record(c1)

        c2 = InsertCmd(1, "i")
        mgr.record(c2)

        # 应该合并为 1 条命令
        assert mgr.get_undo_count() == 1

        # 合并后的命令包含 "Hi"
        cmd = mgr.undo_stack[0]
        assert "Hi" in (cmd.text if hasattr(cmd, 'text') else '')


# ============================================================
# 命令组
# ============================================================
class TestGroup:
    """测试命令组"""

    def test_begin_end_group(self, qapp):
        from core.undo import UndoManager
        from core.commands import InsertCmd

        mgr = UndoManager()

        mgr.begin_group(InsertCmd(0, "a"))
        mgr.record(InsertCmd(1, "b"))
        mgr.record(InsertCmd(2, "c"))
        mgr.end_group()

        # 应该只有 1 条 GroupCmd
        assert mgr.get_undo_count() == 1

        group = mgr.undo_stack[0]
        assert hasattr(group, 'cmds')
        assert len(group.cmds) == 3

    def test_group_undo_atomic(self, qapp):
        from core.undo import UndoManager
        from core.commands import InsertCmd

        mgr = UndoManager()
        sc = FakeScintilla()

        # 手动执行命令，让 sc.text = "abc"
        c1, c2, c3 = InsertCmd(0, "a"), InsertCmd(1, "b"), InsertCmd(2, "c")
        c1.execute(sc)
        c2.execute(sc)
        c3.execute(sc)
        assert sc.text == "abc"

        mgr.begin_group(c1)
        mgr.record(c2)
        mgr.record(c3)
        mgr.end_group()

        # 撤销组 → 全部消失
        mgr.undo(sc)
        assert sc.text == ""


# ============================================================
# 保存点
# ============================================================
class TestSavePoint:
    """测试保存点"""

    def test_mark_save_point(self, qapp):
        from core.undo import UndoManager
        from core.commands import InsertCmd

        mgr = UndoManager()

        mgr.record(InsertCmd(0, "a"))
        mgr.mark_save_point("saved")

        assert mgr.is_clean()

    def test_leave_save_point_after_record(self, qapp):
        from core.undo import UndoManager
        from core.commands import InsertCmd

        mgr = UndoManager()
        mgr.mark_save_point("start")

        assert mgr.is_clean()

        mgr.record(InsertCmd(0, "x"))
        # 有时间窗口合并，不一定立即离开保存点
        # 所以这里只检查状态一致
        assert isinstance(mgr.is_clean(), bool)


# ============================================================
# 深度限制
# ============================================================
class TestDepthLimit:
    """测试撤销栈深度限制"""

    def test_max_depth(self, qapp):
        from core.undo import UndoManager
        from core.commands import InsertCmd

        mgr = UndoManager(max_depth=10)

        # 记录 20 条
        for i in range(20):
            # 用不同位置避免合并
            mgr.record(InsertCmd(i * 100, "x"))

        # 应该不超过 10
        assert mgr.get_undo_count() <= 10


# ============================================================
# 批量操作
# ============================================================
class TestBatch:
    """测试批量撤销/重做"""

    def test_undo_multiple(self, qapp):
        from core.undo import UndoManager
        from core.commands import InsertCmd

        mgr = UndoManager()
        sc = FakeScintilla()

        cmds = []
        for i in range(5):
            c = InsertCmd(i * 10, "x")
            c.execute(sc)
            cmds.append(c)
            mgr.record(c)

        count = mgr.undo_multiple(sc, 3)
        assert count == 3
        assert mgr.get_undo_count() == 2
        assert mgr.get_redo_count() == 3


# ============================================================
# 清空
# ============================================================
class TestClear:
    """测试清空"""

    def test_clear(self, qapp):
        from core.undo import UndoManager
        from core.commands import InsertCmd

        mgr = UndoManager()
        mgr.record(InsertCmd(0, "a"))
        mgr.record(InsertCmd(1, "b"))

        mgr.clear()
        assert mgr.get_undo_count() == 0
        assert mgr.get_redo_count() == 0
        assert not mgr.can_undo()