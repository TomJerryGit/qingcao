# -*- coding: utf-8 -*-
"""事件类身份测试（B1b）

B1b 合并后，从 app.event_bus 与 core.events 导入的同名事件类
应是**同一个对象**（is 断言），而非两份定义。
"""
import pytest


# 在 event_bus.py 里定义的 44 个事件类名
EVENT_NAMES = [
    'BaseEvent',
    'FileEvent', 'FileOpenedEvent', 'FileSavedEvent',
    'FileClosedEvent', 'FileModifiedEvent', 'FileReloadedEvent',
    'FileEncodingChangedEvent',
    'EditorEvent', 'EditorChangedEvent', 'EditorFocusedEvent',
    'EditorCreatedEvent', 'EditorDestroyedEvent',
    'CursorEvent', 'SelectionEvent',
    'TextEditEvent',
    'UndoEvent', 'RedoEvent',
    'SearchEvent', 'SearchStartedEvent', 'SearchFinishedEvent',
    'SearchResultEvent',
    'TabEvent', 'TabChangedEvent', 'TabAddedEvent', 'TabRemovedEvent',
    'ProjectEvent', 'ProjectOpenedEvent', 'ProjectClosedEvent',
    'ProjectFileEvent',
    'MacroEvent', 'MacroStartedEvent', 'MacroStoppedEvent',
    'MacroReplayedEvent',
    'PluginEvent', 'PluginLoadedEvent', 'PluginUnloadedEvent',
    'PluginErrorEvent',
    'ThemeEvent',
    'AppEvent', 'AppReadyEvent', 'AppClosingEvent',
    'StatusMessageEvent', 'NotificationEvent',
]


class TestEventIdentity:

    def test_event_classes_are_same_object(self):
        """从两个模块导入的事件类应是同一个对象"""
        import app.event_bus as bus_mod
        import core.events as evt_mod

        mismatched = []
        for name in EVENT_NAMES:
            a = getattr(bus_mod, name, None)
            b = getattr(evt_mod, name, None)
            if a is None:
                mismatched.append(f"{name}: 不在 app.event_bus")
                continue
            if b is None:
                mismatched.append(f"{name}: 不在 core.events")
                continue
            if a is not b:
                mismatched.append(f"{name}: 不是同一对象")

        assert not mismatched, (
            "B1b 合并失败，以下事件类不是同一对象:\n  "
            + "\n  ".join(mismatched)
        )

    def test_event_type_enum_is_same(self):
        """EventType 枚举也是同一对象"""
        from app.event_bus import EventType as A
        from core.events import EventType as B
        assert A is B

    def test_base_event_is_same(self):
        """BaseEvent 是同一对象"""
        from app.event_bus import BaseEvent as A
        from core.events import BaseEvent as B
        assert A is B

    def test_isinstance_across_modules(self):
        """跨模块 isinstance 检查正常"""
        from app.event_bus import FileOpenedEvent as BusEvt
        from core.events import FileOpenedEvent as CoreEvt

        obj = BusEvt(path="/tmp/x.txt")
        assert isinstance(obj, CoreEvt)
        assert isinstance(obj, BusEvt)
