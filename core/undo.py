#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为撤销/重做管理器模块，包含：
- UndoManager：撤销/重做管理器
- 命令栈管理（撤销栈 + 重做栈）
- 时间窗口命令合并
- 命令组（GroupCmd）自动合并
- 保存点标记与恢复
- 撤销/重做历史记录
- 撤销深度限制
- 内存占用统计
- 撤销/重做信号
- 宏录制钩子
- 命令批量操作
- 事务支持
- 统计信息
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt5.QtCore import QDateTime, QObject, pyqtSignal

from core.commands import (
    MERGE_INTERVAL_MS,
    Command,
    CommandFactory,
    CommandPool,
    DeleteCmd,
    GroupCmd,
    InsertCmd,
    ReplaceCmd,
    merge_commands,
)


# ============================================================
# 常量
# ============================================================
# 默认最大撤销深度
DEFAULT_MAX_DEPTH = 500

# 默认命令合并时间窗口（毫秒）
DEFAULT_MERGE_INTERVAL = 200

# 默认命令合并数量上限（防止单个组过大）
MAX_GROUP_SIZE = 1000

# 撤销栈大小警告阈值
UNDO_STACK_WARN_SIZE = 10000


# ============================================================
# 撤销统计
# ============================================================
class UndoStatistics:
    """撤销/重做统计器"""

    def __init__(self):
        self.total_undo = 0
        self.total_redo = 0
        self.total_commands_recorded = 0
        self.total_commands_merged = 0
        self.merge_count = 0
        self._lock = threading.Lock()

    def record_undo(self):
        with self._lock:
            self.total_undo += 1

    def record_redo(self):
        with self._lock:
            self.total_redo += 1

    def record_command(self):
        with self._lock:
            self.total_commands_recorded += 1

    def record_merge(self, merged_count: int):
        with self._lock:
            self.total_commands_merged += merged_count
            self.merge_count += 1

    def reset(self):
        with self._lock:
            self.__init__()

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'total_undo': self.total_undo,
                'total_redo': self.total_redo,
                'total_commands_recorded': self.total_commands_recorded,
                'total_commands_merged': self.total_commands_merged,
                'merge_count': self.merge_count,
                'avg_merged_per_group': (
                    round(self.total_commands_merged / self.merge_count, 2)
                    if self.merge_count > 0 else 0
                ),
            }

    def dump(self) -> str:
        info = self.get_summary()
        lines = ["撤销统计", "=" * 60]
        for k, v in info.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)


# ============================================================
# 保存点
# ============================================================
@dataclass
class SavePoint:
    """保存点"""

    position: int                 # 在撤销栈中的位置
    timestamp: float = field(default_factory=time.time)
    label: str = ""               # 可读标签
    file_path: Optional[str] = None

    def __repr__(self) -> str:
        return f"<SavePoint pos={self.position} label={self.label!r}>"


# ============================================================
# 撤销历史记录
# ============================================================
@dataclass
class UndoHistoryEntry:
    """撤销历史条目"""

    action: str                   # "record" / "undo" / "redo" / "merge"
    command_desc: str = ""
    timestamp: float = field(default_factory=time.time)
    undo_stack_size: int = 0
    redo_stack_size: int = 0

    def __repr__(self) -> str:
        ts = time.strftime("%H:%M:%S", time.localtime(self.timestamp))
        return (f"<UndoHistory [{ts}] {self.action}: "
                f"{self.command_desc} (undo={self.undo_stack_size})>")


