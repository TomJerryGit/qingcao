#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为事件数据类模块，包含：
- BaseEvent：所有事件的基类
- 文件事件（FileOpenedEvent / FileSavedEvent / FileClosedEvent 等）
- 编辑器事件（EditorChangedEvent / EditorCreatedEvent 等）
- 光标与选区事件（CursorEvent / SelectionEvent）
- 文本编辑事件（TextInsertedEvent / TextDeletedEvent 等）
- 撤销重做事件（UndoEvent / RedoEvent）
- 搜索事件（SearchStartedEvent / SearchFinishedEvent 等）
- 标签事件（TabChangedEvent / TabAddedEvent / TabRemovedEvent）
- 项目事件（ProjectOpenedEvent / ProjectClosedEvent 等）
- 宏事件（MacroStartedEvent / MacroStoppedEvent 等）
- 插件事件（PluginLoadedEvent / PluginErrorEvent 等）
- 主题事件（ThemeEvent）
- 应用事件（AppReadyEvent / AppClosingEvent）
- 状态与通知事件（StatusMessageEvent / NotificationEvent）
- 事件类型枚举（EventType）
- 事件工厂与注册表（EventFactory）
- 事件序列化辅助
- 事件过滤辅助
"""

import datetime
import json
import time
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from enum import Enum, auto
from typing import Any, ClassVar, Dict, List, Optional, Tuple, Type


# ============================================================
# 事件类型枚举
# ============================================================
class EventType(Enum):
    """
    事件类型枚举。

    用于快速判断事件类别，避免频繁的 isinstance 检查。
    """
    # 文件事件
    FILE_OPENED = auto()
    FILE_SAVED = auto()
    FILE_CLOSED = auto()
    FILE_MODIFIED = auto()
    FILE_RELOADED = auto()
    FILE_ENCODING_CHANGED = auto()

    # 编辑器事件
    EDITOR_CHANGED = auto()
    EDITOR_FOCUSED = auto()
    EDITOR_CREATED = auto()
    EDITOR_DESTROYED = auto()

    # 光标与选区
    CURSOR_MOVED = auto()
    SELECTION_CHANGED = auto()

    # 文本编辑
    TEXT_INSERTED = auto()
    TEXT_DELETED = auto()
    TEXT_REPLACED = auto()

    # 撤销重做
    UNDO_PERFORMED = auto()
    REDO_PERFORMED = auto()

    # 搜索
    SEARCH_STARTED = auto()
    SEARCH_FINISHED = auto()
    SEARCH_RESULT = auto()

    # 标签
    TAB_CHANGED = auto()
    TAB_ADDED = auto()
    TAB_REMOVED = auto()

    # 项目
    PROJECT_OPENED = auto()
    PROJECT_CLOSED = auto()
    PROJECT_FILE_ADDED = auto()
    PROJECT_FILE_REMOVED = auto()
    PROJECT_FILE_RENAMED = auto()

    # 宏
    MACRO_STARTED = auto()
    MACRO_STOPPED = auto()
    MACRO_REPLAYED = auto()

    # 插件
    PLUGIN_LOADED = auto()
    PLUGIN_UNLOADED = auto()
    PLUGIN_ERROR = auto()

    # 主题
    THEME_CHANGED = auto()

    # 应用
    APP_READY = auto()
    APP_CLOSING = auto()

    # 状态与通知
    STATUS_MESSAGE = auto()
    NOTIFICATION = auto()

    # 未知
    UNKNOWN = auto()


# ============================================================
# 事件类型到枚举的映射（由子类通过 event_type 类属性指定）
# ============================================================
_EVENT_TYPE_REGISTRY: Dict[Type['BaseEvent'], EventType] = {}


# ============================================================
# 事件基类
# ============================================================
@dataclass
class BaseEvent:
    """
    所有事件的基类。

    所有事件均继承此类，提供：
    - timestamp：事件创建时间戳
    - source：事件来源标识
    - event_id：唯一事件 ID

    子类应设置类属性 `event_type` 指定事件类型枚举。
    """

    # 类属性：事件类型（子类覆盖）
    event_type: ClassVar[EventType] = EventType.UNKNOWN

    # 实例字段
    timestamp: float = field(default_factory=time.time)
    source: Optional[str] = None
    event_id: str = field(default_factory=lambda: _generate_event_id())

    def __post_init__(self):
        """注册事件类型（首次实例化时）"""
        cls = self.__class__
        if cls not in _EVENT_TYPE_REGISTRY:
            _EVENT_TYPE_REGISTRY[cls] = cls.event_type

    # --------------------------------------------------------
    # 序列化
    # --------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（用于日志、持久化、跨进程传递）。

        返回:
            包含所有字段的字典
        """
        result = asdict(self)
        result['_event_class'] = self.__class__.__name__
        result['_event_type'] = self.event_type.name
        # 时间戳转 ISO 格式（便于阅读）
        if 'timestamp' in result:
            try:
                result['_timestamp_iso'] = datetime.datetime.fromtimestamp(
                    result['timestamp']
                ).isoformat()
            except Exception:
                pass
        return result

    def to_json(self, indent: int = None) -> str:
        """序列化为 JSON 字符串"""
        return json.dumps(self.to_dict(), indent=indent,
                          ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'BaseEvent':
        """
        从字典反序列化。

        参数:
            d: 事件字典

        返回:
            事件实例
        """
        # 移除辅助字段
        data = {k: v for k, v in d.items() if not k.startswith('_')}

        # 获取所有有效字段
        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}

        return cls(**filtered)

    @classmethod
    def from_json(cls, json_str: str) -> 'BaseEvent':
        """从 JSON 字符串反序列化"""
        return cls.from_dict(json.loads(json_str))

    # --------------------------------------------------------
    # 时间辅助
    # --------------------------------------------------------
    def age_seconds(self) -> float:
        """返回事件创建至今的秒数"""
        return time.time() - self.timestamp

    def timestamp_iso(self) -> str:
        """返回 ISO 格式时间戳"""
        return datetime.datetime.fromtimestamp(self.timestamp).isoformat()

    # --------------------------------------------------------
    # 字符串表示
    # --------------------------------------------------------
    def __str__(self) -> str:
        return self.summary()

    def summary(self) -> str:
        """返回事件摘要（用于日志）"""
        return f"{self.__class__.__name__}@ {self.timestamp_iso()}"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.to_dict()}>"


