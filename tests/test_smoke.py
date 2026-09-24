# -*- coding: utf-8 -*-
"""Smoke tests for QingCao editor."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class TestImports(unittest.TestCase):
    def test_import_actions(self):
        import app.actions

    def test_import_event_bus(self):
        import app.event_bus

    def test_import_document(self):
        import core.document

    def test_import_commands(self):
        import core.commands

    def test_import_search(self):
        import core.search

    def test_import_undo(self):
        import core.undo

    def test_import_macro(self):
        import core.macro


class TestCommands(unittest.TestCase):
    def test_insert_to_dict(self):
        from core.commands import InsertCmd
        cmd = InsertCmd(10, "hello")
        d = cmd.to_dict()
        self.assertEqual(d["type"], "insert")
        self.assertEqual(d["pos"], 10)

    def test_delete_to_dict(self):
        from core.commands import DeleteCmd
        cmd = DeleteCmd(5, 3, b"abc")
        d = cmd.to_dict()
        self.assertEqual(d["type"], "delete")
        self.assertEqual(d["len"], 3)

    def test_replace_to_dict(self):
        from core.commands import ReplaceCmd
        cmd = ReplaceCmd(0, 5, "old", "new")
        d = cmd.to_dict()
        self.assertEqual(d["type"], "replace")


class TestPreferences(unittest.TestCase):
    def test_default_font_size(self):
        from app.preferences import Preferences
        prefs = Preferences()
        self.assertIsInstance(prefs.font_size, int)
        self.assertGreater(prefs.font_size, 0)

    def test_set_get(self):
        from app.preferences import Preferences
        prefs = Preferences()
        original = prefs.font_size
        prefs.font_size = 16
        self.assertEqual(prefs.font_size, 16)
        prefs.font_size = original


if __name__ == "__main__":
    unittest.main(verbosity=2)