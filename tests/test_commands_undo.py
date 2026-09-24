# -*- coding: utf-8 -*-
"""命令与撤销管理器测试"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class TestInsertCmd(unittest.TestCase):
    def test_create(self):
        from core.commands import InsertCmd
        cmd = InsertCmd(10, "hello")
        self.assertEqual(cmd.pos, 10)
        self.assertEqual(cmd.text, "hello")
        self.assertEqual(cmd.command_type, "insert")

    def test_to_dict_roundtrip(self):
        from core.commands import InsertCmd
        cmd = InsertCmd(10, "hello")
        d = cmd.to_dict()
        cmd2 = InsertCmd.from_dict(d)
        self.assertEqual(cmd2.pos, 10)
        self.assertEqual(cmd2.text, "hello")

    def test_can_merge(self):
        import time
        from core.commands import InsertCmd
        c1 = InsertCmd(0, "hello")
        c2 = InsertCmd(5, " world")
        c2.timestamp = c1.timestamp + 0.05  # 50ms 后
        self.assertTrue(c1.can_merge(c2))

    def test_merge_with(self):
        from core.commands import InsertCmd
        c1 = InsertCmd(0, "hello")
        c2 = InsertCmd(5, " world")
        c2.timestamp = c1.timestamp + 0.05
        merged = c1.merge_with(c2)
        self.assertIsNotNone(merged)
        self.assertEqual(merged.text, "hello world")


class TestDeleteCmd(unittest.TestCase):
    def test_create(self):
        from core.commands import DeleteCmd
        cmd = DeleteCmd(5, 3, b"abc")
        self.assertEqual(cmd.pos, 5)
        self.assertEqual(cmd.length, 3)
        self.assertEqual(cmd.deleted_text, b"abc")

    def test_to_dict(self):
        from core.commands import DeleteCmd
        cmd = DeleteCmd(5, 3, b"abc")
        d = cmd.to_dict()
        self.assertEqual(d['type'], 'delete')
        self.assertEqual(d['pos'], 5)
        self.assertEqual(d['len'], 3)


class TestReplaceCmd(unittest.TestCase):
    def test_create(self):
        from core.commands import ReplaceCmd
        cmd = ReplaceCmd(0, 5, "old", "new")
        self.assertEqual(cmd.old_text, "old")
        self.assertEqual(cmd.new_text, "new")


class TestGroupCmd(unittest.TestCase):
    def test_create(self):
        from core.commands import GroupCmd, InsertCmd
        g = GroupCmd([
            InsertCmd(0, "a"),
            InsertCmd(1, "b"),
        ])
        self.assertEqual(len(g.cmds), 2)
        self.assertEqual(g.command_type, "group")

    def test_to_dict(self):
        from core.commands import GroupCmd, InsertCmd
        g = GroupCmd([InsertCmd(0, "a")])
        d = g.to_dict()
        self.assertEqual(d['type'], 'group')
        self.assertEqual(len(d['cmds']), 1)


class TestSerialization(unittest.TestCase):
    def test_serialize_deserialize(self):
        from core.commands import (
            InsertCmd, DeleteCmd, ReplaceCmd,
            CommandSerializer
        )
        cmds = [
            InsertCmd(0, "hello"),
            DeleteCmd(5, 3, b"abc"),
            ReplaceCmd(10, 5, "old", "new"),
        ]
        data = CommandSerializer.serialize(cmds)
        restored = CommandSerializer.deserialize(data)
        self.assertEqual(len(restored), 3)


class TestCommandPool(unittest.TestCase):
    def test_acquire_release(self):
        from core.commands import CommandPool
        CommandPool.clear()
        cmd = CommandPool.acquire_insert(0, "test")
        self.assertIsNotNone(cmd)
        CommandPool.release_insert(cmd)
        stats = CommandPool.stats()
        self.assertGreater(stats['insert_pool_size'], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)