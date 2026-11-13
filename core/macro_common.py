#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
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

    IDLE = auto()  # 空闲
    RECORDING = auto()  # 录制中
    PLAYING = auto()  # 回放中
    ERROR = auto()  # 错误


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
            "command": self.command_data,
            "offset": self.timestamp_offset,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MacroCommand":
        return cls(
            command_data=d.get("command", {}),
            timestamp_offset=d.get("offset", 0.0),
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
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())
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
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "author": self.author,
            "tags": list(self.tags),
            "shortcut": self.shortcut,
            "metadata": dict(self.metadata),
            "command_count": self.command_count,
            "commands": [c.to_dict() for c in self.commands],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Macro":
        macro = cls(
            name=d.get("name", "未命名宏"),
            description=d.get("description", ""),
            version=d.get("version", MACRO_FORMAT_VERSION),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            author=d.get("author", ""),
            tags=list(d.get("tags", [])),
            shortcut=d.get("shortcut", ""),
            metadata=dict(d.get("metadata", {})),
        )
        for cmd_data in d.get("commands", []):
            macro.commands.append(MacroCommand.from_dict(cmd_data))
        return macro

    def save(self, filepath: str) -> bool:
        """保存到文件"""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[Macro] 保存失败: {e}")
            return False

    @classmethod
    def load(cls, filepath: str) -> Optional["Macro"]:
        """从文件加载"""
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception as e:
            print(f"[Macro] 加载失败: {e}")
            return None

    def __repr__(self) -> str:
        return f"<Macro name={self.name!r} commands={self.command_count}>"


# ============================================================
# 宏录制器
# ============================================================

__all__ = [n for n in dir() if not n.startswith("__")]
