#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为宏录制与回放模块，包含：
- MacroRecorder：宏录制器
- Macro：单个宏对象
- MacroManager：宏管理器（多宏管理）
- MacroCommand：宏命令封装
- 录制开始/停止
- 命令记录与合并
- 回放与批量执行
- 循环回放与条件回放
- 宏保存/加载（JSON 格式）
- 宏编辑器支持
- 宏快捷键绑定
- 宏元数据（名称、描述、创建时间）
- 宏统计信息
- 回放进度与取消
- 回放时禁用事件通知
- 命令对象复用
"""

import datetime
import json
import os
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QApplication, QProgressDialog

from app.event_bus import (
    MacroReplayedEvent,
    MacroStartedEvent,
    MacroStoppedEvent,
    StatusMessageEvent,
    bus,
)
from core.commands import (
    MERGE_INTERVAL_MS,
    Command,
    CommandFactory,
    CommandSerializer,
    DeleteCmd,
    GroupCmd,
    InsertCmd,
    ReplaceCmd,
    merge_commands,
)


# ============================================================
# 常量
# ============================================================
# 宏文件格式版本
MACRO_FORMAT_VERSION = 2

# 默认宏文件扩展名
MACRO_FILE_EXT = ".qingcao-macro.json"

# 宏目录
MACROS_DIR = "macros"

# 单次回放最大命令数（防止死循环）
MAX_REPLAY_COMMANDS = 1000000

# 回放进度更新间隔（毫秒）
REPLAY_PROGRESS_INTERVAL = 100

# 命令合并时间窗口（毫秒）
DEFAULT_MERGE_INTERVAL = 200


# ============================================================
# 宏状态枚举
# ============================================================
class MacroState(Enum):
    """宏状态"""
    IDLE = auto()       # 空闲
    RECORDING = auto()  # 录制中
    PLAYING = auto()    # 回放中
    ERROR = auto()      # 错误


# ============================================================
# 宏命令封装
# ============================================================
@dataclass
class MacroCommand:
    """
    宏命令。

    对 Command 对象的封装，附带时间偏移（相对于宏开始）。
    """

    command_data: Dict[str, Any]  # 序列化的命令
    timestamp_offset: float = 0.0  # 相对于宏开始的时间偏移（秒）

    def to_dict(self) -> Dict[str, Any]:
        return {
            'command': self.command_data,
            'offset': self.timestamp_offset,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'MacroCommand':
        return cls(
            command_data=d.get('command', {}),
            timestamp_offset=d.get('offset', 0.0),
        )


# ============================================================
# 宏对象
# ============================================================
@dataclass
class Macro:
    """
    单个宏对象。

    包含宏的所有数据和元信息。
    """

    name: str = "未命名宏"
    description: str = ""
    version: int = MACRO_FORMAT_VERSION
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now().isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.datetime.now().isoformat()
    )
    author: str = ""
    tags: List[str] = field(default_factory=list)

    # 命令列表
    commands: List[MacroCommand] = field(default_factory=list)

    # 快捷键绑定
    shortcut: str = ""

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    # --------------------------------------------------------
    # 属性
    # --------------------------------------------------------
    @property
    def command_count(self) -> int:
        return len(self.commands)

    @property
    def is_empty(self) -> bool:
        return len(self.commands) == 0

    # --------------------------------------------------------
    # 添加命令
    # --------------------------------------------------------
    def add_command(self, command: Command, offset: float = 0.0):
        """添加一条命令"""
        macro_cmd = MacroCommand(
            command_data=command.to_dict(),
            timestamp_offset=offset,
        )
        self.commands.append(macro_cmd)
        self.updated_at = datetime.datetime.now().isoformat()

    def add_macro_command(self, macro_cmd: MacroCommand):
        """添加宏命令对象"""
        self.commands.append(macro_cmd)
        self.updated_at = datetime.datetime.now().isoformat()

    def clear(self):
        """清空命令"""
        self.commands.clear()
        self.updated_at = datetime.datetime.now().isoformat()

    # --------------------------------------------------------
    # 序列化
    # --------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'description': self.description,
            'version': self.version,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'author': self.author,
            'tags': list(self.tags),
            'shortcut': self.shortcut,
            'metadata': dict(self.metadata),
            'command_count': self.command_count,
            'commands': [c.to_dict() for c in self.commands],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Macro':
        macro = cls(
            name=d.get('name', '未命名宏'),
            description=d.get('description', ''),
            version=d.get('version', MACRO_FORMAT_VERSION),
            created_at=d.get('created_at', ''),
            updated_at=d.get('updated_at', ''),
            author=d.get('author', ''),
            tags=list(d.get('tags', [])),
            shortcut=d.get('shortcut', ''),
            metadata=dict(d.get('metadata', {})),
        )
        for cmd_data in d.get('commands', []):
            macro.commands.append(MacroCommand.from_dict(cmd_data))
        return macro

    def save(self, filepath: str) -> bool:
        """保存到文件"""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)) or '.',
                        exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[Macro] 保存失败: {e}")
            return False

    @classmethod
    def load(cls, filepath: str) -> Optional['Macro']:
        """从文件加载"""
        try:
            with open(filepath, encoding='utf-8') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            print(f"[Macro] 加载失败: {e}")
            return None

    def __repr__(self) -> str:
        return (f"<Macro name={self.name!r} "
                f"commands={self.command_count}>")


# ============================================================
# 宏录制器
# ============================================================
class MacroRecorder(QObject):
    """
    宏录制器。

    监听编辑器的命令记录回调，将命令序列保存为宏。
    支持：
    - 开始/停止录制
    - 命令合并
    - 录制计数
    - 录制时长
    - 录制后保存为宏
    - 快捷键绑定

    信号:
        recording_started(): 开始录制
        recording_stopped(int): 停止录制（命令数量）
        command_recorded(int): 记录一条命令（累计数量）
        macro_saved(str): 宏已保存（文件路径）
        error_occurred(str): 错误
    """

    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal(int)
    command_recorded = pyqtSignal(int)
    macro_saved = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, undo_manager=None, parent: Optional[QObject] = None):
        """
        参数:
            undo_manager: 撤销管理器（用于注册命令记录回调）
            parent: 父 QObject
        """
        super().__init__(parent)

        self.undo_manager = undo_manager

        # 状态
        self._state: MacroState = MacroState.IDLE
        self._recording: bool = False

        # 当前宏
        self.current_macro: Macro = Macro()

        # 录制时间
        self._start_time: float = 0.0
        self._last_command_time: float = 0.0

        # 命令计数
        self._command_count: int = 0

        # 是否启用命令合并
        self.merge_enabled: bool = True
        self.merge_interval_ms: int = DEFAULT_MERGE_INTERVAL

        # 保留原始的 record_hook（用于链式调用）
        self._original_hook: Optional[Callable] = None

    # --------------------------------------------------------
    # 属性
    # --------------------------------------------------------
    @property
    def state(self) -> MacroState:
        return self._state

    @property
    def recording(self) -> bool:
        """是否正在录制"""
        return self._recording

    @property
    def command_count(self) -> int:
        """当前录制的命令数量"""
        return self._command_count

    @property
    def duration(self) -> float:
        """录制时长（秒）"""
        if self._start_time <= 0:
            return 0.0
        return time.time() - self._start_time

    # --------------------------------------------------------
    # 开始/停止录制
    # --------------------------------------------------------
    def start(self, name: str = "", clear: bool = True):
        """
        开始录制宏。

        参数:
            name: 宏名称（留空则自动生成）
            clear: 是否清空当前宏
        """
        if self._recording:
            return

        # 初始化宏
        if clear or self.current_macro.is_empty:
            if not name:
                name = self._generate_macro_name()
            self.current_macro = Macro(
                name=name,
                author=self._get_default_author(),
            )

        # 重置时间
        # 修复 B3：_last_command_time 统一为 offset
        # （相对 _start_time 的秒数），而不是绝对时间戳。
        # 原实现初始化为 _start_time（绝对），而比较时用 offset
        # （相对），永远为负，导致所有连续命令被合并。
        self._start_time = time.time()
        self._last_command_time = 0.0
        self._command_count = 0

        # 设置状态
        self._recording = True
        self._state = MacroState.RECORDING

        # 注册命令记录回调
        self._register_hook()

        # 发射信号
        self.recording_started.emit()
        self.command_recorded.emit(0)

        # 事件总线
        try:
            bus.emit_event(MacroStartedEvent(
                command_count=0,
                macro_name=self.current_macro.name,
            ))
        except Exception:
            pass

    def stop(self) -> Macro:
        """
        停止录制。

        返回:
            录制的宏对象
        """
        if not self._recording:
            return self.current_macro

        # 更新状态
        self._recording = False
        self._state = MacroState.IDLE

        # 计算时长
        duration = time.time() - self._start_time

        # 取消注册回调
        self._unregister_hook()

        # 更新宏元数据
        self.current_macro.updated_at = datetime.datetime.now().isoformat()
        self.current_macro.metadata['duration'] = round(duration, 3)
        self.current_macro.metadata['recorded_at'] = (
            datetime.datetime.now().isoformat()
        )

        # 发射信号
        self.recording_stopped.emit(self._command_count)

        # 事件总线
        try:
            bus.emit_event(MacroStoppedEvent(
                command_count=self._command_count,
                macro_name=self.current_macro.name,
                duration_seconds=duration,
            ))
        except Exception:
            pass

        return self.current_macro

    def toggle(self):
        """切换录制状态"""
        if self._recording:
            self.stop()
        else:
            self.start()

    def cancel(self):
        """取消录制并清空当前宏"""
        if self._recording:
            self._recording = False
            self._state = MacroState.IDLE
            self._unregister_hook()

        self.current_macro.clear()
        self._command_count = 0

    # --------------------------------------------------------
    # 命令记录回调
    # --------------------------------------------------------
    def _register_hook(self):
        """注册命令记录回调到 undo_manager"""
        if not self.undo_manager:
            return

        # 保存原始回调（可能被其他模块使用）
        self._original_hook = getattr(self.undo_manager, 'record_hook', None)

        # 注册我们的回调
        def combined_hook(command):
            # 先调用原始回调
            if self._original_hook:
                try:
                    self._original_hook(command)
                except Exception:
                    pass

            # 再记录到宏
            self._on_command_recorded(command)

        self.undo_manager.record_hook = combined_hook

    def _unregister_hook(self):
        """取消注册"""
        if not self.undo_manager:
            return

        # 恢复原始回调
        self.undo_manager.record_hook = self._original_hook

    def _on_command_recorded(self, command: Command):
        """
        命令记录回调。

        参数:
            command: 记录的命令对象
        """
        if not self._recording:
            return

        try:
            # 计算时间偏移
            now = time.time()
            offset = now - self._start_time

            # 检查是否需要合并
            if (self.merge_enabled and
                    self.current_macro.commands and
                    offset - self._last_command_time < self.merge_interval_ms / 1000.0):

                # 尝试与上一条命令合并
                last_macro_cmd = self.current_macro.commands[-1]

                try:
                    last_cmd = Command.from_dict(last_macro_cmd.command_data)
                    if last_cmd.can_merge(command):
                        merged = last_cmd.merge_with(command)
                        if merged is not None:
                            # 更新最后一条命令
                            last_macro_cmd.command_data = merged.to_dict()
                            self._last_command_time = offset
                            return
                except Exception:
                    pass

            # 添加新命令
            self.current_macro.add_command(command, offset)
            self._command_count += 1
            self._last_command_time = offset

            # 发射信号
            self.command_recorded.emit(self._command_count)

        except Exception as e:
            self.error_occurred.emit(f"记录命令失败: {e}")

    # --------------------------------------------------------
    # 回放
    # --------------------------------------------------------
    def replay(self, proxy, macro: Optional[Macro] = None,
               repeat: int = 1, show_progress: bool = True,
               check_cancel: bool = True) -> bool:
        """
        回放宏。

        参数:
            proxy: 编辑器代理
            macro: 要回放的宏（None 则使用当前宏）
            repeat: 重复次数
            show_progress: 是否显示进度对话框
            check_cancel: 是否允许取消

        返回:
            是否成功完成
        """
        if macro is None:
            macro = self.current_macro

        if macro.is_empty:
            self.error_occurred.emit("宏为空")
            return False

        if proxy is None or not hasattr(proxy, 'sc'):
            self.error_occurred.emit("编辑器代理无效")
            return False

        # 检查命令数量
        total_commands = len(macro.commands) * repeat
        if total_commands > MAX_REPLAY_COMMANDS:
            self.error_occurred.emit(
                f"回放命令数量过多 ({total_commands})"
            )
            return False

        # 记录状态
        old_state = self._state
        self._state = MacroState.PLAYING

        # 保存旧的 record_hook 并禁用录制
        was_recording = self._recording
        if was_recording:
            self._unregister_hook()

        start_time = time.time()

        # 回放前的缓冲区快照
        #
        # 用途见下方"写入单条整体回滚命令"：回放期间关闭了 Scintilla 通知
        # （性能考虑），`_on_scintilla_modified` 收不到事件，自研撤销栈
        # 不会有任何回放命令 —— 若不管，Ctrl+Z 会弹出回放**之前**的旧命令
        # 并按旧位置执行，直接损坏内容。
        text_before_replay = ""
        try:
            text_before_replay = proxy.sc.text()
        except Exception:
            pass

        try:
            # 禁用 Scintilla 通知（提高性能）
            self._disable_scintilla_notifications(proxy)

            # 进度对话框
            progress = None
            if show_progress and total_commands > 100:
                progress = QProgressDialog(
                    "正在回放宏...", "取消", 0, repeat, None
                )
                progress.setWindowModality(Qt.WindowModal)
                progress.setMinimumDuration(300)
                progress.show()

            # 执行回放
            cancelled = False
            executed = 0

            for r in range(repeat):
                if check_cancel and progress and progress.wasCanceled():
                    cancelled = True
                    break

                # 回放单次
                for macro_cmd in macro.commands:
                    try:
                        cmd = Command.from_dict(macro_cmd.command_data)
                        cmd.execute(proxy.sc)
                        executed += 1
                    except Exception as e:
                        print(f"[Macro] 回放命令失败: {e}")

                # 更新进度
                if progress:
                    progress.setValue(r + 1)
                    QApplication.processEvents()

            # 关闭进度
            if progress:
                progress.close()

            elapsed = (time.time() - start_time) * 1000

            # 标记修改
            #
            # 修复（INV-M3，审计用例复现）：原先只改 `proxy._modified`，
            # 不调用 `document.mark_modified()` —— 于是
            # `proxy.is_modified` 与 `document.is_modified` 出现分歧
            # （标签页显示 '*' 但文档认为干净，自动保存/关闭提示据此误判）。
            proxy.sc.setModified(True)
            if hasattr(proxy, '_modified'):
                proxy._modified = True
            try:
                doc = getattr(proxy, 'document', None)
                if doc is not None and hasattr(doc, 'mark_modified'):
                    doc.mark_modified()
            except Exception:
                pass
            if hasattr(proxy, 'modified_changed'):
                try:
                    proxy.modified_changed.emit(True)
                except Exception:
                    pass

            # 写入一条**整体回滚命令**，让一次 Ctrl+Z 回到回放前
            #
            # 修复（INV-M1/INV-M2，审计用例复现）：
            #   回放用 `SCI_SETMODEVENTMASK(0)` 关闭了修改通知（第 577 行），
            #   `EditorProxy._on_scintilla_modified` 因此不会触发，
            #   `UndoManager.record()` 从未被调用 —— 回放改变了缓冲区却
            #   在撤销栈里**没有任何记录**。于是用户按 Ctrl+Z 时弹出的是
            #   回放**之前**的旧命令，按旧位置执行 → 内容损坏且不可预期。
            #
            #   这里把"回放前 → 回放后"的整段变化作为**一个原子命令**补记
            #   进撤销栈：undo 恢复回放前的全文，redo 恢复回放后的全文。
            #   使用 `CompoundCmd`（带显式逆操作），它能被 UndoManager
            #   正确 undo/redo（不像 GroupCmd 那样在 redo 时会再次执行正向）。
            try:
                if executed and text_before_replay != proxy.sc.text():
                    from core.commands import CompoundCmd as _Compound

                    text_after = proxy.sc.text()

                    def _restore(text):
                        def _fn(sc):
                            # 注意：不能用 `SCI_SETTEXT` + str —— 该消息的
                            # lParam 需要 bytes，传 str 会抛
                            # "argument 3 has unexpected type 'str'"，
                            # 命令因此静默失败（看起来像"撤销没反应"）。
                            # QScintilla 的 `setText()` 接受 str 并处理编码。
                            try:
                                sc.setText(text)
                            except Exception:
                                try:
                                    data = text.encode("utf-8")
                                    sc.SendScintilla(sc.SCI_SETTEXT, 0, data)
                                except Exception:
                                    pass
                        return _fn

                    rollback = _Compound(
                        forward_fn=_restore(text_after),
                        backward_fn=_restore(text_before_replay),
                        pos=0,
                        description="宏回放",
                    )
                    um = getattr(proxy, 'undo_manager', None)
                    if um is not None:
                        # 清空回放前的撤销历史：回放是一次"批量替换"，
                        # 旧的命令位置相对新内容已失效（INV-M2 要求
                        # 一次 Ctrl+Z 就回到回放前，而不是先执行旧命令）。
                        try:
                            um.undo_stack.clear()
                        except Exception:
                            pass
                        try:
                            um.redo_stack.clear()
                        except Exception:
                            pass
                        um.record(rollback)
            except Exception as e:
                print(f"[Macro] 记录回放回滚命令失败: {e}")

            # 恢复状态
            self._enable_scintilla_notifications(proxy)
            self._state = old_state

            # 恢复录制（如果之前在录制）
            if was_recording:
                self._recording = True
                self._register_hook()

            # 发射信号
            try:
                bus.emit_event(MacroReplayedEvent(
                    command_count=executed,
                    macro_name=macro.name,
                    elapsed_ms=elapsed,
                ))
            except Exception:
                pass

            if cancelled:
                self.error_occurred.emit("回放已取消")
                return False

            return True

        except Exception as e:
            self._state = MacroState.ERROR
            self._enable_scintilla_notifications(proxy)
            self.error_occurred.emit(f"回放失败: {e}")
            traceback.print_exc()
            return False

    def replay_with_offsets(self, proxy, macro: Optional[Macro] = None):
        """
        按录制时的时间偏移回放（模拟真实时间）。

        参数:
            proxy: 编辑器代理
            macro: 宏对象
        """
        if macro is None:
            macro = self.current_macro

        if macro.is_empty:
            return False

        # 禁用通知
        self._disable_scintilla_notifications(proxy)

        try:
            last_offset = 0.0
            for macro_cmd in macro.commands:
                # 等待时间差
                delay = macro_cmd.timestamp_offset - last_offset
                if delay > 0:
                    time.sleep(delay)
                last_offset = macro_cmd.timestamp_offset

                # 执行命令
                try:
                    cmd = Command.from_dict(macro_cmd.command_data)
                    cmd.execute(proxy.sc)
                except Exception as e:
                    print(f"[Macro] 回放失败: {e}")

            proxy.sc.setModified(True)
            return True

        except Exception as e:
            self.error_occurred.emit(f"回放失败: {e}")
            return False
        finally:
            self._enable_scintilla_notifications(proxy)

    def _disable_scintilla_notifications(self, proxy):
        """禁用 Scintilla 通知以提高回放性能"""
        try:
            proxy.sc.SendScintilla(proxy.sc.SCI_SETMODEVENTMASK, 0)
        except Exception:
            pass

    def _enable_scintilla_notifications(self, proxy):
        """恢复 Scintilla 通知"""
        try:
            from PyQt5.Qsci import QsciScintilla
            mask = (QsciScintilla.SC_MOD_INSERTTEXT |
                    QsciScintilla.SC_MOD_DELETETEXT)
            proxy.sc.SendScintilla(proxy.sc.SCI_SETMODEVENTMASK, mask)
        except Exception:
            pass

    # --------------------------------------------------------
    # 保存/加载
    # --------------------------------------------------------
    def save_current(self, filepath: Optional[str] = None) -> bool:
        """
        保存当前宏。

        参数:
            filepath: 文件路径（None 则自动生成）

        返回:
            是否成功
        """
        if self.current_macro.is_empty:
            self.error_occurred.emit("宏为空，无法保存")
            return False

        if not filepath:
            filepath = os.path.join(
                MACROS_DIR,
                f"{self._sanitize_filename(self.current_macro.name)}"
                f"{MACRO_FILE_EXT}"
            )

        success = self.current_macro.save(filepath)
        if success:
            self.macro_saved.emit(filepath)
        return success

    def load(self, filepath: str) -> bool:
        """
        加载宏文件。

        参数:
            filepath: 宏文件路径

        返回:
            是否成功
        """
        macro = Macro.load(filepath)
        if macro is None:
            self.error_occurred.emit(f"加载宏失败: {filepath}")
            return False

        self.current_macro = macro
        self._command_count = len(macro.commands)
        return True

    # --------------------------------------------------------
    # 查询
    # --------------------------------------------------------
    def has_commands(self) -> bool:
        """当前宏是否包含命令"""
        return not self.current_macro.is_empty

    def get_commands(self) -> List[MacroCommand]:
        """获取当前宏的所有命令"""
        return list(self.current_macro.commands)

    def get_info(self) -> Dict[str, Any]:
        """获取录制器信息"""
        return {
            'state': self._state.name,
            'recording': self._recording,
            'command_count': self._command_count,
            'duration': round(self.duration, 2),
            'macro_name': self.current_macro.name,
            'macro_empty': self.current_macro.is_empty,
        }

    # --------------------------------------------------------
    # 辅助
    # --------------------------------------------------------
    def _generate_macro_name(self) -> str:
        """生成默认宏名称"""
        now = datetime.datetime.now()
        return f"宏_{now.strftime('%Y%m%d_%H%M%S')}"

    def _get_default_author(self) -> str:
        """获取默认作者名"""
        try:
            settings = QSettings("QingCao", "Editor")
            return settings.value("author_name", "", type=str)
        except Exception:
            return ""

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """清理文件名中的非法字符"""
        invalid_chars = '<>:"/\\|?*'
        for c in invalid_chars:
            name = name.replace(c, '_')
        return name.strip() or "macro"

    # --------------------------------------------------------
    # 调试
    # --------------------------------------------------------
    def dump(self) -> str:
        """导出录制器信息"""
        info = self.get_info()
        lines = ["MacroRecorder", "=" * 60]
        lines.append(f"状态: {info['state']}")
        lines.append(f"录制中: {info['recording']}")
        lines.append(f"命令数: {info['command_count']}")
        lines.append(f"时长: {info['duration']} 秒")
        lines.append(f"宏名称: {info['macro_name']}")
        lines.append(f"宏为空: {info['macro_empty']}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<MacroRecorder state={self._state.name} "
                f"commands={self._command_count} "
                f"recording={self._recording}>")


# ============================================================
# 宏管理器
# ============================================================
class MacroManager(QObject):
    """
    宏管理器。

    管理多个宏，提供：
    - 宏列表
    - 宏的增删改查
    - 宏集合保存/加载
    - 快捷键绑定
    - 导入/导出

    信号:
        macro_added(str): 宏添加（名称）
        macro_removed(str): 宏移除（名称）
        macro_updated(str): 宏更新（名称）
        macros_changed(): 宏列表变更
    """

    macro_added = pyqtSignal(str)
    macro_removed = pyqtSignal(str)
    macro_updated = pyqtSignal(str)
    macros_changed = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

        # 宏字典：名称 -> Macro
        self._macros: Dict[str, Macro] = {}

        # 快捷键映射：快捷键 -> 宏名称
        self._shortcuts: Dict[str, str] = {}

    # --------------------------------------------------------
    # 增删改查
    # --------------------------------------------------------
    def add(self, macro: Macro, overwrite: bool = False) -> bool:
        """
        添加宏。

        参数:
            macro: 宏对象
            overwrite: 同名时是否覆盖

        返回:
            是否成功
        """
        if not macro.name:
            return False

        if macro.name in self._macros and not overwrite:
            return False

        self._macros[macro.name] = macro

        # 绑定快捷键
        if macro.shortcut:
            self._shortcuts[macro.shortcut] = macro.name

        self.macro_added.emit(macro.name)
        self.macros_changed.emit()
        return True

    def remove(self, name: str) -> bool:
        """移除宏"""
        if name not in self._macros:
            return False

        macro = self._macros.pop(name)

        # 移除快捷键
        if macro.shortcut and self._shortcuts.get(macro.shortcut) == name:
            del self._shortcuts[macro.shortcut]

        self.macro_removed.emit(name)
        self.macros_changed.emit()
        return True

    def get(self, name: str) -> Optional[Macro]:
        """获取宏"""
        return self._macros.get(name)

    def has(self, name: str) -> bool:
        """检查宏是否存在"""
        return name in self._macros

    def rename(self, old_name: str, new_name: str) -> bool:
        """重命名宏"""
        if old_name not in self._macros:
            return False
        if new_name in self._macros:
            return False

        macro = self._macros.pop(old_name)
        macro.name = new_name
        self._macros[new_name] = macro

        # 更新快捷键映射
        for shortcut, name in list(self._shortcuts.items()):
            if name == old_name:
                self._shortcuts[shortcut] = new_name

        self.macro_updated.emit(new_name)
        self.macros_changed.emit()
        return True

    def list_names(self) -> List[str]:
        """列出所有宏名称"""
        return sorted(self._macros.keys())

    def list_macros(self) -> List[Macro]:
        """列出所有宏"""
        return [self._macros[name] for name in self.list_names()]

    def count(self) -> int:
        """宏数量"""
        return len(self._macros)

    def clear(self):
        """清空所有宏"""
        self._macros.clear()
        self._shortcuts.clear()
        self.macros_changed.emit()

    # --------------------------------------------------------
    # 快捷键
    # --------------------------------------------------------
    def bind_shortcut(self, name: str, shortcut: str) -> bool:
        """绑定快捷键"""
        if name not in self._macros:
            return False

        macro = self._macros[name]

        # 解除旧的绑定
        if macro.shortcut and self._shortcuts.get(macro.shortcut) == name:
            del self._shortcuts[macro.shortcut]

        # 解除可能冲突的绑定
        if shortcut in self._shortcuts:
            old_name = self._shortcuts[shortcut]
            if old_name in self._macros:
                self._macros[old_name].shortcut = ""

        # 设置新绑定
        macro.shortcut = shortcut
        self._shortcuts[shortcut] = name

        self.macro_updated.emit(name)
        return True

    def unbind_shortcut(self, name: str) -> bool:
        """解除快捷键绑定"""
        if name not in self._macros:
            return False

        macro = self._macros[name]
        if macro.shortcut and self._shortcuts.get(macro.shortcut) == name:
            del self._shortcuts[macro.shortcut]

        macro.shortcut = ""
        self.macro_updated.emit(name)
        return True

    def get_macro_by_shortcut(self, shortcut: str) -> Optional[Macro]:
        """通过快捷键获取宏"""
        name = self._shortcuts.get(shortcut)
        if name:
            return self._macros.get(name)
        return None

    def list_shortcuts(self) -> Dict[str, str]:
        """列出所有快捷键绑定"""
        return dict(self._shortcuts)

    # --------------------------------------------------------
    # 批量保存/加载
    # --------------------------------------------------------
    def save_all(self, directory: str = MACROS_DIR) -> int:
        """
        保存所有宏到目录。

        返回:
            成功保存的数量
        """
        os.makedirs(directory, exist_ok=True)
        count = 0

        for name, macro in self._macros.items():
            filename = MacroRecorder._sanitize_filename(name) + MACRO_FILE_EXT
            filepath = os.path.join(directory, filename)
            if macro.save(filepath):
                count += 1

        return count

    def load_all(self, directory: str = MACROS_DIR) -> int:
        """
        从目录加载所有宏。

        返回:
            成功加载的数量
        """
        if not os.path.isdir(directory):
            return 0

        count = 0
        for filename in os.listdir(directory):
            if filename.endswith(MACRO_FILE_EXT) or filename.endswith('.json'):
                filepath = os.path.join(directory, filename)
                macro = Macro.load(filepath)
                if macro:
                    self.add(macro, overwrite=True)
                    count += 1

        return count

    def export_to_json(self, filepath: str) -> bool:
        """导出所有宏到单个 JSON 文件"""
        try:
            data = {
                'version': MACRO_FORMAT_VERSION,
                'exported_at': datetime.datetime.now().isoformat(),
                'count': self.count(),
                'macros': [m.to_dict() for m in self.list_macros()],
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[MacroManager] 导出失败: {e}")
            return False

    def import_from_json(self, filepath: str,
                         overwrite: bool = False) -> int:
        """从单个 JSON 文件导入宏"""
        try:
            with open(filepath, encoding='utf-8') as f:
                data = json.load(f)

            macros_data = data.get('macros', [])
            count = 0
            for macro_data in macros_data:
                macro = Macro.from_dict(macro_data)
                if self.add(macro, overwrite=overwrite):
                    count += 1
            return count
        except Exception as e:
            print(f"[MacroManager] 导入失败: {e}")
            return 0

    # --------------------------------------------------------
    # 调试
    # --------------------------------------------------------
    def dump(self) -> str:
        """导出管理器信息"""
        lines = [f"MacroManager: {self.count()} 个宏", "=" * 60]
        for name in self.list_names():
            macro = self._macros[name]
            shortcut = f" [{macro.shortcut}]" if macro.shortcut else ""
            lines.append(f"  - {name}{shortcut} "
                         f"({macro.command_count} 条命令)")
        return "\n".join(lines)

    def __len__(self) -> int:
        return self.count()

    def __contains__(self, name: str) -> bool:
        return self.has(name)

    def __iter__(self):
        return iter(self.list_macros())

    def __repr__(self) -> str:
        return f"<MacroManager macros={self.count()}>"


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import shutil
    import tempfile

    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    print("=== 测试 Macro ===")

    # 创建一个宏
    macro = Macro(name="测试宏", description="这是一个测试")
    macro.add_command(InsertCmd(0, "Hello "))
    macro.add_command(InsertCmd(6, "World"))
    macro.add_command(DeleteCmd(0, 5, b"Hello"))

    print(f"宏: {macro}")
    print(f"命令数: {macro.command_count}")
    print(f"序列化: {len(json.dumps(macro.to_dict()))} 字符")
    print()

    # 保存/加载
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_macro_test_")
    test_file = os.path.join(tmp_dir, "test.qingcao-macro.json")

    print(f"保存: {macro.save(test_file)}")
    loaded = Macro.load(test_file)
    print(f"加载: {loaded}")
    print(f"加载后命令数: {loaded.command_count}")
    print()

    # 测试 MacroRecorder
    print("=== 测试 MacroRecorder ===")

    class FakeUndoManager:
        def __init__(self):
            self.record_hook = None

        def record(self, cmd):
            if self.record_hook:
                self.record_hook(cmd)

    class FakeScintilla:
        def __init__(self):
            self.text_content = ""

        def SendScintilla(self, *args):
            return 0

        def setModified(self, m):
            pass

    class FakeProxy:
        def __init__(self):
            self.sc = FakeScintilla()

    undo_mgr = FakeUndoManager()
    recorder = MacroRecorder(undo_manager=undo_mgr)

    # 连接信号
    recorder.recording_started.connect(
        lambda: print("[信号] 录制开始")
    )
    recorder.recording_stopped.connect(
        lambda n: print(f"[信号] 录制停止: {n} 条命令")
    )
    recorder.command_recorded.connect(
        lambda n: print(f"[信号] 已记录 {n} 条命令")
    )

    # 开始录制
    recorder.start("我的测试宏")

    # 模拟记录命令
    undo_mgr.record(InsertCmd(0, "A"))
    undo_mgr.record(InsertCmd(1, "B"))
    undo_mgr.record(InsertCmd(2, "C"))

    # 停止
    result_macro = recorder.stop()
    print(f"录制的宏: {result_macro.name}")
    print(f"命令数: {result_macro.command_count}")
    print()

    print(recorder.dump())
    print()

    # 保存录制的宏
    output_path = os.path.join(tmp_dir, "recorded.qingcao-macro.json")
    print(f"保存录制宏: {recorder.save_current(output_path)}")
    print()

    # 测试回放（使用假代理）
    print("=== 测试回放 ===")
    proxy = FakeProxy()
    success = recorder.replay(proxy, repeat=1, show_progress=False,
                              check_cancel=False)
    print(f"回放结果: {success}")
    print()

    # 测试 MacroManager
    print("=== 测试 MacroManager ===")
    manager = MacroManager()

    # 添加宏
    manager.add(Macro(name="宏A", description="测试A"))
    manager.add(Macro(name="宏B", description="测试B"))
    manager.add(Macro(name="宏C", description="测试C"))

    print(f"宏数量: {manager.count()}")
    print(f"宏列表: {manager.list_names()}")

    # 绑定快捷键
    manager.bind_shortcut("宏A", "Ctrl+Alt+1")
    manager.bind_shortcut("宏B", "Ctrl+Alt+2")

    print(f"快捷键: {manager.list_shortcuts()}")
    print()

    # 通过快捷键获取宏
    macro_a = manager.get_macro_by_shortcut("Ctrl+Alt+1")
    print(f"Ctrl+Alt+1 -> {macro_a.name if macro_a else '无'}")
    print()

    # 重命名
    manager.rename("宏C", "宏C_重命名")
    print(f"重命名后: {manager.list_names()}")
    print()

    print(manager.dump())
    print()

    # 测试批量保存/加载
    print("=== 测试批量保存/加载 ===")
    save_dir = os.path.join(tmp_dir, "macros")
    print(f"保存全部: {manager.save_all(save_dir)} 个")

    new_manager = MacroManager()
    print(f"加载全部: {new_manager.load_all(save_dir)} 个")
    print(f"加载后: {new_manager.list_names()}")
    print()

    # 测试导出/导入
    print("=== 测试导出/导入 ===")
    export_file = os.path.join(tmp_dir, "macros_export.json")
    print(f"导出: {manager.export_to_json(export_file)}")

    new_manager2 = MacroManager()
    print(f"导入: {new_manager2.import_from_json(export_file)} 个")
    print(f"导入后: {new_manager2.list_names()}")
    print()

    # 清理
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print("测试完成。")
    sys.exit(0)