#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为全局事件总线模块，包含：
- 所有强类型事件数据类（dataclass）
- 事件总线类（基于 PyQt5 pyqtSignal）
# P2-C9: 已从 PySide6 迁移到 PyQt5
- 全局单例实例
- 事件发布/订阅辅助方法
- 事件历史记录
- 事件过滤器
- 调试支持
"""

import time
import weakref
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set

from PyQt5.QtCore import QObject, pyqtSignal

# ============================================================
# 事件类型与事件类（B1b: 统一从 core.events 重导出）
# ============================================================
# 所有事件定义已迁移到 core/events.py。
# 本模块保留 EventBus 与相关工具（EventHistory / subscribe /
# TemporarySubscription），不再重复定义事件类。
#
# 这样做的原因：
#   1. app/event_bus.py 与 core/events.py 曾各自定义过 44 个
#      同名事件类，字段一致但对象不同，isinstance 可能失败。
#   2. B1a 验证了两处字段完全一致、events 是超集。
#   3. 统一到 core.events 后，任何调用方无论从哪个模块导入，
#      拿到的都是同一对象。
from core.events import (
    AppClosingEvent,
    # 应用
    AppEvent,
    AppReadyEvent,
    # 基类
    BaseEvent,
    # 光标与选区
    CursorEvent,
    EditorChangedEvent,
    EditorCreatedEvent,
    EditorDestroyedEvent,
    # 编辑器事件
    EditorEvent,
    EditorFocusedEvent,
    EventFactory,
    # 枚举与工厂
    EventType,
    FileClosedEvent,
    FileEncodingChangedEvent,
    # 文件事件
    FileEvent,
    FileModifiedEvent,
    FileOpenedEvent,
    FileReloadedEvent,
    FileSavedEvent,
    # 宏
    MacroEvent,
    MacroReplayedEvent,
    MacroStartedEvent,
    MacroStoppedEvent,
    NotificationEvent,
    PluginErrorEvent,
    # 插件
    PluginEvent,
    PluginLoadedEvent,
    PluginUnloadedEvent,
    ProjectClosedEvent,
    # 项目
    ProjectEvent,
    ProjectFileAddedEvent,
    ProjectFileEvent,
    ProjectFileRemovedEvent,
    ProjectFileRenamedEvent,
    ProjectOpenedEvent,
    RedoEvent,
    # 搜索
    SearchEvent,
    SearchFinishedEvent,
    SearchResultEvent,
    SearchStartedEvent,
    SelectionEvent,
    # 状态与通知
    StatusMessageEvent,
    TabAddedEvent,
    TabChangedEvent,
    # 标签
    TabEvent,
    TabRemovedEvent,
    TextDeletedEvent,
    # 文本编辑
    TextEditEvent,
    TextInsertedEvent,
    TextReplacedEvent,
    # 主题
    ThemeEvent,
    # 撤销重做
    UndoEvent,
)


class EventHistory:
    """
    事件历史记录器，用于调试和回放。
    默认只保留最近 500 条事件。
    """

    def __init__(self, max_size: int = 500):
        self.max_size = max_size
        self._events: List[BaseEvent] = []
        self._counts: Dict[str, int] = {}

    def record(self, event: BaseEvent):
        """记录一个事件"""
        self._events.append(event)
        event_name = event.__class__.__name__
        self._counts[event_name] = self._counts.get(event_name, 0) + 1
        # 超出容量则移除最旧的
        if len(self._events) > self.max_size:
            self._events.pop(0)

    def clear(self):
        """清空历史"""
        self._events.clear()
        self._counts.clear()

    def get_all(self) -> List[BaseEvent]:
        """获取所有事件"""
        return list(self._events)

    def get_recent(self, count: int = 10) -> List[BaseEvent]:
        """获取最近 N 条事件"""
        return self._events[-count:]

    def get_by_type(self, event_class: type) -> List[BaseEvent]:
        """获取指定类型的事件"""
        return [e for e in self._events if isinstance(e, event_class)]

    def get_counts(self) -> Dict[str, int]:
        """获取各类事件的计数"""
        return dict(self._counts)

    def dump(self, limit: int = 20) -> str:
        """导出最近事件的文本摘要"""
        lines = [f"事件历史 (共 {len(self._events)} 条)", "=" * 60]
        for event in self._events[-limit:]:
            ts = time.strftime("%H:%M:%S", time.localtime(event.timestamp))
            lines.append(f"  [{ts}] {event.__class__.__name__}: {event.to_dict()}")
        return "\n".join(lines)


# ============================================================
# 事件总线
# ============================================================
class EventBus(QObject):
    """
    全局事件总线。

    使用 PySide6 的 pyqtSignal 机制实现类型安全的发布/订阅。
    所有事件均通过对应的 pyqtSignal 发射，订阅者通过 connect 注册。

    特性:
    - 强类型事件（dataclass）
    - 事件历史记录
    - 事件过滤器
    - 调试模式
    """

    # --------------------------------------------------------
    # 文件事件信号
    # --------------------------------------------------------
    file_opened = pyqtSignal(FileOpenedEvent)
    file_saved = pyqtSignal(FileSavedEvent)
    file_closed = pyqtSignal(FileClosedEvent)
    file_modified = pyqtSignal(FileModifiedEvent)
    file_reloaded = pyqtSignal(FileReloadedEvent)
    file_encoding_changed = pyqtSignal(FileEncodingChangedEvent)

    # --------------------------------------------------------
    # 编辑器事件信号
    # --------------------------------------------------------
    editor_changed = pyqtSignal(EditorChangedEvent)
    editor_focused = pyqtSignal(EditorFocusedEvent)
    editor_created = pyqtSignal(EditorCreatedEvent)
    editor_destroyed = pyqtSignal(EditorDestroyedEvent)

    # --------------------------------------------------------
    # 光标与选择信号
    # --------------------------------------------------------
    cursor_moved = pyqtSignal(CursorEvent)
    selection_changed = pyqtSignal(SelectionEvent)

    # --------------------------------------------------------
    # 编辑操作信号
    # --------------------------------------------------------
    text_inserted = pyqtSignal(TextEditEvent)
    text_deleted = pyqtSignal(TextEditEvent)
    undo_performed = pyqtSignal(UndoEvent)
    redo_performed = pyqtSignal(RedoEvent)

    # --------------------------------------------------------
    # 搜索信号
    # --------------------------------------------------------
    search_started = pyqtSignal(SearchStartedEvent)
    search_finished = pyqtSignal(SearchFinishedEvent)
    search_result = pyqtSignal(SearchResultEvent)

    # --------------------------------------------------------
    # 标签信号
    # --------------------------------------------------------
    tab_changed = pyqtSignal(TabChangedEvent)
    tab_added = pyqtSignal(TabAddedEvent)
    tab_removed = pyqtSignal(TabRemovedEvent)

    # --------------------------------------------------------
    # 项目信号
    # --------------------------------------------------------
    project_opened = pyqtSignal(ProjectOpenedEvent)
    project_closed = pyqtSignal(ProjectClosedEvent)
    project_file_added = pyqtSignal(ProjectFileEvent)
    project_file_removed = pyqtSignal(ProjectFileEvent)
    # P0-3 修复：新增 renamed signal
    project_file_renamed = pyqtSignal(ProjectFileEvent)

    # --------------------------------------------------------
    # 宏信号
    # --------------------------------------------------------
    macro_started = pyqtSignal(MacroStartedEvent)
    macro_stopped = pyqtSignal(MacroStoppedEvent)
    macro_replayed = pyqtSignal(MacroReplayedEvent)

    # --------------------------------------------------------
    # 插件信号
    # --------------------------------------------------------
    plugin_loaded = pyqtSignal(PluginLoadedEvent)
    plugin_unloaded = pyqtSignal(PluginUnloadedEvent)
    plugin_error = pyqtSignal(PluginErrorEvent)

    # --------------------------------------------------------
    # 主题信号
    # --------------------------------------------------------
    theme_changed = pyqtSignal(ThemeEvent)

    # --------------------------------------------------------
    # 应用信号
    # --------------------------------------------------------
    app_ready = pyqtSignal(AppReadyEvent)
    app_closing = pyqtSignal(AppClosingEvent)

    # --------------------------------------------------------
    # 状态与通知信号
    # --------------------------------------------------------
    status_message = pyqtSignal(StatusMessageEvent)
    notification = pyqtSignal(NotificationEvent)

    # --------------------------------------------------------
    # 构造函数
    # --------------------------------------------------------
    def __init__(self, parent: Optional[QObject] = None, debug: bool = False):
        super().__init__(parent)

        # 调试模式
        self.debug = debug

        # 事件历史
        self.history = EventHistory(max_size=500)

        # 事件过滤器：{event_class: [filter_func, ...]}
        self._filters: Dict[type, List[Callable[[BaseEvent], bool]]] = {}

        # 订阅者统计：{event_name: count}
        self._subscriber_counts: Dict[str, int] = {}

        # 是否暂停发射（用于批量操作时抑制事件）
        self._paused = False

        # 暂停期间的缓存事件
        self._pending_events: List[BaseEvent] = []

        # 如果开启调试，连接所有信号到记录器
        if debug:
            self._connect_debug_logger()

    # --------------------------------------------------------
    # 事件发射辅助方法
    # --------------------------------------------------------
    def emit_event(self, event: BaseEvent):
        """
        统一的事件发射入口。

        根据事件类型自动路由到对应的 pyqtSignal。
        支持事件过滤和暂停缓存。
        """
        if self._paused:
            self._pending_events.append(event)
            return

        # 应用过滤器
        if not self._apply_filters(event):
            return

        # 记录历史
        self.history.record(event)

        # 调试输出
        if self.debug:
            print(f"[EventBus] {event.__class__.__name__}: {event.to_dict()}")

        # 路由到对应信号
        self._route_event(event)

    def _route_event(self, event: BaseEvent):
        """将事件路由到对应的 pyqtSignal"""
        # 文件事件
        if isinstance(event, FileOpenedEvent):
            self.file_opened.emit(event)
        elif isinstance(event, FileSavedEvent):
            self.file_saved.emit(event)
        elif isinstance(event, FileClosedEvent):
            self.file_closed.emit(event)
        elif isinstance(event, FileModifiedEvent):
            self.file_modified.emit(event)
        elif isinstance(event, FileReloadedEvent):
            self.file_reloaded.emit(event)
        elif isinstance(event, FileEncodingChangedEvent):
            self.file_encoding_changed.emit(event)

        # 编辑器事件
        elif isinstance(event, EditorChangedEvent):
            self.editor_changed.emit(event)
        elif isinstance(event, EditorFocusedEvent):
            self.editor_focused.emit(event)
        elif isinstance(event, EditorCreatedEvent):
            self.editor_created.emit(event)
        elif isinstance(event, EditorDestroyedEvent):
            self.editor_destroyed.emit(event)

        # 光标与选择
        elif isinstance(event, CursorEvent):
            self.cursor_moved.emit(event)
        elif isinstance(event, SelectionEvent):
            self.selection_changed.emit(event)

        # 编辑操作
        elif isinstance(event, TextEditEvent):
            # 根据具体类型区分（保留扩展空间）
            self.text_inserted.emit(event)
        elif isinstance(event, UndoEvent):
            self.undo_performed.emit(event)
        elif isinstance(event, RedoEvent):
            self.redo_performed.emit(event)

        # 搜索
        elif isinstance(event, SearchStartedEvent):
            self.search_started.emit(event)
        elif isinstance(event, SearchFinishedEvent):
            self.search_finished.emit(event)
        elif isinstance(event, SearchResultEvent):
            self.search_result.emit(event)

        # 标签
        elif isinstance(event, TabChangedEvent):
            self.tab_changed.emit(event)
        elif isinstance(event, TabAddedEvent):
            self.tab_added.emit(event)
        elif isinstance(event, TabRemovedEvent):
            self.tab_removed.emit(event)

        # 项目
        elif isinstance(event, ProjectOpenedEvent):
            self.project_opened.emit(event)
        elif isinstance(event, ProjectClosedEvent):
            self.project_closed.emit(event)
        # P0-3 修复：先检查子类，避免 ProjectFileEvent 基类
        # 把所有子类都当成 ProjectFileAddedEvent 发出。
        elif isinstance(event, ProjectFileAddedEvent):
            self.project_file_added.emit(event)
        elif isinstance(event, ProjectFileRemovedEvent):
            self.project_file_removed.emit(event)
        elif isinstance(event, ProjectFileRenamedEvent):
            self.project_file_renamed.emit(event)

        # 宏
        elif isinstance(event, MacroStartedEvent):
            self.macro_started.emit(event)
        elif isinstance(event, MacroStoppedEvent):
            self.macro_stopped.emit(event)
        elif isinstance(event, MacroReplayedEvent):
            self.macro_replayed.emit(event)

        # 插件
        elif isinstance(event, PluginLoadedEvent):
            self.plugin_loaded.emit(event)
        elif isinstance(event, PluginUnloadedEvent):
            self.plugin_unloaded.emit(event)
        elif isinstance(event, PluginErrorEvent):
            self.plugin_error.emit(event)

        # 主题
        elif isinstance(event, ThemeEvent):
            self.theme_changed.emit(event)

        # 应用
        elif isinstance(event, AppReadyEvent):
            self.app_ready.emit(event)
        elif isinstance(event, AppClosingEvent):
            self.app_closing.emit(event)

        # 状态与通知
        elif isinstance(event, StatusMessageEvent):
            self.status_message.emit(event)
        elif isinstance(event, NotificationEvent):
            self.notification.emit(event)

        else:
            if self.debug:
                print(f"[EventBus] 未知事件类型: {event.__class__.__name__}")

    # --------------------------------------------------------
    # 事件过滤
    # --------------------------------------------------------
    def add_filter(self, event_class: type, filter_func: Callable[[BaseEvent], bool]):
        """
        为指定类型的事件添加过滤器。

        过滤器函数接收事件对象，返回 True 表示允许通过，False 表示拦截。

        用法:
            def filter_cursor(event):
                return event.line > 0  # 忽略行号为0的事件
            bus.add_filter(CursorEvent, filter_cursor)
        """
        self._filters.setdefault(event_class, []).append(filter_func)

    def remove_filter(self, event_class: type, filter_func: Callable):
        """移除过滤器"""
        if event_class in self._filters:
            try:
                self._filters[event_class].remove(filter_func)
            except ValueError:
                pass

    def clear_filters(self):
        """清空所有过滤器"""
        self._filters.clear()

    def _apply_filters(self, event: BaseEvent) -> bool:
        """应用所有适用的过滤器，返回 True 表示允许通过"""
        for event_class, filters in self._filters.items():
            if isinstance(event, event_class):
                for f in filters:
                    try:
                        if not f(event):
                            return False
                    except Exception as e:
                        if self.debug:
                            print(f"[EventBus] 过滤器异常: {e}")
        return True

    # --------------------------------------------------------
    # 暂停/恢复
    # --------------------------------------------------------
    def pause(self):
        """暂停事件发射（缓存到队列）"""
        self._paused = True

    def resume(self, flush: bool = True):
        """
        恢复事件发射。

        参数:
            flush: 是否立即发射暂停期间缓存的事件
        """
        self._paused = False
        if flush and self._pending_events:
            pending = self._pending_events
            self._pending_events = []
            for event in pending:
                self.emit_event(event)

    def is_paused(self) -> bool:
        """检查是否处于暂停状态"""
        return self._paused

    # --------------------------------------------------------
    # 便捷方法（常用事件的快捷方式）
    # --------------------------------------------------------
    def emit_status(self, message: str, timeout: int = 3000, level: str = "info"):
        """发射状态栏消息的快捷方法"""
        self.emit_event(StatusMessageEvent(
            message=message, timeout=timeout, level=level
        ))

    def emit_notification(self, title: str, message: str,
                          level: str = "info", actions: Optional[List[str]] = None):
        """发射通知的快捷方法"""
        self.emit_event(NotificationEvent(
            title=title, message=message, level=level,
            actions=actions or []
        ))

    def emit_error(self, title: str, message: str):
        """发射错误通知"""
        self.emit_notification(title, message, level="error")

    def emit_success(self, message: str, timeout: int = 2000):
        """发射成功状态"""
        self.emit_status(message, timeout, level="success")

    # --------------------------------------------------------
    # 调试
    # --------------------------------------------------------
    def _connect_debug_logger(self):
        """连接所有信号到调试记录器"""
        # 由于信号参数类型各异，这里用通用方式
        # 实际使用时通过 emit_event 中的 debug 输出已足够
        pass

    def dump_history(self, limit: int = 20) -> str:
        """导出事件历史"""
        return self.history.dump(limit)

    def clear_history(self):
        """清空事件历史"""
        self.history.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取事件统计信息"""
        return {
            'total_events': len(self.history.get_all()),
            'event_counts': self.history.get_counts(),
            'filter_count': sum(len(v) for v in self._filters.values()),
            'paused': self._paused,
            'pending_count': len(self._pending_events),
        }