# ============================================================
# 辅助：生成唯一事件 ID
# ============================================================
_EVENT_COUNTER = 0


def _generate_event_id() -> str:
    """生成唯一的事件 ID"""
    global _EVENT_COUNTER
    _EVENT_COUNTER += 1
    return f"evt_{int(time.time() * 1000)}_{_EVENT_COUNTER}"


# ============================================================
# 文件事件
# ============================================================
@dataclass
class FileEvent(BaseEvent):
    """文件事件基类"""
    event_type: ClassVar[EventType] = EventType.UNKNOWN
    path: str = ""
    encoding: str = "utf-8"


@dataclass
class FileOpenedEvent(FileEvent):
    """文件打开事件"""
    event_type: ClassVar[EventType] = EventType.FILE_OPENED
    size: int = 0
    line_count: int = 0
    is_readonly: bool = False

    def summary(self) -> str:
        return f"打开文件: {self.path} ({self.size} 字节, {self.line_count} 行)"


@dataclass
class FileSavedEvent(FileEvent):
    """文件保存事件"""
    event_type: ClassVar[EventType] = EventType.FILE_SAVED
    size: int = 0
    backup_path: Optional[str] = None
    modified_duration: float = 0.0  # 从修改到保存的秒数

    def summary(self) -> str:
        return f"保存文件: {self.path} ({self.size} 字节)"


@dataclass
class FileClosedEvent(FileEvent):
    """文件关闭事件"""
    event_type: ClassVar[EventType] = EventType.FILE_CLOSED
    was_modified: bool = False
    open_duration: float = 0.0

    def summary(self) -> str:
        modified = " (有未保存修改)" if self.was_modified else ""
        return f"关闭文件: {self.path}{modified}"