# ============================================================
# 撤销/重做管理器
# ============================================================
class UndoManager(QObject):
    """
    撤销/重做管理器。

    职责:
    - 管理撤销栈和重做栈
    - 记录命令到栈
    - 执行撤销/重做操作
    - 时间窗口内的命令自动合并
    - 保存点标记与恢复
    - 撤销深度限制（防止内存爆炸）
    - 宏录制钩子（record_hook）
    - 统计信息

    信号:
        command_recorded(str): 命令已记录（命令描述）
        undo_performed(str): 撤销完成（命令描述）
        redo_performed(str): 重做完成（命令描述）
        stack_changed(int, int): 栈变化（undo_size, redo_size）
        save_point_reached(): 到达保存点
        save_point_left(): 离开保存点
        undo_stack_full(): 撤销栈已满
    """

    # 信号
    command_recorded = pyqtSignal(str)
    undo_performed = pyqtSignal(str)
    redo_performed = pyqtSignal(str)
    stack_changed = pyqtSignal(int, int)
    save_point_reached = pyqtSignal()
    save_point_left = pyqtSignal()
    undo_stack_full = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None,
                 max_depth: int = DEFAULT_MAX_DEPTH,
                 merge_interval: int = DEFAULT_MERGE_INTERVAL):
        """
        参数:
            parent: 父 QObject
            max_depth: 最大撤销深度（0 表示无限）
            merge_interval: 命令合并时间窗口（毫秒）
        """
        super().__init__(parent)

        # 栈
        self.undo_stack: List[Command] = []
        self.redo_stack: List[Command] = []

        # 配置
        self.max_depth = max_depth
        self.merge_interval = merge_interval

        # 命令合并状态
        self._pending_group: Optional[GroupCmd] = None
        self._pending_group_time: float = 0.0

        # 宏录制钩子
        self.record_hook: Optional[Callable] = None

        # 保存点
        self._save_points: List[SavePoint] = []
        self._current_save_position: int = 0
        self._at_save_point: bool = True

        # 事务支持
        self._transaction_active: bool = False
        self._transaction_start_size: int = 0

        # 统计
        self.statistics = UndoStatistics()

        # 历史记录（用于调试）
        self._history: deque = deque(maxlen=200)
        self._history_enabled: bool = False

        # 线程锁（保护栈操作）
        self._lock = threading.RLock()

        # 禁用状态（用于批量操作时暂停记录）
        self._disabled: bool = False

    # ========================================================
    # 记录命令
    # ========================================================
    def record(self, command: Command):
        """
        记录一个命令到撤销栈。

        参数:
            command: 命令对象（已执行）

        修复（INV-1，审计用例复现）：
            原先只有 `_do_record()` 会 `redo_stack.clear()`，而 `record()`
            里**合并分支直接 `return True`**（`_try_merge` 命中即返回），
            绕过了清空逻辑：

                undo_stack=[A, Z] -> undo() -> redo_stack=[Z]
                begin_group(P) + record(Q) -> Q 合并进 pending group，return
                => 内容已经被改变（P/Q 进了撤销栈），但 redo 栈仍留着 Z

            用户此时按 Ctrl+Y 会重放 Z，而 Z 是针对**旧内容**的命令 ——
            内容错乱且不可逆。

            因此把"新操作使 redo 失效"提到 `record()` 入口：无论走合并
            还是独立记录路径，只要记录了一条新命令，redo 栈都必须清空。
            （`_do_record` 里的清空保留，作为直接调用它的其它路径的兜底。）
        """
        if self._disabled:
            return

        if command is None:
            return

        with self._lock:
            try:
                # 统计
                self.statistics.record_command()

                # 新操作让重做栈失效 —— 必须放在合并判断**之前**，
                # 因为合并分支也会 return（见 docstring）。
                if self.redo_stack:
                    self.redo_stack.clear()
                    try:
                        self.stack_changed.emit(
                            len(self.undo_stack), 0
                        )
                    except Exception:
                        pass

                # 检查是否与 pending group 合并
                if self._try_merge(command):
                    return

                # 提交 pending group
                self._commit_pending_group()

                # 直接记录命令
                self._do_record(command)

            except Exception as e:
                print(f"[UndoManager] 记录失败: {e}")

    def _do_record(self, command: Command):
        """实际记录命令"""
        # 清空重做栈（新操作后重做栈失效）
        if self.redo_stack:
            self.redo_stack.clear()

        # 添加命令
        self.undo_stack.append(command)

        # 检查深度限制
        if self.max_depth > 0 and len(self.undo_stack) > self.max_depth:
            # 移除最旧的一半
            remove_count = len(self.undo_stack) // 2
            del self.undo_stack[:remove_count]

        # 更新保存点位置
        self._update_save_points_after_record()

        # 检查是否离开保存点
        self._check_save_point_state()

        # 历史记录
        if self._history_enabled:
            self._history.append(UndoHistoryEntry(
                action="record",
                command_desc=command.describe() if hasattr(command, 'describe')
                else str(command),
                undo_stack_size=len(self.undo_stack),
                redo_stack_size=len(self.redo_stack),
            ))

        # 调用宏录制钩子
        if self.record_hook:
            try:
                self.record_hook(command)
            except Exception as e:
                print(f"[UndoManager] record_hook 异常: {e}")

        # 发射信号
        try:
            self.command_recorded.emit(
                command.describe() if hasattr(command, 'describe')
                else type(command).__name__
            )
            self.stack_changed.emit(len(self.undo_stack), len(self.redo_stack))
        except Exception:
            pass

    # ========================================================
    # 命令合并
    # ========================================================
    def try_append_typing(self, pos: int, text) -> bool:
        """打字快路径：直接追加到栈顶 InsertCmd，跳过命令对象分配。

        只在"连续单字符插入、位置相邻、合并窗口内"时命中；其它情况返回
        False，由调用方走完整的命令构建路径。语义与原有 merge 完全一致
        （一次撤销撤掉整段连续输入）。
        """
        if self._disabled or self._pending_group is not None:
            return False
        if not self.undo_stack:
            return False
        # 新操作使 redo 失效（与 record() 入口语义一致）
        if self.redo_stack:
            self.redo_stack.clear()
        last = self.undo_stack[-1]
        now = time.time()
        try:
            if not last.can_merge_append(now, pos):
                return False
            from core.commands import _to_text
            last.append_text(_to_text(text), now)
            self.statistics.record_merge(1)
            return True
        except Exception:
            return False

    def _try_merge(self, command: Command) -> bool:
        """
        尝试将命令合并到 pending group 或上一个命令。

        返回:
            True 表示已合并，False 表示需要独立记录
        """
        now = time.time() * 1000

        # 检查是否有 pending group
        if self._pending_group is not None:
            elapsed = now - self._pending_group_time

            if elapsed < self.merge_interval:
                # 时间窗口内，检查组大小
                if len(self._pending_group.cmds) < MAX_GROUP_SIZE:
                    # 尝试合并到组
                    self._pending_group.add(command)
                    self._pending_group_time = now
                    self.statistics.record_merge(1)

                    if self._history_enabled:
                        self._history.append(UndoHistoryEntry(
                            action="merge",
                            command_desc=f"合并到组 ({len(self._pending_group.cmds)})",
                        ))
                    return True
                else:
                    # 组太大，先提交
                    self._commit_pending_group()
            else:
                # 时间窗口外，提交旧组
                self._commit_pending_group()

        # 检查是否可以与上一个命令合并
        if self.undo_stack:
            last_cmd = self.undo_stack[-1]

            try:
                if last_cmd.can_merge(command):
                    # C 阶段优化：InsertCmd 原地追加，不重建对象
                    if (hasattr(last_cmd, "append_from")
                            and last_cmd.append_from(command)):
                        self.statistics.record_merge(1)
                        if self._history_enabled:
                            self._history.append(UndoHistoryEntry(
                                action="merge",
                                command_desc="原地追加",
                                undo_stack_size=len(self.undo_stack),
                                redo_stack_size=len(self.redo_stack),
                            ))
                        return True
                    merged = last_cmd.merge_with(command)
                    if merged is not None:
                        # 替换栈顶
                        self.undo_stack[-1] = merged
                        self.statistics.record_merge(1)

                        if self._history_enabled:
                            self._history.append(UndoHistoryEntry(
                                action="merge",
                                command_desc=f"合并: {merged.describe() if hasattr(merged, 'describe') else type(merged).__name__}",
                                undo_stack_size=len(self.undo_stack),
                                redo_stack_size=len(self.redo_stack),
                            ))
                        return True
            except Exception:
                pass

        return False

    def begin_group(self, command: Command):
        """
        开始一个命令组。

        组内的所有命令将被合并为一个 GroupCmd。

        参数:
            command: 第一条命令
        """
        if self._disabled:
            return

        with self._lock:
            # 提交旧组
            self._commit_pending_group()

            # 创建新组
            self._pending_group = GroupCmd([command])
            self._pending_group_time = time.time() * 1000

    def end_group(self):
        """结束当前命令组并提交"""
        with self._lock:
            self._commit_pending_group()

    def _commit_pending_group(self):
        """提交待处理的命令组"""
        if self._pending_group is None:
            return

        group = self._pending_group
        self._pending_group = None

        if group.is_empty():
            return

        self._do_record(group)

    # ========================================================
    # 撤销
    # ========================================================
    def undo(self, scintilla=None) -> bool:
        """
        执行撤销。

        参数:
            scintilla: QScintilla 控件（用于执行命令）

        返回:
            是否成功
        """
        if self._disabled:
            return False

        with self._lock:
            try:
                # 提交 pending group
                self._commit_pending_group()

                # 检查栈
                if not self.undo_stack:
                    return False

                # 弹出命令
                command = self.undo_stack.pop()

                # 执行撤销（如果提供了 scintilla）
                if scintilla is not None:
                    command.undo(scintilla)

                # 添加到重做栈
                self.redo_stack.append(command)

                # 更新保存点
                self._update_save_points_after_undo()

                # 检查保存点状态
                self._check_save_point_state()

                # 统计
                self.statistics.record_undo()

                # 历史记录
                if self._history_enabled:
                    self._history.append(UndoHistoryEntry(
                        action="undo",
                        command_desc=command.describe() if hasattr(command, 'describe')
                        else type(command).__name__,
                        undo_stack_size=len(self.undo_stack),
                        redo_stack_size=len(self.redo_stack),
                    ))

                # 发射信号
                try:
                    self.undo_performed.emit(
                        command.describe() if hasattr(command, 'describe')
                        else type(command).__name__
                    )
                    self.stack_changed.emit(
                        len(self.undo_stack), len(self.redo_stack)
                    )
                except Exception:
                    pass

                return True

            except Exception as e:
                print(f"[UndoManager] 撤销失败: {e}")
                return False

    # ========================================================
    # 重做
    # ========================================================
    def redo(self, scintilla=None) -> bool:
        """
        执行重做。

        参数:
            scintilla: QScintilla 控件

        返回:
            是否成功
        """
        if self._disabled:
            return False

        with self._lock:
            try:
                # 提交 pending group
                self._commit_pending_group()

                # 检查栈
                if not self.redo_stack:
                    return False

                # 弹出命令
                command = self.redo_stack.pop()

                # 执行重做
                if scintilla is not None:
                    command.execute(scintilla)

                # 添加到撤销栈
                self.undo_stack.append(command)

                # 更新保存点
                self._update_save_points_after_redo()

                # 检查保存点状态
                self._check_save_point_state()

                # 统计
                self.statistics.record_redo()

                # 历史记录
                if self._history_enabled:
                    self._history.append(UndoHistoryEntry(
                        action="redo",
                        command_desc=command.describe() if hasattr(command, 'describe')
                        else type(command).__name__,
                        undo_stack_size=len(self.undo_stack),
                        redo_stack_size=len(self.redo_stack),
                    ))

                # 发射信号
                try:
                    self.redo_performed.emit(
                        command.describe() if hasattr(command, 'describe')
                        else type(command).__name__
                    )
                    self.stack_changed.emit(
                        len(self.undo_stack), len(self.redo_stack)
                    )
                except Exception:
                    pass

                return True

            except Exception as e:
                print(f"[UndoManager] 重做失败: {e}")
                return False

    # ========================================================
    # 批量操作
    # ========================================================
    def undo_multiple(self, scintilla=None, count: int = 1) -> int:
        """
        执行多次撤销。

        参数:
            scintilla: QScintilla 控件
            count: 撤销次数

        返回:
            实际撤销的次数
        """
        executed = 0
        for _ in range(count):
            if not self.undo(scintilla):
                break
            executed += 1
        return executed

    def redo_multiple(self, scintilla=None, count: int = 1) -> int:
        """执行多次重做"""
        executed = 0
        for _ in range(count):
            if not self.redo(scintilla):
                break
            executed += 1
        return executed

    def undo_to_save_point(self, scintilla=None) -> int:
        """
        撤销到最近的保存点。

        返回:
            实际撤销的次数
        """
        # 找到目标位置
        target_pos = self._find_nearest_save_point_before()

        if target_pos is None:
            return 0

        count = 0
        while len(self.undo_stack) > target_pos:
            if not self.undo(scintilla):
                break
            count += 1

        return count

    def redo_to_save_point(self, scintilla=None) -> int:
        """重做到最近的保存点"""
        target_pos = self._find_nearest_save_point_after()

        if target_pos is None:
            return 0

        count = 0
        while len(self.undo_stack) < target_pos and self.redo_stack:
            if not self.redo(scintilla):
                break
            count += 1

        return count

    # ========================================================
    # 状态查询
    # ========================================================
    def can_undo(self) -> bool:
        """是否可撤销"""
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        """是否可重做"""
        return len(self.redo_stack) > 0

    def get_undo_count(self) -> int:
        """撤销栈大小"""
        return len(self.undo_stack)

    def get_redo_count(self) -> int:
        """重做栈大小"""
        return len(self.redo_stack)

    def get_undo_description(self) -> str:
        """获取下一个可撤销命令的描述"""
        if not self.undo_stack:
            return ""
        cmd = self.undo_stack[-1]
        return cmd.describe() if hasattr(cmd, 'describe') else type(cmd).__name__

    def get_redo_description(self) -> str:
        """获取下一个可重做命令的描述"""
        if not self.redo_stack:
            return ""
        cmd = self.redo_stack[-1]
        return cmd.describe() if hasattr(cmd, 'describe') else type(cmd).__name__

    def is_clean(self) -> bool:
        """是否处于保存点（无未保存修改）"""
        return self._at_save_point

    # ========================================================
    # 清空
    # ========================================================
    def clear(self):
        """清空所有栈"""
        with self._lock:
            self.undo_stack.clear()
            self.redo_stack.clear()
            self._pending_group = None
            self._save_points.clear()
            self._current_save_position = 0
            self._at_save_point = True

            try:
                self.stack_changed.emit(0, 0)
            except Exception:
                pass

    def clear_redo(self):
        """清空重做栈"""
        with self._lock:
            self.redo_stack.clear()
            try:
                self.stack_changed.emit(
                    len(self.undo_stack), len(self.redo_stack)
                )
            except Exception:
                pass

    # ========================================================
    # 保存点
    # ========================================================
    def mark_save_point(self, label: str = "",
                        file_path: Optional[str] = None):
        """
        标记当前状态为保存点。

        参数:
            label: 可读标签（如 "已保存"）
            file_path: 关联的文件路径
        """
        with self._lock:
            # 提交 pending group
            self._commit_pending_group()

            position = len(self.undo_stack)
            save_point = SavePoint(
                position=position,
                label=label or "保存点",
                file_path=file_path,
            )

            # 移除重复位置的点
            self._save_points = [
                sp for sp in self._save_points if sp.position != position
            ]

            self._save_points.append(save_point)
            self._save_points.sort(key=lambda sp: sp.position)

            self._current_save_position = position
            self._at_save_point = True

            try:
                self.save_point_reached.emit()
            except Exception:
                pass

    def clear_save_points(self):
        """清除所有保存点"""
        with self._lock:
            self._save_points.clear()
            self._at_save_point = False

    def get_save_points(self) -> List[SavePoint]:
        """获取所有保存点"""
        return list(self._save_points)

    def get_nearest_save_point(self) -> Optional[SavePoint]:
        """获取最近的保存点"""
        if not self._save_points:
            return None

        current_pos = len(self.undo_stack)
        nearest = None
        min_distance = float('inf')

        for sp in self._save_points:
            distance = abs(sp.position - current_pos)
            if distance < min_distance:
                min_distance = distance
                nearest = sp

        return nearest

    def _find_nearest_save_point_before(self) -> Optional[int]:
        """找到当前位置之前最近的保存点"""
        current_pos = len(self.undo_stack)
        candidates = [sp.position for sp in self._save_points
                      if sp.position <= current_pos]
        return max(candidates) if candidates else None

    def _find_nearest_save_point_after(self) -> Optional[int]:
        """找到当前位置之后最近的保存点"""
        current_pos = len(self.undo_stack)
        candidates = [sp.position for sp in self._save_points
                      if sp.position > current_pos]
        return min(candidates) if candidates else None

    def _update_save_points_after_record(self):
        """记录命令后更新保存点位置（无需调整，因为位置是按栈大小）"""
        # 位置是栈大小的快照，记录新命令后，之前的保存点位置不变
        # 但当前不在保存点了
        pass

    def _update_save_points_after_undo(self):
        """撤销后更新"""
        pass

    def _update_save_points_after_redo(self):
        """重做后更新"""
        pass

    def _check_save_point_state(self):
        """检查是否处于保存点状态"""
        current_pos = len(self.undo_stack)

        was_at = self._at_save_point
        now_at = (current_pos == self._current_save_position)

        self._at_save_point = now_at

        try:
            if now_at and not was_at:
                self.save_point_reached.emit()
            elif not now_at and was_at:
                self.save_point_left.emit()
        except Exception:
            pass

    # ========================================================
    # 事务支持
    # ========================================================
    def begin_transaction(self):
        """
        开始事务。

        事务内的所有命令将被合并为一个命令组，
        在 commit_transaction 时一次性记录。
        """
        if self._disabled:
            return

        with self._lock:
            if self._transaction_active:
                return

            # 提交已有组
            self._commit_pending_group()

            self._transaction_active = True
            self._transaction_start_size = len(self.undo_stack)

    def commit_transaction(self, description: str = ""):
        """
        提交事务。

        参数:
            description: 事务描述（可选）
        """
        if not self._transaction_active:
            return

        with self._lock:
            self._transaction_active = False

            # 检查是否有新命令
            new_count = len(self.undo_stack) - self._transaction_start_size

            if new_count > 0:
                # 将新命令合并为一个组
                new_commands = self.undo_stack[self._transaction_start_size:]
                del self.undo_stack[self._transaction_start_size:]

                if len(new_commands) == 1:
                    group = new_commands[0]
                else:
                    group = GroupCmd(new_commands)
                    if description:
                        group.metadata['transaction'] = description

                self.undo_stack.append(group)

                try:
                    self.stack_changed.emit(
                        len(self.undo_stack), len(self.redo_stack)
                    )
                except Exception:
                    pass

    def rollback_transaction(self, scintilla=None):
        """
        回滚事务。

        撤销事务内的所有操作。
        """
        if not self._transaction_active:
            return

        with self._lock:
            self._transaction_active = False

            # 撤销所有新命令
            while len(self.undo_stack) > self._transaction_start_size:
                if not self.undo(scintilla):
                    break

    # ========================================================
    # 启用/禁用
    # ========================================================
    def disable(self):
        """禁用记录（用于批量操作时避免记录无用命令）"""
        self._disabled = True

    def enable(self):
        """启用记录"""
        self._disabled = False

    def is_disabled(self) -> bool:
        return self._disabled

    def __enter__(self):
        """上下文管理器：自动禁用"""
        self.disable()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器：自动启用"""
        self.enable()
        return False

    # ========================================================
    # 合并优化
    # ========================================================
    def compact(self) -> int:
        """
        压缩撤销栈。

        合并栈中可以合并的命令，减少内存占用。

        返回:
            合并的命令数量
        """
        with self._lock:
            if len(self.undo_stack) < 2:
                return 0

            original_size = len(self.undo_stack)

            try:
                compacted = merge_commands(self.undo_stack,
                                           self.merge_interval)
                self.undo_stack = compacted
            except Exception as e:
                print(f"[UndoManager] 压缩失败: {e}")
                return 0

            merged_count = original_size - len(self.undo_stack)

            if merged_count > 0:
                try:
                    self.stack_changed.emit(
                        len(self.undo_stack), len(self.redo_stack)
                    )
                except Exception:
                    pass

            return merged_count

    # ========================================================
    # 统计与信息
    # ========================================================
    def get_memory_estimate(self) -> int:
        """
        估算撤销栈的内存占用（字节）。

        粗略估算，仅供参考。
        """
        total = 0

        for cmd in self.undo_stack:
            try:
                data = cmd.to_dict()
                import json
                total += len(json.dumps(data).encode('utf-8'))
            except Exception:
                total += 100  # 粗略估计

        for cmd in self.redo_stack:
            try:
                data = cmd.to_dict()
                import json
                total += len(json.dumps(data).encode('utf-8'))
            except Exception:
                total += 100

        return total

    def get_info(self) -> Dict[str, Any]:
        """获取管理器信息"""
        return {
            'undo_count': len(self.undo_stack),
            'redo_count': len(self.redo_stack),
            'max_depth': self.max_depth,
            'merge_interval': self.merge_interval,
            'at_save_point': self._at_save_point,
            'save_points': len(self._save_points),
            'memory_bytes': self.get_memory_estimate(),
            'can_undo': self.can_undo(),
            'can_redo': self.can_redo(),
            'disabled': self._disabled,
            'transaction_active': self._transaction_active,
            'pending_group': (
                len(self._pending_group.cmds)
                if self._pending_group else 0
            ),
        }

    def set_history_enabled(self, enabled: bool):
        """启用/禁用历史记录"""
        self._history_enabled = enabled

    def get_history(self, limit: int = 50) -> List[UndoHistoryEntry]:
        """获取历史记录"""
        if not self._history_enabled:
            return []
        return list(self._history)[-limit:]

    def clear_history(self):
        """清空历史记录"""
        self._history.clear()

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出管理器信息"""
        info = self.get_info()
        lines = ["UndoManager", "=" * 60]

        for k, v in info.items():
            if k == 'memory_bytes':
                lines.append(f"  {k}: {v} ({v / 1024:.1f} KB)")
            else:
                lines.append(f"  {k}: {v}")

        # 保存点
        if self._save_points:
            lines.append("")
            lines.append("保存点:")
            for sp in self._save_points:
                ts = time.strftime("%H:%M:%S",
                                   time.localtime(sp.timestamp))
                marker = " ← 当前" if sp.position == self._current_save_position else ""
                lines.append(f"  [{ts}] pos={sp.position} "
                             f"{sp.label}{marker}")

        # 栈内容摘要
        if self.undo_stack:
            lines.append("")
            lines.append("撤销栈（最近 10 条）:")
            for cmd in self.undo_stack[-10:]:
                desc = (cmd.describe() if hasattr(cmd, 'describe')
                        else type(cmd).__name__)
                lines.append(f"  - {desc}")

        if self.redo_stack:
            lines.append("")
            lines.append("重做栈（最近 5 条）:")
            for cmd in self.redo_stack[-5:]:
                desc = (cmd.describe() if hasattr(cmd, 'describe')
                        else type(cmd).__name__)
                lines.append(f"  - {desc}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<UndoManager undo={len(self.undo_stack)} "
                f"redo={len(self.redo_stack)} "
                f"at_save={self._at_save_point}>")


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    print("=== 测试 UndoManager ===")

    # 创建管理器
    manager = UndoManager()

    # 连接信号
    manager.command_recorded.connect(
        lambda d: print(f"[信号] 记录: {d}")
    )
    manager.undo_performed.connect(
        lambda d: print(f"[信号] 撤销: {d}")
    )
    manager.redo_performed.connect(
        lambda d: print(f"[信号] 重做: {d}")
    )
    manager.stack_changed.connect(
        lambda u, r: print(f"[信号] 栈: undo={u}, redo={r}")
    )
    manager.save_point_reached.connect(
        lambda: print("[信号] 到达保存点")
    )
    manager.save_point_left.connect(
        lambda: print("[信号] 离开保存点")
    )

    print()

    # 模拟记录命令
    print("=== 记录命令 ===")
    manager.record(InsertCmd(0, "Hello"))
    manager.record(InsertCmd(5, " World"))
    manager.record(InsertCmd(11, "!"))

    print(f"\n栈状态: {manager}")
    print()

    # 标记保存点
    print("=== 标记保存点 ===")
    manager.mark_save_point("已保存")
    print(f"是否在保存点: {manager.is_clean()}")
    print()

    # 继续记录
    print("=== 继续记录 ===")
    manager.record(DeleteCmd(0, 5, b"Hello"))
    print(f"是否在保存点: {manager.is_clean()}")
    print()

    # 撤销
    print("=== 撤销 ===")
    manager.undo()
    print(f"撤销后是否在保存点: {manager.is_clean()}")
    print()

    # 重做
    print("=== 重做 ===")
    manager.redo()
    print(f"重做后是否在保存点: {manager.is_clean()}")
    print()

    # 测试命令合并
    print("=== 测试命令合并 ===")
    manager.clear()

    # 快速连续插入（应合并）
    manager.record(InsertCmd(0, "H"))
    manager.record(InsertCmd(1, "e"))
    manager.record(InsertCmd(2, "l"))
    manager.record(InsertCmd(3, "l"))
    manager.record(InsertCmd(4, "o"))

    print(f"合并后栈大小: {len(manager.undo_stack)}")
    if manager.undo_stack:
        cmd = manager.undo_stack[0]
        print(f"栈顶命令: {cmd.describe() if hasattr(cmd, 'describe') else cmd}")
    print()

    # 测试组
    print("=== 测试命令组 ===")
    manager.clear()

    manager.begin_group(InsertCmd(0, "A"))
    manager.record(InsertCmd(1, "B"))
    manager.record(InsertCmd(2, "C"))
    manager.end_group()

    print(f"组后栈大小: {len(manager.undo_stack)}")
    print()

    # 测试事务
    print("=== 测试事务 ===")
    manager.clear()

    manager.begin_transaction()
    manager.record(InsertCmd(0, "X"))
    manager.record(InsertCmd(1, "Y"))
    manager.record(InsertCmd(2, "Z"))
    manager.commit_transaction("批量插入")

    print(f"事务后栈大小: {len(manager.undo_stack)}")
    print()

    # 测试保存点恢复
    print("=== 测试保存点恢复 ===")
    manager.clear()

    manager.record(InsertCmd(0, "A"))
    manager.mark_save_point("save1")
    manager.record(InsertCmd(1, "B"))
    manager.record(InsertCmd(2, "C"))

    print(f"当前栈: {len(manager.undo_stack)}")
    print(f"是否在保存点: {manager.is_clean()}")

    count = manager.undo_to_save_point()
    print(f"撤销到保存点: {count} 次")
    print(f"是否在保存点: {manager.is_clean()}")
    print()

    # 测试启用/禁用
    print("=== 测试启用/禁用 ===")
    manager.clear()

    with manager:
        manager.record(InsertCmd(0, "ignored"))
    manager.record(InsertCmd(0, "recorded"))

    print(f"禁用期间记录被忽略，栈大小: {len(manager.undo_stack)}")
    print()

    # 打印统计
    print("=== 统计信息 ===")
    print(manager.statistics.dump())
    print()

    # 打印管理器状态
    print("=== 管理器状态 ===")
    print(manager.dump())
    print()

    print(f"管理器信息: {manager.get_info()}")
    print()

    # 测试历史
    print("=== 测试历史记录 ===")
    manager.set_history_enabled(True)
    manager.record(InsertCmd(0, "history1"))
    manager.record(InsertCmd(8, "history2"))
    manager.undo()

    history = manager.get_history()
    print(f"历史记录数: {len(history)}")
    for entry in history:
        print(f"  {entry}")
    print()

    print("测试完成。")
    sys.exit(0)