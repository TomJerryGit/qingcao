# -*- coding: utf-8 -*-
"""事件类字段存在性测试（B1a）"""
import dataclasses


def _has_field(cls, name):
    try:
        return name in {f.name for f in dataclasses.fields(cls)}
    except Exception:
        return False


class TestEventFields:

    def test_search_started_has_scope(self):
        from core.events import SearchStartedEvent
        assert _has_field(SearchStartedEvent, 'scope'), \
            "SearchStartedEvent 缺少 scope 字段（B1a 修复）"

    def test_editor_changed_has_filepath(self):
        from core.events import EditorChangedEvent
        # filepath 从 EditorEvent 继承
        assert _has_field(EditorChangedEvent, 'filepath')

    def test_editor_created_has_filepath(self):
        from core.events import EditorCreatedEvent
        assert _has_field(EditorCreatedEvent, 'filepath')

    def test_file_opened_fields(self):
        from core.events import FileOpenedEvent
        for name in ('path', 'encoding', 'size', 'line_count', 'is_readonly'):
            assert _has_field(FileOpenedEvent, name), \
                f"FileOpenedEvent 缺少 {name}"

    def test_file_saved_fields(self):
        from core.events import FileSavedEvent
        for name in ('path', 'encoding', 'size', 'backup_path'):
            assert _has_field(FileSavedEvent, name), \
                f"FileSavedEvent 缺少 {name}"

    def test_cursor_fields(self):
        from core.events import CursorEvent
        for name in ('line', 'col', 'position'):
            assert _has_field(CursorEvent, name), \
                f"CursorEvent 缺少 {name}"

    def test_tab_changed_fields(self):
        from core.events import TabChangedEvent
        for name in ('index', 'title', 'filepath', 'old_index'):
            assert _has_field(TabChangedEvent, name), \
                f"TabChangedEvent 缺少 {name}"

    def test_macro_started_has_macro_name(self):
        from core.events import MacroStartedEvent
        assert _has_field(MacroStartedEvent, 'macro_name')

    def test_macro_stopped_has_duration(self):
        from core.events import MacroStoppedEvent
        assert _has_field(MacroStoppedEvent, 'duration_seconds')

    def test_status_message_fields(self):
        from core.events import StatusMessageEvent
        for name in ('message', 'timeout', 'level'):
            assert _has_field(StatusMessageEvent, name), \
                f"StatusMessageEvent 缺少 {name}"