@dataclass
class FileModifiedEvent(FileEvent):
    """文件内容修改事件"""
    event_type: ClassVar[EventType] = EventType.FILE_MODIFIED
    modified: bool = True
    change_count: int = 0

    def summary(self) -> str:
        return f"修改文件: {self.path}"


@dataclass
class FileReloadedEvent(FileEvent):
    """文件重新加载事件（外部修改后）"""
    event_type: ClassVar[EventType] = EventType.FILE_RELOADED
    reason: str = ""
    external_change: bool = False

    def summary(self) -> str:
        return f"重新加载: {self.path} ({self.reason})"


@dataclass
class FileEncodingChangedEvent(FileEvent):
    """文件编码变更事件"""
    event_type: ClassVar[EventType] = EventType.FILE_ENCODING_CHANGED
    old_encoding: str = ""
    new_encoding: str = ""

    def summary(self) -> str:
        return (f"编码变更: {self.path} "
                f"{self.old_encoding} → {self.new_encoding}")


# ============================================================
# 编辑器事件
# ============================================================
@dataclass
class EditorEvent(BaseEvent):
    """编辑器事件基类"""
    event_type: ClassVar[EventType] = EventType.UNKNOWN
    editor_id: int = 0
    filepath: Optional[str] = None


@dataclass
class EditorChangedEvent(EditorEvent):
    """当前活动编辑器变更"""
    event_type: ClassVar[EventType] = EventType.EDITOR_CHANGED
    old_editor_id: int = 0

    def summary(self) -> str:
        return f"切换编辑器: {self.filepath or '(未命名)'}"


@dataclass
class EditorFocusedEvent(EditorEvent):
    """编辑器获得焦点"""
    event_type: ClassVar[EventType] = EventType.EDITOR_FOCUSED


@dataclass
class EditorCreatedEvent(EditorEvent):
    """新编辑器创建"""
    event_type: ClassVar[EventType] = EventType.EDITOR_CREATED


@dataclass
class EditorDestroyedEvent(EditorEvent):
    """编辑器销毁"""
    event_type: ClassVar[EventType] = EventType.EDITOR_DESTROYED


# ============================================================
# 光标与选区事件
# ============================================================
@dataclass
class CursorEvent(BaseEvent):
    """光标位置事件"""
    event_type: ClassVar[EventType] = EventType.CURSOR_MOVED
    line: int = 0            # 1 开始
    col: int = 0             # 0 开始
    position: int = 0        # 字符偏移
    editor_id: int = 0
    filepath: Optional[str] = None

    def summary(self) -> str:
        return f"光标: 行 {self.line}, 列 {self.col}"


@dataclass
class SelectionEvent(BaseEvent):
    """选区变更事件"""
    event_type: ClassVar[EventType] = EventType.SELECTION_CHANGED
    start: int = 0
    end: int = 0
    text: str = ""
    line_count: int = 0
    char_count: int = 0
    editor_id: int = 0

    def summary(self) -> str:
        return f"选区: {self.char_count} 字符, {self.line_count} 行"


# ============================================================
# 文本编辑事件
# ============================================================
@dataclass
class TextEditEvent(BaseEvent):
    """文本编辑事件基类"""
    event_type: ClassVar[EventType] = EventType.UNKNOWN
    position: int = 0
    text: str = ""
    length: int = 0
    editor_id: int = 0
    filepath: Optional[str] = None


@dataclass
class TextInsertedEvent(TextEditEvent):
    """文本插入事件"""
    event_type: ClassVar[EventType] = EventType.TEXT_INSERTED

    def summary(self) -> str:
        preview = self.text[:30].replace('\n', '\\n')
        return f"插入: '{preview}' @ {self.position}"


@dataclass
class TextDeletedEvent(TextEditEvent):
    """文本删除事件"""
    event_type: ClassVar[EventType] = EventType.TEXT_DELETED

    def summary(self) -> str:
        return f"删除: {self.length} 字符 @ {self.position}"


@dataclass
class TextReplacedEvent(TextEditEvent):
    """文本替换事件"""
    event_type: ClassVar[EventType] = EventType.TEXT_REPLACED
    old_text: str = ""

    def summary(self) -> str:
        return (f"替换: '{self.old_text[:15]}' → "
                f"'{self.text[:15]}' @ {self.position}")


