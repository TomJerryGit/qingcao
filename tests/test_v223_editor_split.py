# -*- coding: utf-8 -*-
"""v2.23 D1：core/editor.py 拆分结构回归"""

import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIXINS = (
    "editor_save",
    "editor_loading",
    "editor_cursor",
    "editor_editops",
    "editor_bookmarks",
    "editor_search",
)


def test_editor_split_structure():
    lines = len(open(os.path.join(ROOT, "core", "editor.py"), encoding="utf-8").readlines())
    assert lines < 2200, "editor.py 拆分后应 < 2200 行，当前 %d" % lines
    for name in MIXINS:
        assert os.path.isfile(os.path.join(ROOT, "core", name + ".py"))
    from core.editor import EditorProxy

    bases = [c.__name__ for c in EditorProxy.__mro__]
    for name in (
        "EditorSaveMixin",
        "EditorLoadingMixin",
        "EditorCursorMixin",
        "EditorEditOpsMixin",
        "EditorBookmarksMixin",
        "EditorSearchMixin",
        "EditorEventsMixin",
        "EditorLspMixin",
        "EditorTextOpsMixin",
    ):
        assert name in bases, (name, bases)
    for name in (
        "save_file",
        "open_file",
        "get_text",
        "move_line_down",
        "toggle_bookmark",
        "search_in_buffer",
        "highlight_all",
    ):
        assert hasattr(EditorProxy, name), name


def test_editor_common_shared():
    import core.editor_common as common

    assert hasattr(common, "_normalize_bytes")
    assert hasattr(common, "MARKER_BOOKMARK")
    assert hasattr(common, "INDICATOR_SEARCH")