# ============================================================
# 全局单例
# ============================================================
# 全局事件总线实例。所有模块共享同一个实例。
#
# 用法:
#     from app.event_bus import bus
#
#     # 发射事件
#     bus.emit_event(FileOpenedEvent(path="/path/to/file"))
#
#     # 订阅事件
#     bus.file_opened.connect(lambda e: print(f"打开了 {e.path}"))
#
bus = EventBus(debug=False)


# ============================================================
# 装饰器：订阅事件
# ============================================================
def subscribe(event_signal: pyqtSignal):
    """
    事件订阅装饰器。

    用法:
        @subscribe(bus.file_opened)
        def on_file_opened(event):
            print(f"打开了: {event.path}")

    注意: 装饰器会立即连接信号，被装饰的函数不能是类方法
    （除非在类定义后手动连接）。
    """
    def decorator(func: Callable):
        event_signal.connect(func)
        return func
    return decorator


# ============================================================
# 上下文管理器：临时连接
# ============================================================
class TemporarySubscription:
    """
    临时订阅上下文管理器。

    用法:
        with TemporarySubscription(bus.file_opened, callback):
            # 此作用域内 callback 会接收 file_opened 事件
            ...
        # 退出后自动断开
    """

    def __init__(self, signal: pyqtSignal, slot: Callable):
        self.signal = signal
        self.slot = slot

    def __enter__(self):
        self.signal.connect(self.slot)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.signal.disconnect(self.slot)
        except (TypeError, RuntimeError):
            pass
        return False


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # 使用全局单例
    from app.event_bus import bus

    # 测试订阅
    def on_file_opened(event: FileOpenedEvent):
        print(f"[订阅] 文件已打开: {event.path}, 大小: {event.size}")

    def on_cursor_moved(event: CursorEvent):
        print(f"[订阅] 光标移动到: 行{event.line}, 列{event.col}")

    bus.file_opened.connect(on_file_opened)
    bus.cursor_moved.connect(on_cursor_moved)

    # 测试事件发射
    print("=== 测试文件打开事件 ===")
    bus.emit_event(FileOpenedEvent(
        path="/home/user/test.py",
        size=1024,
        line_count=50,
        encoding="utf-8",
        source="test"
    ))

    print("\n=== 测试光标移动事件 ===")
    bus.emit_event(CursorEvent(line=10, col=5, position=100))

    print("\n=== 测试状态消息 ===")
    bus.emit_status("测试状态消息", timeout=2000)

    print("\n=== 测试过滤器 ===")
    def filter_cursor(event: CursorEvent) -> bool:
        return event.line > 5  # 只允许行号大于5的通过

    bus.add_filter(CursorEvent, filter_cursor)
    bus.emit_event(CursorEvent(line=3, col=0))   # 应被过滤
    bus.emit_event(CursorEvent(line=8, col=0))   # 应通过

    print("\n=== 测试暂停/恢复 ===")
    bus.pause()
    bus.emit_event(CursorEvent(line=20, col=10))
    bus.emit_event(CursorEvent(line=25, col=15))
    print(f"暂停期间缓存了 {bus.get_stats()['pending_count']} 个事件")
    bus.resume()

    print("\n=== 事件统计 ===")
    stats = bus.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n=== 事件历史 ===")
    print(bus.dump_history(limit=10))