# ============================================================
# 撤销/重做事件
# ============================================================
@dataclass
class UndoEvent(BaseEvent):
    """撤销事件"""
    event_type: ClassVar[EventType] = EventType.UNDO_PERFORMED
    command_count: int = 0
    undo_stack_size: int = 0
    editor_id: int = 0

    def summary(self) -> str:
        return f"撤销 (剩余 {self.undo_stack_size} 步)"


@dataclass
class RedoEvent(BaseEvent):
    """重做事件"""
    event_type: ClassVar[EventType] = EventType.REDO_PERFORMED
    command_count: int = 0
    redo_stack_size: int = 0
    editor_id: int = 0

    def summary(self) -> str:
        return f"重做 (剩余 {self.redo_stack_size} 步)"


# ============================================================
# 搜索事件
# ============================================================
@dataclass
class SearchEvent(BaseEvent):
    """搜索事件基类"""
    event_type: ClassVar[EventType] = EventType.UNKNOWN
    pattern: str = ""
    is_regex: bool = False
    case_sensitive: bool = False
    whole_word: bool = False
    scope: str = "current"  # current / project / all


@dataclass
class SearchStartedEvent(SearchEvent):
    """搜索开始"""
    event_type: ClassVar[EventType] = EventType.SEARCH_STARTED
    # B1a: scope 字段（event_bus 独有）
    scope: str = "current"
    directory: str = ""
    file_filter: str = "*.*"

    def summary(self) -> str:
        return f"搜索开始: '{self.pattern}' ({self.scope})"


@dataclass
class SearchFinishedEvent(SearchEvent):
    """搜索结束"""
    event_type: ClassVar[EventType] = EventType.SEARCH_FINISHED
    match_count: int = 0
    file_count: int = 0
    elapsed_ms: float = 0.0
    cancelled: bool = False

    def summary(self) -> str:
        status = "已取消" if self.cancelled else "完成"
        return (f"搜索{status}: '{self.pattern}' "
                f"({self.match_count} 个匹配, {self.elapsed_ms:.0f} ms)")


@dataclass
class SearchResultEvent(SearchEvent):
    """单条搜索结果"""
    event_type: ClassVar[EventType] = EventType.SEARCH_RESULT
    filepath: str = ""
    line: int = 0
    col: int = 0
    text: str = ""

    def summary(self) -> str:
        return f"匹配: {self.filepath}:{self.line}:{self.col}"


# ============================================================
# 标签事件
# ============================================================
@dataclass
class TabEvent(BaseEvent):
    """标签事件基类"""
    event_type: ClassVar[EventType] = EventType.UNKNOWN
    index: int = 0
    title: str = ""
    filepath: Optional[str] = None


@dataclass
class TabChangedEvent(TabEvent):
    """当前标签切换"""
    event_type: ClassVar[EventType] = EventType.TAB_CHANGED
    old_index: int = -1
    old_title: str = ""

    def summary(self) -> str:
        return f"切换标签: {self.old_index} → {self.index} ({self.title})"


@dataclass
class TabAddedEvent(TabEvent):
    """标签新增"""
    event_type: ClassVar[EventType] = EventType.TAB_ADDED

    def summary(self) -> str:
        return f"新增标签: {self.title}"


@dataclass
class TabRemovedEvent(TabEvent):
    """标签关闭"""
    event_type: ClassVar[EventType] = EventType.TAB_REMOVED

    def summary(self) -> str:
        return f"关闭标签: {self.title}"


# ============================================================
# 项目事件
# ============================================================
@dataclass
class ProjectEvent(BaseEvent):
    """项目事件基类"""
    event_type: ClassVar[EventType] = EventType.UNKNOWN
    root_path: str = ""
    project_name: str = ""


@dataclass
class ProjectOpenedEvent(ProjectEvent):
    """项目打开"""
    event_type: ClassVar[EventType] = EventType.PROJECT_OPENED
    file_count: int = 0

    def summary(self) -> str:
        return f"打开项目: {self.project_name} ({self.root_path})"


