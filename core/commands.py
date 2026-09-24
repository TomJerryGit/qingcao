#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为命令模式模块，包含：
- Command：命令抽象基类
- InsertCmd：插入文本命令
- DeleteCmd：删除文本命令
- ReplaceCmd：替换文本命令
- GroupCmd：命令组（事务性操作）
- CompoundCmd：复合命令（带逆操作）
- CommandPool：命令对象池（复用）
- CommandFactory：命令工厂与注册表
- CommandSerializer：命令序列化/反序列化
- 命令合并策略
- 命令位置信息
- 命令元数据
- 命令统计
- 命令历史查询

修复记录:
- InsertCmd.execute / undo: 兼容 str / bytes / None 输入
- ReplaceCmd.execute / undo: 同样兼容
- DeleteCmd.execute: 兼容 deleted_text 为 str / bytes
- 所有 to_dict 方法统一 str 输出，避免 JSON 序列化问题
"""

import time
import weakref
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Tuple, Type


# ============================================================
# 常量
# ============================================================
# 命令合并时间窗口（毫秒），超过此间隔不再合并
MERGE_INTERVAL_MS = 200

# 命令池最大容量
COMMAND_POOL_SIZE = 100

# 命令序列化格式版本
COMMAND_FORMAT_VERSION = 2

# 命令类型标识
CMD_TYPE_INSERT = "insert"
CMD_TYPE_DELETE = "delete"
CMD_TYPE_REPLACE = "replace"
CMD_TYPE_GROUP = "group"
CMD_TYPE_COMPOUND = "compound"
CMD_TYPE_MOVE_LINE = "move_line"
CMD_TYPE_INDENT = "indent"
CMD_TYPE_COMMENT = "comment"


# ============================================================
# 辅助函数
# ============================================================
def _to_bytes(data) -> bytes:
    """
    统一将输入转为 bytes。

    参数:
        data: str / bytes / None / 其他

    返回:
        bytes
    """
    if data is None:
        return b''
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, str):
        return data.encode('utf-8', errors='replace')
    # 其他类型：转字符串再编码
    return str(data).encode('utf-8', errors='replace')


def _to_text(data) -> str:
    """
    统一将输入转为 str。

    参数:
        data: str / bytes / None / 其他

    返回:
        str
    """
    if data is None:
        return ''
    if isinstance(data, str):
        return data
    if isinstance(data, bytes):
        return data.decode('utf-8', errors='replace')
    if isinstance(data, bytearray):
        return bytes(data).decode('utf-8', errors='replace')
    return str(data)


# ============================================================
# 命令抽象基类
# ============================================================
class Command(ABC):
    """
    命令抽象基类。

    所有编辑操作均封装为命令对象，用于：
    - 撤销/重做
    - 宏录制/回放
    - 操作审计
    - 协作同步

    子类必须实现:
    - execute(scintilla): 执行命令
    - undo(scintilla): 撤销命令
    - to_dict(): 序列化为字典
    - from_dict(d): 从字典反序列化（类方法）
    - get_position(): 返回命令影响的最小位置

    可选实现:
    - merge_with(other): 与另一命令合并
    - can_merge(other): 判断是否可以合并
    - get_metadata(): 返回命令元数据
    """

    # 类属性：命令类型标识
    command_type: str = "unknown"

    def __init__(self):
        # 命令创建时间戳
        self.timestamp: float = time.time()

        # 命令元数据（可选）
        self.metadata: Dict[str, Any] = {}

        # 命令执行标志
        self._executed: bool = False

    # --------------------------------------------------------
    # 抽象方法（子类必须实现）
    # --------------------------------------------------------
    @abstractmethod
    def execute(self, scintilla):
        """执行命令"""
        pass

    @abstractmethod
    def undo(self, scintilla):
        """撤销命令"""
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        pass

    @abstractmethod
    def get_position(self) -> int:
        """返回命令影响的最小位置（用于滚动到变更处）"""
        pass

    # --------------------------------------------------------
    # 类方法（工厂）
    # --------------------------------------------------------
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'Command':
        """
        从字典反序列化为命令对象。

        自动根据 type 字段分派到对应子类。
        """
        return CommandFactory.create_from_dict(d)

    # --------------------------------------------------------
    # 命令合并（可选重写）
    # --------------------------------------------------------
    def can_merge(self, other: 'Command') -> bool:
        """
        判断是否可以与另一命令合并。

        默认不可合并。子类可重写此方法实现合并逻辑。
        """
        return False

    def merge_with(self, other: 'Command') -> Optional['Command']:
        """
        与另一命令合并，返回新命令或 None（不可合并时）。

        默认返回 None。子类可重写此方法。
        """
        return None

    # --------------------------------------------------------
    # 元数据
    # --------------------------------------------------------
    def set_metadata(self, key: str, value: Any):
        """设置元数据"""
        self.metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """获取元数据"""
        return self.metadata.get(key, default)

    def describe(self) -> str:
        """返回命令的可读描述"""
        return f"{self.command_type}@{self.get_position()}"

    # --------------------------------------------------------
    # 查询
    # --------------------------------------------------------
    @property
    def executed(self) -> bool:
        """命令是否已执行"""
        return self._executed

    def mark_executed(self):
        """标记命令已执行"""
        self._executed = True

    def mark_undone(self):
        """标记命令已撤销"""
        self._executed = False

    # --------------------------------------------------------
    # 字符串表示
    # --------------------------------------------------------
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} pos={self.get_position()}>"


# ============================================================
# 插入命令
# ============================================================
class InsertCmd(Command):
    """
    插入文本命令。

    记录在指定位置插入的文本。撤销时删除该文本。
    """

    command_type = CMD_TYPE_INSERT

    def __init__(self, pos: int, text):
        """
        参数:
            pos: 插入位置（字符偏移）
            text: 插入的文本（str 或 bytes）
        """
        super().__init__()
        self.pos = int(pos)
        # 内部保存为 str（方便序列化与比较）
        self.text: str = _to_text(text)

    def execute(self, scintilla):
        """执行插入"""
        try:
            # 边界保护
            length = scintilla.SendScintilla(scintilla.SCI_GETLENGTH)
            pos = max(0, min(self.pos, length))

            # 统一转为 bytes
            data = _to_bytes(self.text)

            if data:
                scintilla.SendScintilla(
                    scintilla.SCI_INSERTTEXT, pos, data
                )
            self.mark_executed()
        except Exception as e:
            print(f"[InsertCmd] 执行失败: {e}")

    def undo(self, scintilla):
        """撤销插入（即删除）"""
        try:
            # 边界保护
            length = scintilla.SendScintilla(scintilla.SCI_GETLENGTH)
            pos = max(0, min(self.pos, length))

            # 计算字节长度
            encoded = _to_bytes(self.text)
            del_len = min(len(encoded), length - pos)

            if del_len > 0:
                scintilla.SendScintilla(
                    scintilla.SCI_DELETERANGE, pos, del_len
                )
            self.mark_undone()
        except Exception as e:
            print(f"[InsertCmd] 撤销失败: {e}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': CMD_TYPE_INSERT,
            'pos': self.pos,
            'text': self.text,
            'timestamp': self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'InsertCmd':
        cmd = cls(d['pos'], d.get('text', ''))
        cmd.timestamp = d.get('timestamp', time.time())
        return cmd

    def get_position(self) -> int:
        return self.pos

    # --------------------------------------------------------
    # 合并逻辑
    # --------------------------------------------------------
    def can_merge(self, other: 'Command') -> bool:
        """连续的插入可以合并"""
        if not isinstance(other, InsertCmd):
            return False
        # 位置相邻（本次插入位置等于另一命令的插入位置+长度）
        if self.pos + len(self.text) == other.pos:
            # 时间窗口内
            if (other.timestamp - self.timestamp) * 1000 < MERGE_INTERVAL_MS:
                return True
        return False

    def merge_with(self, other: 'Command') -> Optional['InsertCmd']:
        """合并两个连续插入"""
        if not self.can_merge(other):
            return None
        merged = InsertCmd(self.pos, self.text + other.text)
        merged.timestamp = other.timestamp
        return merged

    # --------------------------------------------------------
    # 元数据
    # --------------------------------------------------------
    def describe(self) -> str:
        text_preview = self.text[:20].replace('\n', '\\n')
        if len(self.text) > 20:
            text_preview += "..."
        return f"Insert@{self.pos}: '{text_preview}' ({len(self.text)} 字符)"

    def __len__(self) -> int:
        return len(self.text)


# ============================================================
# 删除命令
# ============================================================
class DeleteCmd(Command):
    """
    删除文本命令。

    记录在指定位置删除的文本。撤销时重新插入该文本。
    """

    command_type = CMD_TYPE_DELETE

    def __init__(self, pos: int, length: int, deleted_text=b''):
        """
        参数:
            pos: 删除起始位置
            length: 删除的字节数
            deleted_text: 被删除的文本（bytes / str，用于撤销）
        """
        super().__init__()
        self.pos = int(pos)
        self.length = int(length)
        # 内部保存为 bytes（用于精确还原）
        self.deleted_text: bytes = _to_bytes(deleted_text)

    def execute(self, scintilla):
        """执行删除"""
        try:
            length = scintilla.SendScintilla(scintilla.SCI_GETLENGTH)
            pos = max(0, min(self.pos, length))
            del_len = min(self.length, length - pos)
            if del_len > 0:
                scintilla.SendScintilla(
                    scintilla.SCI_DELETERANGE, pos, del_len
                )
            self.mark_executed()
        except Exception as e:
            print(f"[DeleteCmd] 执行失败: {e}")

    def undo(self, scintilla):
        """撤销删除（即重新插入）"""
        try:
            if not self.deleted_text:
                return
            length = scintilla.SendScintilla(scintilla.SCI_GETLENGTH)
            pos = max(0, min(self.pos, length))
            scintilla.SendScintilla(
                scintilla.SCI_INSERTTEXT, pos, self.deleted_text
            )
            self.mark_undone()
        except Exception as e:
            print(f"[DeleteCmd] 撤销失败: {e}")

    def to_dict(self) -> Dict[str, Any]:
        # 使用 utf-8 解码显示（有损但可读）
        return {
            'type': CMD_TYPE_DELETE,
            'pos': self.pos,
            'len': self.length,
            'text': self.deleted_text.decode('utf-8', errors='replace'),
            'timestamp': self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'DeleteCmd':
        text = d.get('text', '')
        cmd = cls(d['pos'], d.get('len', len(text)), text)
        cmd.timestamp = d.get('timestamp', time.time())
        return cmd

    def get_position(self) -> int:
        return self.pos

    # --------------------------------------------------------
    # 合并逻辑
    # --------------------------------------------------------
    def can_merge(self, other: 'Command') -> bool:
        """连续删除可以合并"""
        if not isinstance(other, DeleteCmd):
            return False
        # 同一位置删除（因为删除后位置不变）
        if self.pos == other.pos:
            if (other.timestamp - self.timestamp) * 1000 < MERGE_INTERVAL_MS:
                return True
        return False

    def merge_with(self, other: 'Command') -> Optional['DeleteCmd']:
        """合并两个连续删除"""
        if not self.can_merge(other):
            return None
        merged = DeleteCmd(
            self.pos,
            self.length + other.length,
            self.deleted_text + other.deleted_text
        )
        merged.timestamp = other.timestamp
        return merged

    # --------------------------------------------------------
    # 元数据
    # --------------------------------------------------------
    def describe(self) -> str:
        text_preview = self.deleted_text.decode(
            'utf-8', errors='replace'
        )[:20]
        return f"Delete@{self.pos}: {self.length} 字节 ('{text_preview}')"

    def __len__(self) -> int:
        return self.length


# ============================================================
# 替换命令
# ============================================================
class ReplaceCmd(Command):
    """
    替换文本命令。

    记录在指定范围替换的文本。撤销时恢复原文本。
    """

    command_type = CMD_TYPE_REPLACE

    def __init__(self, pos: int, length: int,
                 old_text, new_text):
        """
        参数:
            pos: 替换起始位置
            length: 被替换的字节数
            old_text: 原文本（str / bytes，用于撤销）
            new_text: 新文本（str / bytes）
        """
        super().__init__()
        self.pos = int(pos)
        self.length = int(length)
        self.old_text: str = _to_text(old_text)
        self.new_text: str = _to_text(new_text)

    def execute(self, scintilla):
        """执行替换"""
        try:
            # 删除旧文本
            length = scintilla.SendScintilla(scintilla.SCI_GETLENGTH)
            pos = max(0, min(self.pos, length))
            del_len = min(self.length, length - pos)
            if del_len > 0:
                scintilla.SendScintilla(
                    scintilla.SCI_DELETERANGE, pos, del_len
                )

            # 插入新文本（统一转 bytes）
            data = _to_bytes(self.new_text)
            if data:
                scintilla.SendScintilla(
                    scintilla.SCI_INSERTTEXT, pos, data
                )
            self.mark_executed()
        except Exception as e:
            print(f"[ReplaceCmd] 执行失败: {e}")

    def undo(self, scintilla):
        """撤销替换"""
        try:
            # 删除新文本
            length = scintilla.SendScintilla(scintilla.SCI_GETLENGTH)
            pos = max(0, min(self.pos, length))
            new_encoded = _to_bytes(self.new_text)
            del_len = min(len(new_encoded), length - pos)
            if del_len > 0:
                scintilla.SendScintilla(
                    scintilla.SCI_DELETERANGE, pos, del_len
                )

            # 恢复旧文本
            old_encoded = _to_bytes(self.old_text)
            if old_encoded:
                scintilla.SendScintilla(
                    scintilla.SCI_INSERTTEXT, pos, old_encoded
                )
            self.mark_undone()
        except Exception as e:
            print(f"[ReplaceCmd] 撤销失败: {e}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': CMD_TYPE_REPLACE,
            'pos': self.pos,
            'len': self.length,
            'old': self.old_text,
            'new': self.new_text,
            'timestamp': self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'ReplaceCmd':
        cmd = cls(d['pos'], d.get('len', 0),
                  d.get('old', ''), d.get('new', ''))
        cmd.timestamp = d.get('timestamp', time.time())
        return cmd

    def get_position(self) -> int:
        return self.pos

    def describe(self) -> str:
        return (f"Replace@{self.pos}: '{self.old_text[:15]}' -> "
                f"'{self.new_text[:15]}'")


# ============================================================
# 命令组
# ============================================================
class GroupCmd(Command):
    """
    命令组（事务性操作）。

    将多个命令打包为一个原子操作，撤销/重做时整体处理。
    用于：
    - 列模式批量编辑
    - 多光标编辑
    - 宏录制的批量操作
    """

    command_type = CMD_TYPE_GROUP

    def __init__(self, cmds: Optional[List[Command]] = None):
        super().__init__()
        self.cmds: List[Command] = cmds if cmds else []

    def add(self, cmd: Command):
        """添加命令到组"""
        self.cmds.append(cmd)

    def extend(self, cmds: List[Command]):
        """批量添加命令"""
        self.cmds.extend(cmds)

    def execute(self, scintilla):
        """执行组内所有命令"""
        for cmd in self.cmds:
            cmd.execute(scintilla)
        self.mark_executed()

    def undo(self, scintilla):
        """逆序撤销组内所有命令"""
        for cmd in reversed(self.cmds):
            cmd.undo(scintilla)
        self.mark_undone()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type': CMD_TYPE_GROUP,
            'cmds': [c.to_dict() for c in self.cmds],
            'timestamp': self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'GroupCmd':
        cmds = [Command.from_dict(c) for c in d.get('cmds', [])]
        cmd = cls(cmds)
        cmd.timestamp = d.get('timestamp', time.time())
        return cmd

    def get_position(self) -> int:
        """返回组内最小位置"""
        if not self.cmds:
            return 0
        return min(c.get_position() for c in self.cmds)

    def can_merge(self, other: 'Command') -> bool:
        """命令组可以合并另一个命令组"""
        return isinstance(other, GroupCmd)

    def merge_with(self, other: 'Command') -> Optional['GroupCmd']:
        """合并两个命令组"""
        if not self.can_merge(other):
            return None
        merged = GroupCmd(self.cmds + other.cmds)
        merged.timestamp = other.timestamp
        return merged

    def __len__(self) -> int:
        return len(self.cmds)

    def __iter__(self):
        return iter(self.cmds)

    def __getitem__(self, index) -> Command:
        return self.cmds[index]

    def is_empty(self) -> bool:
        """是否为空组"""
        return len(self.cmds) == 0

    def describe(self) -> str:
        return f"Group({len(self.cmds)} 条命令)"


# ============================================================
# 复合命令
# ============================================================
class CompoundCmd(Command):
    """
    复合命令（带显式逆操作）。

    用于记录正向操作和反向操作不同的场景，例如：
    - 整行移动：正向是移动，反向也是移动（但方向相反）
    - 代码注释切换：正向是添加，反向是删除
    """

    command_type = CMD_TYPE_COMPOUND

    def __init__(self,
                 forward_fn=None,
                 backward_fn=None,
                 pos: int = 0,
                 description: str = ""):
        """
        参数:
            forward_fn: 正向操作函数（接收 scintilla）
            backward_fn: 反向操作函数（接收 scintilla）
            pos: 命令影响的位置
            description: 描述
        """
        super().__init__()
        self.forward_fn = forward_fn
        self.backward_fn = backward_fn
        self.pos = pos
        self.description = description

    def execute(self, scintilla):
        """执行正向操作"""
        if self.forward_fn:
            try:
                self.forward_fn(scintilla)
            except Exception as e:
                print(f"[CompoundCmd] 正向操作失败: {e}")
        self.mark_executed()

    def undo(self, scintilla):
        """执行反向操作"""
        if self.backward_fn:
            try:
                self.backward_fn(scintilla)
            except Exception as e:
                print(f"[CompoundCmd] 反向操作失败: {e}")
        self.mark_undone()

    def to_dict(self) -> Dict[str, Any]:
        # 复合命令通常无法序列化函数，只能记录描述
        return {
            'type': CMD_TYPE_COMPOUND,
            'pos': self.pos,
            'description': self.description,
            'timestamp': self.timestamp,
            'serializable': False,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'CompoundCmd':
        cmd = cls(pos=d.get('pos', 0),
                  description=d.get('description', ''))
        cmd.timestamp = d.get('timestamp', time.time())
        return cmd

    def get_position(self) -> int:
        return self.pos

    def describe(self) -> str:
        return f"Compound@{self.pos}: {self.description}"


# ============================================================
# 命令工厂
# ============================================================
class CommandFactory:
    """
    命令工厂。

    负责根据类型标识创建命令对象，并维护命令类型注册表。
    """

    # 命令类型注册表
    _registry: Dict[str, Type[Command]] = {
        CMD_TYPE_INSERT: InsertCmd,
        CMD_TYPE_DELETE: DeleteCmd,
        CMD_TYPE_REPLACE: ReplaceCmd,
        CMD_TYPE_GROUP: GroupCmd,
        CMD_TYPE_COMPOUND: CompoundCmd,
    }

    @classmethod
    def register(cls, type_name: str, cmd_class: Type[Command]):
        """注册自定义命令类型"""
        cls._registry[type_name] = cmd_class

    @classmethod
    def unregister(cls, type_name: str):
        """注销命令类型"""
        cls._registry.pop(type_name, None)

    @classmethod
    def create_from_dict(cls, d: Dict[str, Any]) -> Command:
        """
        从字典创建命令对象。

        参数:
            d: 命令字典

        返回:
            命令实例

        异常:
            ValueError: 未知命令类型
        """
        cmd_type = d.get('type')
        if not cmd_type:
            raise ValueError("命令字典缺少 'type' 字段")

        cmd_class = cls._registry.get(cmd_type)
        if cmd_class is None:
            raise ValueError(f"未知命令类型: {cmd_type}")

        return cmd_class.from_dict(d)

    @classmethod
    def create_insert(cls, pos: int, text) -> InsertCmd:
        """创建插入命令"""
        return InsertCmd(pos, text)

    @classmethod
    def create_delete(cls, pos: int, length: int,
                      deleted_text=b'') -> DeleteCmd:
        """创建删除命令"""
        return DeleteCmd(pos, length, deleted_text)

    @classmethod
    def create_replace(cls, pos: int, length: int,
                       old_text, new_text) -> ReplaceCmd:
        """创建替换命令"""
        return ReplaceCmd(pos, length, old_text, new_text)

    @classmethod
    def create_group(cls,
                     cmds: Optional[List[Command]] = None) -> GroupCmd:
        """创建命令组"""
        return GroupCmd(cmds)

    @classmethod
    def list_types(cls) -> List[str]:
        """列出所有已注册的命令类型"""
        return list(cls._registry.keys())


# ============================================================
# 命令序列化器
# ============================================================
class CommandSerializer:
    """
    命令序列化器。

    将命令列表序列化为 JSON 兼容的字典，支持版本迁移。
    """

    @staticmethod
    def serialize(cmds: List[Command]) -> Dict[str, Any]:
        """
        序列化命令列表。

        参数:
            cmds: 命令列表

        返回:
            序列化后的字典
        """
        return {
            'version': COMMAND_FORMAT_VERSION,
            'count': len(cmds),
            'created_at': time.time(),
            'commands': [cmd.to_dict() for cmd in cmds],
        }

    @staticmethod
    def deserialize(data: Dict[str, Any]) -> List[Command]:
        """
        反序列化命令列表。

        参数:
            data: 序列化数据

        返回:
            命令列表
        """
        version = data.get('version', 1)
        commands_data = data.get('commands', [])

        # 版本迁移
        if version < 2:
            commands_data = CommandSerializer._migrate_v1_to_v2(
                commands_data
            )

        result = []
        for cmd_data in commands_data:
            try:
                cmd = Command.from_dict(cmd_data)
                result.append(cmd)
            except Exception as e:
                print(f"[CommandSerializer] 反序列化失败: {e}")
                continue

        return result

    @staticmethod
    def _migrate_v1_to_v2(commands_data: List[Dict[str, Any]]
                          ) -> List[Dict[str, Any]]:
        """从 v1 迁移到 v2"""
        for cmd_data in commands_data:
            # v1 使用 'length'，v2 使用 'len'
            if 'length' in cmd_data and 'len' not in cmd_data:
                cmd_data['len'] = cmd_data.pop('length')
        return commands_data

    @staticmethod
    def to_json(cmds: List[Command]) -> str:
        """序列化为 JSON 字符串"""
        import json
        return json.dumps(
            CommandSerializer.serialize(cmds),
            indent=2, ensure_ascii=False
        )

    @staticmethod
    def from_json(json_str: str) -> List[Command]:
        """从 JSON 字符串反序列化"""
        import json
        data = json.loads(json_str)
        return CommandSerializer.deserialize(data)


# ============================================================
# 命令对象池
# ============================================================
class CommandPool:
    """
    命令对象池。

    复用命令对象，减少 GC 压力。适用于高频创建的场景（如输入）。
    """

    _insert_pool: List[InsertCmd] = []
    _delete_pool: List[DeleteCmd] = []

    @classmethod
    def acquire_insert(cls, pos: int, text) -> InsertCmd:
        """获取插入命令（从池或新建）"""
        if cls._insert_pool:
            cmd = cls._insert_pool.pop()
            # 重置状态
            cmd.pos = int(pos)
            cmd.text = _to_text(text)
            cmd.timestamp = time.time()
            cmd.metadata = {}
            cmd._executed = False
            return cmd
        return InsertCmd(pos, text)

    @classmethod
    def release_insert(cls, cmd: InsertCmd):
        """归还插入命令到池"""
        if len(cls._insert_pool) < COMMAND_POOL_SIZE:
            cls._insert_pool.append(cmd)

    @classmethod
    def acquire_delete(cls, pos: int, length: int,
                       deleted_text=b'') -> DeleteCmd:
        """获取删除命令（从池或新建）"""
        if cls._delete_pool:
            cmd = cls._delete_pool.pop()
            cmd.pos = int(pos)
            cmd.length = int(length)
            cmd.deleted_text = _to_bytes(deleted_text)
            cmd.timestamp = time.time()
            cmd.metadata = {}
            cmd._executed = False
            return cmd
        return DeleteCmd(pos, length, deleted_text)

    @classmethod
    def release_delete(cls, cmd: DeleteCmd):
        """归还删除命令到池"""
        if len(cls._delete_pool) < COMMAND_POOL_SIZE:
            cls._delete_pool.append(cmd)

    @classmethod
    def clear(cls):
        """清空池"""
        cls._insert_pool.clear()
        cls._delete_pool.clear()

    @classmethod
    def stats(cls) -> Dict[str, int]:
        """返回池的统计信息"""
        return {
            'insert_pool_size': len(cls._insert_pool),
            'delete_pool_size': len(cls._delete_pool),
            'max_size': COMMAND_POOL_SIZE,
        }


# ============================================================
# 命令统计
# ============================================================
class CommandStats:
    """
    命令统计器。

    记录命令使用情况，用于性能分析和用户行为统计。
    """

    def __init__(self):
        self.total_commands: int = 0
        self.type_counts: Dict[str, int] = {}
        self.total_inserted_chars: int = 0
        self.total_deleted_chars: int = 0
        self.first_command_time: Optional[float] = None
        self.last_command_time: Optional[float] = None

    def record(self, cmd: Command):
        """记录一个命令"""
        self.total_commands += 1
        cmd_type = cmd.command_type
        self.type_counts[cmd_type] = self.type_counts.get(cmd_type, 0) + 1

        if isinstance(cmd, InsertCmd):
            self.total_inserted_chars += len(cmd.text)
        elif isinstance(cmd, DeleteCmd):
            self.total_deleted_chars += cmd.length
        elif isinstance(cmd, GroupCmd):
            for sub_cmd in cmd.cmds:
                self.record(sub_cmd)
            return  # 避免重复计数

        now = time.time()
        if self.first_command_time is None:
            self.first_command_time = now
        self.last_command_time = now

    def reset(self):
        """重置统计"""
        self.__init__()

    def get_summary(self) -> Dict[str, Any]:
        """获取统计摘要"""
        duration = 0.0
        if self.first_command_time and self.last_command_time:
            duration = self.last_command_time - self.first_command_time

        return {
            'total_commands': self.total_commands,
            'type_counts': dict(self.type_counts),
            'inserted_chars': self.total_inserted_chars,
            'deleted_chars': self.total_deleted_chars,
            'duration_seconds': round(duration, 2),
            'commands_per_second': (
                round(self.total_commands / duration, 2)
                if duration > 0 else 0
            ),
        }

    def dump(self) -> str:
        """导出统计信息"""
        summary = self.get_summary()
        lines = ["命令统计", "=" * 60]
        lines.append(f"总命令数: {summary['total_commands']}")
        lines.append(f"插入字符: {summary['inserted_chars']}")
        lines.append(f"删除字符: {summary['deleted_chars']}")
        lines.append(f"持续时间: {summary['duration_seconds']} 秒")
        lines.append(f"每秒命令: {summary['commands_per_second']}")
        lines.append("")
        lines.append("按类型统计:")
        for cmd_type, count in sorted(summary['type_counts'].items(),
                                      key=lambda x: x[1], reverse=True):
            lines.append(f"  {cmd_type}: {count}")
        return "\n".join(lines)


# ============================================================
# 命令历史
# ============================================================
class CommandHistory:
    """
    命令历史记录器。

    用于调试和审计，记录最近执行的命令。
    """

    def __init__(self, max_size: int = 200):
        self.max_size = max_size
        self._history: List[Tuple[float, Command, str]] = []

    def record(self, cmd: Command, action: str = "execute"):
        """
        记录命令。

        参数:
            cmd: 命令
            action: 动作类型（execute / undo / redo）
        """
        self._history.append((time.time(), cmd, action))
        if len(self._history) > self.max_size:
            self._history.pop(0)

    def clear(self):
        """清空历史"""
        self._history.clear()

    def get_recent(self, count: int = 20
                    ) -> List[Tuple[float, Command, str]]:
        """获取最近的命令"""
        return self._history[-count:]

    def get_by_action(self, action: str
                       ) -> List[Tuple[float, Command, str]]:
        """按动作类型筛选"""
        return [entry for entry in self._history if entry[2] == action]

    def dump(self, count: int = 20) -> str:
        """导出历史"""
        lines = [f"命令历史 (共 {len(self._history)} 条)", "=" * 60]
        for ts, cmd, action in self.get_recent(count):
            time_str = time.strftime("%H:%M:%S", time.localtime(ts))
            lines.append(f"  [{time_str}] {action:8s} {cmd.describe()}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._history)


# ============================================================
# 辅助函数
# ============================================================
def merge_commands(cmds: List[Command],
                   interval_ms: float = MERGE_INTERVAL_MS
                   ) -> List[Command]:
    """
    合并命令列表中的可合并命令。

    参数:
        cmds: 命令列表
        interval_ms: 合并时间窗口（毫秒）

    返回:
        合并后的命令列表
    """
    if not cmds:
        return []

    merged: List[Command] = [cmds[0]]
    for cmd in cmds[1:]:
        last = merged[-1]
        if last.can_merge(cmd):
            new_cmd = last.merge_with(cmd)
            if new_cmd is not None:
                merged[-1] = new_cmd
                continue
        merged.append(cmd)

    return merged


def commands_to_positions(cmds: List[Command]) -> List[int]:
    """提取所有命令的位置"""
    return [cmd.get_position() for cmd in cmds]


def total_chars_changed(cmds: List[Command]) -> int:
    """计算命令列表总影响字符数"""
    total = 0
    for cmd in cmds:
        if isinstance(cmd, InsertCmd):
            total += len(cmd.text)
        elif isinstance(cmd, DeleteCmd):
            total += cmd.length
        elif isinstance(cmd, ReplaceCmd):
            total += max(len(cmd.old_text), len(cmd.new_text))
        elif isinstance(cmd, GroupCmd):
            total += total_chars_changed(cmd.cmds)
    return total


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    print("=== 测试命令创建 ===")

    # 创建插入命令
    insert = CommandFactory.create_insert(10, "Hello")
    print(f"插入命令: {insert}")
    print(f"  dict: {insert.to_dict()}")

    # 创建删除命令
    delete = CommandFactory.create_delete(5, 3, b"abc")
    print(f"删除命令: {delete}")
    print(f"  dict: {delete.to_dict()}")

    # 创建替换命令
    replace = CommandFactory.create_replace(0, 5, "Hello", "World")
    print(f"替换命令: {replace}")
    print(f"  dict: {replace.to_dict()}")

    print()
    print("=== 测试命令组 ===")
    group = CommandFactory.create_group([insert, delete, replace])
    print(f"命令组: {group}")
    print(f"  包含 {len(group)} 条命令")
    print(f"  最小位置: {group.get_position()}")

    print()
    print("=== 测试序列化/反序列化 ===")
    cmds = [insert, delete, replace, group]
    serialized = CommandSerializer.serialize(cmds)
    print(f"序列化: {serialized['count']} 条命令")

    deserialized = CommandSerializer.deserialize(serialized)
    print(f"反序列化: {len(deserialized)} 条命令")
    for cmd in deserialized:
        print(f"  - {cmd.describe()}")

    print()
    print("=== 测试 JSON 序列化 ===")
    json_str = CommandSerializer.to_json(cmds)
    print(f"JSON 长度: {len(json_str)} 字符")

    restored = CommandSerializer.from_json(json_str)
    print(f"从 JSON 恢复: {len(restored)} 条命令")

    print()
    print("=== 测试命令合并 ===")
    # 连续插入命令
    cmd1 = InsertCmd(0, "Hello ")
    cmd2 = InsertCmd(6, "World")
    cmd2.timestamp = cmd1.timestamp + 0.05  # 50ms 后
    merged = merge_commands([cmd1, cmd2])
    print(f"合并前: 2 条命令")
    print(f"合并后: {len(merged)} 条命令")
    if merged:
        print(f"  结果: {merged[0].describe()}")

    print()
    print("=== 测试命令对象池 ===")
    pool_cmd = CommandPool.acquire_insert(100, "pooled")
    print(f"从池获取: {pool_cmd}")
    CommandPool.release_insert(pool_cmd)
    print(f"池统计: {CommandPool.stats()}")

    print()
    print("=== 测试命令统计 ===")
    stats = CommandStats()
    for cmd in cmds:
        stats.record(cmd)
    print(stats.dump())

    print()
    print("=== 测试命令历史 ===")
    history = CommandHistory()
    for cmd in cmds:
        history.record(cmd, "execute")
    print(history.dump())

    print()
    print("=== 测试命令类型注册 ===")
    print(f"已注册类型: {CommandFactory.list_types()}")

    print()
    print("=== 测试辅助函数 ===")
    print(f"命令位置: {commands_to_positions(cmds)}")
    print(f"总影响字符数: {total_chars_changed(cmds)}")

    print()
    print("=== 测试 bytes 兼容性（关键修复）===")
    # 模拟从 QScintilla 传来的 bytes
    cmd_bytes = InsertCmd(0, b"Hello bytes")
    print(f"bytes 输入: {cmd_bytes.describe()}")
    print(f"  to_dict: {cmd_bytes.to_dict()}")

    # 模拟 None 输入
    cmd_none = InsertCmd(0, None)
    print(f"None 输入: {cmd_none.describe()}")

    # 从 dict 恢复
    d = {'type': 'insert', 'pos': 5, 'text': 'test'}
    cmd_restored = Command.from_dict(d)
    print(f"从 dict 恢复: {cmd_restored.describe()}")