@dataclass
class ProjectClosedEvent(ProjectEvent):
    """项目关闭"""
    event_type: ClassVar[EventType] = EventType.PROJECT_CLOSED

    def summary(self) -> str:
        return f"关闭项目: {self.project_name}"


@dataclass
class ProjectFileEvent(ProjectEvent):
    """项目文件变更事件基类"""
    event_type: ClassVar[EventType] = EventType.UNKNOWN
    filepath: str = ""
    action: str = ""  # add / remove / rename


@dataclass
class ProjectFileAddedEvent(ProjectFileEvent):
    """项目文件新增"""
    event_type: ClassVar[EventType] = EventType.PROJECT_FILE_ADDED

    def summary(self) -> str:
        return f"项目新增文件: {self.filepath}"


@dataclass
class ProjectFileRemovedEvent(ProjectFileEvent):
    """项目文件移除"""
    event_type: ClassVar[EventType] = EventType.PROJECT_FILE_REMOVED

    def summary(self) -> str:
        return f"项目移除文件: {self.filepath}"


@dataclass
class ProjectFileRenamedEvent(ProjectFileEvent):
    """项目文件重命名"""
    event_type: ClassVar[EventType] = EventType.PROJECT_FILE_RENAMED
    old_path: str = ""

    def summary(self) -> str:
        return f"项目重命名: {self.old_path} → {self.filepath}"


# ============================================================
# 宏事件
# ============================================================
@dataclass
class MacroEvent(BaseEvent):
    """宏事件基类"""
    event_type: ClassVar[EventType] = EventType.UNKNOWN
    command_count: int = 0


@dataclass
class MacroStartedEvent(MacroEvent):
    """宏录制开始"""
    event_type: ClassVar[EventType] = EventType.MACRO_STARTED
    macro_name: str = ""

    def summary(self) -> str:
        return f"宏录制开始: {self.macro_name or '(未命名)'}"


@dataclass
class MacroStoppedEvent(MacroEvent):
    """宏录制停止"""
    event_type: ClassVar[EventType] = EventType.MACRO_STOPPED
    macro_name: str = ""
    duration_seconds: float = 0.0

    def summary(self) -> str:
        return (f"宏录制停止: {self.macro_name or '(未命名)'} "
                f"({self.command_count} 条命令, {self.duration_seconds:.1f}s)")


@dataclass
class MacroReplayedEvent(MacroEvent):
    """宏回放"""
    event_type: ClassVar[EventType] = EventType.MACRO_REPLAYED
    macro_name: str = ""
    elapsed_ms: float = 0.0

    def summary(self) -> str:
        return (f"宏回放: {self.macro_name or '(未命名)'} "
                f"({self.command_count} 条命令, {self.elapsed_ms:.0f} ms)")


# ============================================================
# 插件事件
# ============================================================
@dataclass
class PluginEvent(BaseEvent):
    """插件事件基类"""
    event_type: ClassVar[EventType] = EventType.UNKNOWN
    plugin_name: str = ""
    version: str = ""


@dataclass
class PluginLoadedEvent(PluginEvent):
    """插件加载成功"""
    event_type: ClassVar[EventType] = EventType.PLUGIN_LOADED
    load_time_ms: float = 0.0

    def summary(self) -> str:
        return f"插件加载: {self.plugin_name} v{self.version}"


@dataclass
class PluginUnloadedEvent(PluginEvent):
    """插件卸载"""
    event_type: ClassVar[EventType] = EventType.PLUGIN_UNLOADED

    def summary(self) -> str:
        return f"插件卸载: {self.plugin_name}"


@dataclass
class PluginErrorEvent(PluginEvent):
    """插件错误"""
    event_type: ClassVar[EventType] = EventType.PLUGIN_ERROR
    error_type: str = ""
    error_message: str = ""
    traceback: str = ""

    def summary(self) -> str:
        return f"插件错误: {self.plugin_name} - {self.error_message}"


# ============================================================
# 主题事件
# ============================================================
@dataclass
class ThemeEvent(BaseEvent):
    """主题变更事件"""
    event_type: ClassVar[EventType] = EventType.THEME_CHANGED
    old_theme: str = ""
    new_theme: str = ""
    theme_path: str = ""

    def summary(self) -> str:
        return f"主题切换: {self.old_theme} → {self.new_theme}"


# ============================================================
# 应用事件
# ============================================================
@dataclass
class AppEvent(BaseEvent):
    """应用事件基类"""
    event_type: ClassVar[EventType] = EventType.UNKNOWN


@dataclass
class AppReadyEvent(AppEvent):
    """应用就绪"""
    event_type: ClassVar[EventType] = EventType.APP_READY
    startup_time_ms: float = 0.0
    plugin_count: int = 0
    version: str = ""

    def summary(self) -> str:
        return f"应用就绪 ({self.startup_time_ms:.0f} ms)"


@dataclass
class AppClosingEvent(AppEvent):
    """应用即将关闭"""
    event_type: ClassVar[EventType] = EventType.APP_CLOSING
    open_file_count: int = 0
    modified_count: int = 0
    uptime_seconds: float = 0.0

    def summary(self) -> str:
        return (f"应用关闭 (运行 {self.uptime_seconds:.0f}s, "
                f"{self.open_file_count} 个文件, "
                f"{self.modified_count} 个未保存)")


# ============================================================
# 状态与通知事件
# ============================================================
@dataclass
class StatusMessageEvent(BaseEvent):
    """状态栏消息事件"""
    event_type: ClassVar[EventType] = EventType.STATUS_MESSAGE
    message: str = ""
    timeout: int = 3000
    level: str = "info"  # info / warning / error / success

    def summary(self) -> str:
        return f"状态: {self.message}"


@dataclass
class NotificationEvent(BaseEvent):
    """通知事件（可显示气泡）"""
    event_type: ClassVar[EventType] = EventType.NOTIFICATION
    title: str = ""
    message: str = ""
    level: str = "info"
    actions: List[str] = field(default_factory=list)
    duration: int = 5000  # 毫秒

    def summary(self) -> str:
        return f"通知: [{self.level}] {self.title} - {self.message}"


# ============================================================
# 事件工厂
# ============================================================
class EventFactory:
    """
    事件工厂。

    根据事件类名或事件类型枚举创建事件对象。
    支持动态注册自定义事件。
    """

    _by_class_name: Dict[str, Type[BaseEvent]] = {}
    _by_event_type: Dict[EventType, Type[BaseEvent]] = {}

    @classmethod
    def register(cls, event_class: Type[BaseEvent]):
        """注册事件类型"""
        cls._by_class_name[event_class.__name__] = event_class
        if event_class.event_type != EventType.UNKNOWN:
            cls._by_event_type[event_class.event_type] = event_class

    @classmethod
    def create(cls, class_name: str, **kwargs) -> Optional[BaseEvent]:
        """根据类名创建事件"""
        event_class = cls._by_class_name.get(class_name)
        if event_class is None:
            return None
        return event_class(**kwargs)

    @classmethod
    def create_from_dict(cls, d: Dict[str, Any]) -> Optional[BaseEvent]:
        """从字典创建（自动识别类型）"""
        class_name = d.get('_event_class')
        if not class_name:
            return None
        return cls.create(class_name, **{
            k: v for k, v in d.items() if not k.startswith('_')
        })

    @classmethod
    def list_event_classes(cls) -> List[str]:
        """列出所有已注册的事件类名"""
        return list(cls._by_class_name.keys())

    @classmethod
    def get_event_class(cls, event_type: EventType) -> Optional[Type[BaseEvent]]:
        """根据事件类型获取事件类"""
        return cls._by_event_type.get(event_type)


# ============================================================
# 自动注册所有事件类
# ============================================================
_ALL_EVENT_CLASSES = [
    # 文件
    FileOpenedEvent, FileSavedEvent, FileClosedEvent,
    FileModifiedEvent, FileReloadedEvent, FileEncodingChangedEvent,
    # 编辑器
    EditorChangedEvent, EditorFocusedEvent,
    EditorCreatedEvent, EditorDestroyedEvent,
    # 光标与选区
    CursorEvent, SelectionEvent,
    # 文本编辑
    TextInsertedEvent, TextDeletedEvent, TextReplacedEvent,
    # 撤销重做
    UndoEvent, RedoEvent,
    # 搜索
    SearchStartedEvent, SearchFinishedEvent, SearchResultEvent,
    # 标签
    TabChangedEvent, TabAddedEvent, TabRemovedEvent,
    # 项目
    ProjectOpenedEvent, ProjectClosedEvent,
    ProjectFileAddedEvent, ProjectFileRemovedEvent, ProjectFileRenamedEvent,
    # 宏
    MacroStartedEvent, MacroStoppedEvent, MacroReplayedEvent,
    # 插件
    PluginLoadedEvent, PluginUnloadedEvent, PluginErrorEvent,
    # 主题
    ThemeEvent,
    # 应用
    AppReadyEvent, AppClosingEvent,
    # 状态与通知
    StatusMessageEvent, NotificationEvent,
]

for _cls in _ALL_EVENT_CLASSES:
    EventFactory.register(_cls)


# ============================================================
# 辅助函数
# ============================================================
def event_to_dict(event: BaseEvent) -> Dict[str, Any]:
    """事件转字典（便捷函数）"""
    if event is None:
        return {}
    return event.to_dict()


def event_from_dict(d: Dict[str, Any]) -> Optional[BaseEvent]:
    """从字典创建事件（便捷函数）"""
    return EventFactory.create_from_dict(d)


def event_to_json(event: BaseEvent, indent: int = None) -> str:
    """事件转 JSON"""
    if event is None:
        return "{}"
    return event.to_json(indent)


def event_from_json(json_str: str) -> Optional[BaseEvent]:
    """从 JSON 创建事件"""
    try:
        d = json.loads(json_str)
        return EventFactory.create_from_dict(d)
    except Exception:
        return None


def is_file_event(event: BaseEvent) -> bool:
    """判断是否为文件事件"""
    return isinstance(event, FileEvent)


def is_editor_event(event: BaseEvent) -> bool:
    """判断是否为编辑器事件"""
    return isinstance(event, (EditorEvent, CursorEvent, SelectionEvent,
                              TextEditEvent, UndoEvent, RedoEvent))


def is_search_event(event: BaseEvent) -> bool:
    """判断是否为搜索事件"""
    return isinstance(event, SearchEvent)


def is_project_event(event: BaseEvent) -> bool:
    """判断是否为项目事件"""
    return isinstance(event, ProjectEvent)


def is_plugin_event(event: BaseEvent) -> bool:
    """判断是否为插件事件"""
    return isinstance(event, PluginEvent)


def get_event_type(event: BaseEvent) -> EventType:
    """获取事件类型（更安全的访问）"""
    if event is None:
        return EventType.UNKNOWN
    return event.event_type


def event_matches(event: BaseEvent, event_type: EventType) -> bool:
    """判断事件是否匹配指定类型"""
    return event is not None and event.event_type == event_type


def filter_events_by_type(events: List[BaseEvent],
                          event_type: EventType) -> List[BaseEvent]:
    """按类型过滤事件列表"""
    return [e for e in events if e.event_type == event_type]


def filter_events_by_class(events: List[BaseEvent],
                           event_class: Type[BaseEvent]) -> List[BaseEvent]:
    """按类过滤事件列表"""
    return [e for e in events if isinstance(e, event_class)]


def events_summary(events: List[BaseEvent],
                   limit: Optional[int] = None) -> str:
    """
    生成事件列表的摘要文本。

    参数:
        events: 事件列表
        limit: 最多显示条数

    返回:
        摘要字符串
    """
    if not events:
        return "（无事件）"

    total = len(events)
    display = events[-limit:] if limit else events

    lines = [f"事件摘要（共 {total} 条）", "=" * 60]
    for event in display:
        ts = datetime.datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S")
        lines.append(f"  [{ts}] {event.summary()}")

    if limit and total > limit:
        lines.append(f"  ... 及其他 {total - limit} 条")

    return "\n".join(lines)


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    print("=== 测试事件创建 ===")

    # 创建文件打开事件
    event = FileOpenedEvent(
        path="/home/user/test.py",
        size=1024,
        line_count=50,
        encoding="utf-8",
        is_readonly=False,
        source="test"
    )
    print(f"事件: {event}")
    print(f"摘要: {event.summary()}")
    print(f"类型: {event.event_type.name}")
    print(f"事件 ID: {event.event_id}")
    print()

    # 测试序列化
    print("=== 测试序列化 ===")
    d = event.to_dict()
    print(f"字典键: {sorted(d.keys())}")
    print(f"JSON 长度: {len(event.to_json())} 字符")

    restored = BaseEvent.from_dict(d)
    print(f"恢复事件: {restored.summary()}")
    print()

    # 测试事件工厂
    print("=== 测试事件工厂 ===")
    event2 = EventFactory.create("FileSavedEvent",
                                  path="/tmp/a.py", size=100)
    print(f"工厂创建: {event2.summary()}")

    restored2 = EventFactory.create_from_dict(event2.to_dict())
    print(f"从字典恢复: {restored2.summary()}")
    print(f"已注册事件类: {len(EventFactory.list_event_classes())}")
    print()

    # 测试不同类型的事件
    print("=== 测试各类型事件 ===")
    events = [
        CursorEvent(line=10, col=5, position=200),
        SelectionEvent(text="hello", char_count=5, line_count=1),
        TextInsertedEvent(position=0, text="Hello World"),
        TextDeletedEvent(position=10, length=5),
        UndoEvent(command_count=1, undo_stack_size=10),
        RedoEvent(command_count=1, redo_stack_size=2),
        SearchStartedEvent(pattern="test", is_regex=True),
        SearchFinishedEvent(pattern="test", match_count=15, elapsed_ms=250.0),
        TabChangedEvent(index=1, old_index=0, title="test.py"),
        TabAddedEvent(index=2, title="new.py"),
        MacroStartedEvent(command_count=0, macro_name="test_macro"),
        MacroStoppedEvent(command_count=5, macro_name="test_macro"),
        PluginLoadedEvent(plugin_name="markdown", version="1.0.0"),
        PluginErrorEvent(plugin_name="bad", error_message="加载失败"),
        ThemeEvent(old_theme="dark", new_theme="light"),
        AppReadyEvent(startup_time_ms=800, version="2.0.0"),
        StatusMessageEvent(message="文件已保存", level="success"),
        NotificationEvent(title="提示", message="这是一条通知"),
    ]

    for e in events:
        print(f"  {e.event_type.name:25s} {e.summary()}")
    print()

    # 测试类型过滤
    print("=== 测试类型过滤 ===")
    file_events = filter_events_by_class(events, FileEvent)
    print(f"文件事件数: {len(file_events)}")

    editor_events = filter_events_by_class(events, EditorEvent)
    print(f"编辑器事件数: {len(editor_events)}")

    text_events = filter_events_by_class(events, TextEditEvent)
    print(f"文本编辑事件数: {len(text_events)}")
    print()

    # 测试 JSON 序列化与反序列化
    print("=== 测试 JSON 往返 ===")
    for e in events[:3]:
        json_str = e.to_json()
        restored = event_from_json(json_str)
        if restored:
            print(f"  OK: {restored.summary()}")
        else:
            print(f"  FAIL: {e.summary()}")
    print()

    # 生成摘要
    print("=== 事件列表摘要 ===")
    print(events_summary(events, limit=10))
    print()

    # 测试辅助判断
    print("=== 测试辅助函数 ===")
    test_event = FileOpenedEvent(path="/test.py")
    print(f"是否文件事件: {is_file_event(test_event)}")
    print(f"是否编辑器事件: {is_editor_event(test_event)}")
    print(f"事件类型: {get_event_type(test_event).name}")
    print(f"匹配 FILE_OPENED: {event_matches(test_event, EventType.FILE_OPENED)}")
    print()

    print(f"事件年龄: {test_event.age_seconds():.4f} 秒")
    print(f"时间戳 ISO: {test_event.timestamp_iso()}")

    print()
    print("测试完成。")