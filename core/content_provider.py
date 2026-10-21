#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为内容提供者模块，包含：
- ContentProvider：内容提供者抽象基类
- LocalFileProvider：本地文件提供者（mmap 分块）
- MemoryProvider：内存提供者（临时缓冲区）
- StreamProvider：流式提供者（stdin/网络流）
- ProviderFactory：提供者工厂
- 分块读写与脏块追踪
- 自动编码检测（chardet 可选）
- BOM 处理
- 行尾符识别与转换
- 原子保存
- 文件权限与只读保护
- 大文件虚拟加载
- 内存限制与块卸载
- 文件变更检测（mtime/hash）

修复记录:
- 在基类 ContentProvider 增加 check_external_change / reload /
  set_readonly 的默认实现，避免 MemoryProvider 缺少方法
- 所有子类无需实现这三个方法也不会崩溃
"""

import hashlib
import io
import logging
import mmap
import os
import stat
import sys
import time
from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


# ============================================================
# 常量
# ============================================================
DEFAULT_BLOCK_SIZE = 64 * 1024          # 默认块大小 64KB
MAX_BLOCK_SIZE = 1024 * 1024            # 最大块大小 1MB
MIN_BLOCK_SIZE = 4096                   # 最小块大小 4KB
MAX_LOADED_BLOCKS = 2000                # 最多同时加载的块数
LARGE_FILE_THRESHOLD = 10 * 1024 * 1024  # 大文件阈值 10MB
HUGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 超大文件阈值 100MB

# 低于该大小的文件**不建立内存映射**，直接用文件读。
#
# 为什么（Windows 文件锁定，已实测）：
#   即使**只读**的 mmap 也会阻止另一进程覆盖写该文件
#   （`open(path,'w')` 抛 `OSError: [Errno 22]`）。编辑器一旦为某文件
#   建立映射，git / 构建工具 / 其它编辑器就无法修改它 —— 于是
#   "外部文件变更检测"与"三方合并"永远不会触发（这正是它们存在的意义）。
#
#   小文件逐个 read() 的开销可以忽略，且不留下驻锁；大文件才用映射
#   换取 I/O 性能（`release_mmap()` 可在需要时主动释放）。
MMAP_MIN_SIZE = 4 * 1024 * 1024         # 4MB

# 常见编码
ENCODING_UTF8 = 'utf-8'
ENCODING_UTF8_BOM = 'utf-8-sig'
ENCODING_GBK = 'gbk'
ENCODING_GB18030 = 'gb18030'
ENCODING_BIG5 = 'big5'
ENCODING_SHIFT_JIS = 'shift_jis'
ENCODING_EUC_KR = 'euc-kr'
ENCODING_LATIN1 = 'latin-1'
ENCODING_ASCII = 'ascii'
ENCODING_UTF16_LE = 'utf-16-le'
ENCODING_UTF16_BE = 'utf-16-be'

# BOM 标记
BOMS = {
    b'\xef\xbb\xbf': 'utf-8-sig',
    b'\xff\xfe\x00\x00': 'utf-32-le',
    b'\x00\x00\xfe\xff': 'utf-32-be',
    b'\xff\xfe': 'utf-16-le',
    b'\xfe\xff': 'utf-16-be',
}

# 行尾符
EOL_LF = '\n'
EOL_CRLF = '\r\n'
EOL_CR = '\r'

# BOM 字符（U+FEFF）
_BOM_CHAR = '\ufeff'

# 需要"解码后手动剥 BOM"的编码
#
# 为什么需要（真实压测发现的缺陷）：
#   `BOMS` 把 UTF-16/32 的 BOM 映射成**裸端序编码**（`utf-16-le` 等），
#   这类编码**不剥离 BOM**，解出来第一个字符就是 U+FEFF。
#   而 `utf-8-sig` 会自动剥离 —— 于是只有 UTF-16/32 会出现
#   "文本模型里凭空多一个不可见字符"的不对称行为。
#
#   实测：32 字符的 UTF-16LE 文件被读成 33 字符，首字符 U+FEFF。
#   `encode()` 用同一裸端序编码不会补 BOM，所以**字节仍保真**，
#   但文本层面的搜索/替换/解析/diff 都会因此错位或报错。
_BOM_STRIPPED_ENCODINGS = frozenset({
    'utf-16', 'utf-16-le', 'utf-16-be',
    'utf-32', 'utf-32-le', 'utf-32-be',
})

# 裸端序编码 → 它应该带上的 BOM
#
# 用途见 `encode()` 的说明：这类编码的 `str.encode()` 不补 BOM，
# 保存时必须手动补回，否则"编辑过的 UTF-16 文件"会丢 BOM。
# `utf-16`/`utf-32`（不带端序后缀）的编码器**自己会加 BOM**，故不在此表。
_BARE_ENDIAN_BOM = {
    'utf-16-le': b'\xff\xfe',
    'utf-16-be': b'\xfe\xff',
    'utf-32-le': b'\xff\xfe\x00\x00',
    'utf-32-be': b'\x00\x00\xfe\xff',
}


def _strip_leading_bom(text: str, encoding: str) -> str:
    """剥掉解码结果**开头**的 BOM（仅首字符，不动正文里的 U+FEFF）"""
    if text and text[0] == _BOM_CHAR:
        if str(encoding or '').lower() in _BOM_STRIPPED_ENCODINGS:
            return text[1:]
    return text


# ============================================================
# 异常定义
# ============================================================
class ContentProviderError(Exception):
    """内容提供者异常基类"""
    pass


class FileNotFoundError(ContentProviderError):
    """文件不存在"""
    pass


class PermissionDeniedError(ContentProviderError):
    """权限不足"""
    pass


class EncodingError(ContentProviderError):
    """编码错误"""
    pass


class ProviderClosedError(ContentProviderError):
    """提供者已关闭"""
    pass


# ============================================================
# 文件状态枚举
# ============================================================
class FileState(Enum):
    """文件状态"""
    CLOSED = auto()     # 未打开
    OPENED = auto()     # 已打开
    MODIFIED = auto()   # 已修改
    READONLY = auto()   # 只读
    ERROR = auto()      # 错误


# ============================================================
# 内容提供者抽象基类
# ============================================================
class ContentProvider(ABC):
    """
    内容提供者抽象基类。

    定义文件内容访问的统一接口。所有具体实现必须继承此类。

    子类必须实现:
    - open(source): 打开数据源
    - read_block(block_id): 读取指定块
    - write_block(block_id, data): 写入指定块
    - save(): 持久化
    - close(): 关闭并释放资源

    属性:
    - block_size: 块大小（字节）
    - total_blocks: 总块数
    - filepath: 数据源路径（可能为空）
    - encoding: 文本编码
    - size: 总字节数
    """

    def __init__(self):
        self._state: FileState = FileState.CLOSED
        self._block_size: int = DEFAULT_BLOCK_SIZE
        self._total_blocks: int = 0
        self._filepath: Optional[str] = None
        self._encoding: str = ENCODING_UTF8
        self._size: int = 0
        self._readonly: bool = False
        self._dirty_blocks: Dict[int, bytes] = {}
        self._eol: str = EOL_LF
        # 行尾符是否由用户**显式**指定（决定保存时是否做行尾转换）
        self._eol_explicit: bool = False
        self._has_bom: bool = False
        self._mtime: float = 0.0
        self._hash: Optional[str] = None
        # 字符对齐块边界缓存（见 _aligned_block_bounds）
        self._bounds_cache: Optional[list] = None
        self._bounds_cache_key = None

    # --------------------------------------------------------
    # 抽象方法
    # --------------------------------------------------------
    @abstractmethod
    def open(self, source: Any, **kwargs) -> bool:
        """打开数据源"""
        pass

    @abstractmethod
    def read_block(self, block_id: int) -> bytes:
        """读取指定块（返回字节串）"""
        pass

    @abstractmethod
    def write_block(self, block_id: int, data: bytes) -> bool:
        """写入指定块（脏块缓冲）"""
        pass

    @abstractmethod
    def save(self) -> bool:
        """持久化数据"""
        pass

    @abstractmethod
    def close(self):
        """关闭并释放资源"""
        pass

    # --------------------------------------------------------
    # 属性访问器
    # --------------------------------------------------------
    @property
    def block_size(self) -> int:
        return self._block_size

    @property
    def total_blocks(self) -> int:
        return self._total_blocks

    @property
    def filepath(self) -> Optional[str]:
        return self._filepath

    @property
    def encoding(self) -> str:
        return self._encoding

    @encoding.setter
    def encoding(self, value: str):
        self._encoding = value

    @property
    def size(self) -> int:
        return self._size

    @property
    def readonly(self) -> bool:
        return self._readonly

    @property
    def state(self) -> FileState:
        return self._state

    @property
    def is_open(self) -> bool:
        return self._state not in (FileState.CLOSED, FileState.ERROR)

    @property
    def is_modified(self) -> bool:
        return len(self._dirty_blocks) > 0

    @property
    def eol(self) -> str:
        return self._eol

    @property
    def has_bom(self) -> bool:
        return self._has_bom

    @property
    def mtime(self) -> float:
        return self._mtime

    @property
    def dirty_block_count(self) -> int:
        return len(self._dirty_blocks)

    # --------------------------------------------------------
    # 便捷方法
    # --------------------------------------------------------
    def read_all(self) -> bytes:
        """读取全部内容（用于小文件或测试）"""
        if not self.is_open:
            raise ProviderClosedError("提供者未打开")
        chunks = []
        for i in range(self._total_blocks):
            chunks.append(self.read_block(i))
        return b''.join(chunks)

    def read_text(self) -> str:
        """读取全部内容为文本"""
        return self.decode(self.read_all())

    # --------------------------------------------------------
    # 块边界对齐（修复跨块多字节字符损坏）
    # --------------------------------------------------------
    # 缺陷背景（P0-A，已用 tools/probe_block_boundary.py 实测复现）：
    #   块按固定字节偏移切分（block_id * 64KiB），一个 UTF-8 多字节字符
    #   可能正好横跨边界。按块独立 decode 时，两半都无法解码，被
    #   `errors='replace'` 换成 U+FFFD。用户屏幕上看到 "�"，
    #   而**一旦保存就会把 EF BF BD 写回磁盘，原字节永久丢失**。
    #
    #   实测：65536 字节处放一个"测"，逐块拼接与 read_text() 均得到
    #   '�'（因为 read_all 也是拼接块字节后再整体解码，同样在边界断开）。
    #
    # 修复思路：
    #   把每个块的**结束位置向前收缩**到最后一个完整字符的边界，
    #   下一个块从该边界开始。于是每块都能独立、无损地解码，
    #   且 read_all() 拼接后也正好还原原文（块之间首尾相接、无重叠无空隙）。
    #
    # 只在多字节可变长编码（UTF-8 系）下启用；单字节编码下对齐结果与
    # 原始偏移完全一致，因此本逻辑对它们是无操作。
    _UTF8_ENCODINGS = ('utf-8', 'utf8', 'utf_8', 'utf-8-sig', 'utf8-sig')

    def _needs_boundary_alignment(self) -> bool:
        """当前编码是否为多字节可变长（需要字符边界对齐）"""
        enc = (self._encoding or '').lower().replace('_', '-')
        return enc in ('utf-8', 'utf8', 'utf-8-sig', 'utf8-sig')

    def _aligned_block_bounds(self) -> list:
        """返回 [(start, end), ...]，每块边界都落在字符边界上。

        结果按 `_size` 缓存，避免热路径重复扫描。
        文件内容变化（size 或脏块）时缓存自动失效。
        """
        cache_key = (self._size, len(self._dirty_blocks))
        if getattr(self, '_bounds_cache_key', None) == cache_key:
            return self._bounds_cache

        size = self._size
        bs = self._block_size
        total = max(1, self._total_blocks)

        # 脏块内的字节以内存为准，其余从文件读
        def _raw(start: int, end: int) -> bytes:
            bid = start // bs
            if bid in self._dirty_blocks:
                blk = bytes(self._dirty_blocks[bid])
                base = bid * bs
                return blk[max(0, start - base):end - base]
            if self._mmap:
                try:
                    return self._mmap[start:end]
                except (ValueError, OSError):
                    pass
            if self._file:
                try:
                    self._file.seek(start)
                    return self._file.read(end - start)
                except Exception:
                    pass
            return b''

        bounds = []
        start = 0
        for _ in range(total):
            if start >= size:
                break
            end = min(start + bs, size)
            if end < size:
                # 以 end 为基准向前试探，找到最近的、可独立解码的字符边界
                win_start = max(start, end - 4)
                win = _raw(win_start, end)
                end = self._align_forward(win, win_start, end)
                if end <= start:
                    # 极端兜底：保证至少前进 1 字节，避免死循环
                    end = min(start + bs, size)
            bounds.append((start, end))
            start = end

        self._bounds_cache = bounds
        self._bounds_cache_key = cache_key
        return bounds

    @staticmethod
    def _is_char_start(buf: bytes, pos: int, end_limit: int) -> bool:
        """判断 buf[pos] 是否是一个**完整** UTF-8 字符的起始字节

        只检查"不是延续字节"是不够的：一个字符的内部也可能出现
        `0xE6` 这类字节（例如 "测" = e6 b5 8b，若从第二个字节 b5 起算
        就永远对不齐）。必须向后验证**完整序列**：

            ASCII      0xxxxxxx                      -> 1 字节
            2 字节     110xxxxx 10xxxxxx              -> 2 字节
            3 字节     1110xxxx 10xxxxxx 10xxxxxx     -> 3 字节
            4 字节     11110xxx 10xxxxxx ×3          -> 4 字节
        """
        if pos < 0 or pos >= len(buf):
            return False
        b0 = buf[pos]
        if b0 < 0x80:
            return True
        if 0xC2 <= b0 <= 0xDF:
            need = 1
        elif 0xE0 <= b0 <= 0xEF:
            need = 2
        elif 0xF0 <= b0 <= 0xF4:
            need = 3
        else:
            # 延续字节 (0x80-0xBF) 或非法首字节 (0xC0/0xC1/0xF5+)
            return False
        if pos + need >= end_limit:
            # 序列不完整（数据在此处被截断）
            return False
        for k in range(1, need + 1):
            if (buf[pos + k] & 0xC0) != 0x80:
                return False
        return True

    def _align_forward(self, win: bytes, win_start: int, end: int) -> int:
        """把 end 收缩到最近的、可独立解码的字符边界

        判定方式：以 `end` 为基准，向前最多试探 3 个位置，选出第一个
        **能作为完整字符串首**的位置。该位置的字节同时满足：
          * 它是某个完整 UTF-8 字符的起始字节（向后验证序列）；
          * 它前面一个字节不是"被截断的多字节序列开头"。

        参数:
            win: [win_start, end) 区间的字节（含边界前的若干字节）
            win_start: 窗口起始偏移（下界保护）
            end: 待调整的结束偏移

        返回:
            调整后的结束偏移（<= end）
        """
        if not win:
            return end
        n = len(win)
        # 以 end 为基准向前试探：end, end-1, end-2, end-3
        for back in range(0, min(4, n + 1)):
            pos = n - back          # 在 win 中的下标（相对）
            if pos < 0:
                pos = 0
            abs_pos = win_start + pos
            if abs_pos > end:
                continue
            if self._is_char_start(win, pos, n):
                # 再确认前一个字节不是"被截断的多字节序列开头"
                if pos == 0:
                    return abs_pos
                prev = win[pos - 1]
                if (prev & 0xC0) == 0xC0 and (prev & 0x1F) != 0:
                    # 前一字节像首字节，但它的序列跨越了 pos —— 该序列
                    # 若完整则应从 prev 开始，说明 pos 不是真正的边界
                    continue
                return abs_pos
        return end

    def _invalidate_bounds_cache(self):
        """内容/尺寸变化后调用，使对齐边界缓存失效"""
        self._bounds_cache_key = None
        self._bounds_cache = None

    # ========================================================
    # 修复：在基类提供默认实现
    # ========================================================
    def check_external_change(self) -> bool:
        """
        检查文件是否被外部程序修改。

        基类默认返回 False（内存/流式提供者没有外部文件）。
        LocalFileProvider 覆盖此方法实现真实检测。
        """
        return False

    def release_mmap(self):
        """释放映射与文件句柄，允许其它程序修改本文件

        为什么需要（Windows 文件锁定，已实测）：
            即使**只读**的内存映射也会阻止另一进程覆盖写该文件 ——
            `open(path, 'w')` 抛 `OSError: [Errno 22] Invalid argument`。
            于是编辑器一打开文件，git / 构建工具 / 其它编辑器就无法修改
            它，而"外部变更检测 / 三方合并"因此永远不会触发。

            小文件（<= `MMAP_MIN_SIZE`）本就不建立映射，本方法对它们等价
            于释放句柄；大文件才真正解开映射，由 CPython 的 mmap 析构器
            安全回收（显式 `close()` 与 Qt 视图生命周期交织时曾引发段错误，
            因此这里只丢弃引用）。

        调用点：`TabManager.open_file` / `_reload_file`（各释放自己的
        provider）。释放后 `read_block()` 会经 `_ensure_handle()` 按需重开。
        """
        self._mmap = None
        fh = self._file
        self._file = None
        if fh is not None:
            try:
                if not getattr(fh, 'closed', True):
                    fh.close()
            except Exception:
                pass

    def reload(self) -> bool:
        """
        重新加载文件内容。

        基类默认返回 False（不支持重载）。
        LocalFileProvider 覆盖此方法。
        """
        return False

    def set_readonly(self, readonly: bool) -> bool:
        """
        设置只读状态。

        基类默认直接修改内部标志。
        LocalFileProvider 覆盖此方法做额外校验。
        """
        self._readonly = bool(readonly)
        if readonly:
            self._state = FileState.READONLY
        elif self._state == FileState.READONLY:
            self._state = FileState.OPENED
        return True
    # ========================================================
    # 修复结束
    # ========================================================

    def decode(self, data: bytes) -> str:
        """解码字节串为文本

        ★ 修复（真实压测发现）：UTF-16/UTF-32 文件的 BOM 被当成**正文**读入

            `BOMS` 把 `b'\\xff\\xfe'` 映射到 `'utf-16-le'` 这类**裸端序编码**，
            而这类编码**不会剥离 BOM** —— 解出来的第一个字符就是
            `U+FEFF`（不可见的 BOM）。对比之下 `'utf-8-sig'` 会自动剥离，
            所以只有 UTF-16/32 有这个不对称问题。

            实测：一个 32 字符的 UTF-16LE 文件被读成 **33** 字符，
            首字符 `U+FEFF`。文本内容看起来"没坏"，但：

            * 搜索/替换/正则的第一个字符位置全部偏移；
            * 若是 JSON/XML/源代码，多出的 BOM 字符会让解析器报错；
            * 行级 diff 会把首行判为"已修改"。

            这里在解码后剥掉**开头**的 BOM（仅首字符，不动正文里的
            U+FEFF —— 正文里的同码位字符是合法的）。`encode()` 用同一
            裸端序编码，不会再补 BOM，所以**保存后的字节仍与原文件一致**。
        """
        try:
            text = data.decode(self._encoding, errors='replace')
        except (LookupError, UnicodeDecodeError):
            text = data.decode(ENCODING_UTF8, errors='replace')
        return _strip_leading_bom(text, self._encoding)

    def encode(self, text: str) -> bytes:
        """编码文本为字节串（**保留原文件的 BOM**）

        ★ 真实缺陷（混合场景压测实测发现）：

            UTF-16 LE/BE 文件打开 → 编辑 → 保存后，**BOM 丢了**：

                原: b'\\xff\\xfe' + '中文\\n'.encode('utf-16-le')
                新: 'Z中文\\n'.encode('utf-16-le')      ← 无 BOM

            原因：`BOMS` 把 BOM 映射到**裸端序编码**（`utf-16-le` /
            `utf-32-be` 等）以便逐字节保真，而这类编码的 `str.encode()`
            **不会补 BOM**。于是"没改动直接保存"时字节不变（保存被跳过），
            一旦编辑过就丢了 BOM。

            后果不只是少三个字节：很多工具（记事本/Excel/某些编译器）
            靠 BOM 判断 UTF-16 的端序与"这是 Unicode 文本"，
            丢 BOM 后可能被当成 ANSI 或二进制。

        修复：若原文件带 BOM（`_has_bom`）且编码是裸端序，
        编码后把对应 BOM 补回开头。`utf-8-sig` / `utf-16` 这类
        自带 BOM 的编码不受影响（避免双 BOM）。
        """
        try:
            data = text.encode(self._encoding, errors='replace')
        except (LookupError, UnicodeEncodeError):
            return text.encode(ENCODING_UTF8, errors='replace')

        if not getattr(self, '_has_bom', False):
            return data

        encoding = (self._encoding or '').lower()
        bom = _BARE_ENDIAN_BOM.get(encoding)
        if not bom:
            # 这些编码的 encoder 自己会加 BOM，不能再补
            return data
        if data.startswith(bom):
            return data
        return bom + data

    def get_dirty_blocks(self) -> Dict[int, bytes]:
        """获取所有脏块"""
        return dict(self._dirty_blocks)

    def clear_dirty(self):
        """清空脏块标记"""
        self._dirty_blocks.clear()
        if self._state == FileState.MODIFIED:
            self._state = FileState.OPENED

    def get_info(self) -> Dict[str, Any]:
        """获取提供者信息摘要"""
        return {
            'class': self.__class__.__name__,
            'filepath': self._filepath,
            'size': self._size,
            'block_size': self._block_size,
            'total_blocks': self._total_blocks,
            'encoding': self._encoding,
            'eol': repr(self._eol),
            'has_bom': self._has_bom,
            'readonly': self._readonly,
            'modified': self.is_modified,
            'dirty_blocks': self.dirty_block_count,
            'state': self._state.name,
        }

    def __repr__(self) -> str:
        return (f"<{self.__class__.__name__} "
                f"path={self._filepath!r} "
                f"size={self._size} "
                f"encoding={self._encoding} "
                f"state={self._state.name}>")


# ============================================================
# 本地文件提供者
# ============================================================
class LocalFileProvider(ContentProvider):
    """
    本地文件提供者。

    使用 mmap 实现高效的大文件访问，支持：
    - 分块读取
    - 脏块缓冲
    - 原子保存
    - 自动编码检测
    - BOM 处理
    - 行尾符检测
    - 只读保护
    """

    def __init__(self, block_size: int = DEFAULT_BLOCK_SIZE):
        super().__init__()
        self._block_size = max(MIN_BLOCK_SIZE,
                               min(block_size, MAX_BLOCK_SIZE))

        # 文件句柄
        self._file: Optional[io.BufferedRandom] = None
        self._mmap: Optional[mmap.mmap] = None

        # 缓存已加载的块
        self._loaded_blocks: set = set()

    # --------------------------------------------------------
    # 打开文件
    # --------------------------------------------------------
    def open(self, source: str, encoding: Optional[str] = None,
             readonly: bool = False, detect_encoding: bool = True,
             block_size: Optional[int] = None) -> bool:
        """
        打开本地文件。

        参数:
            source: 文件路径
            encoding: 指定编码（None 则自动检测）
            readonly: 是否以只读模式打开
            detect_encoding: 是否自动检测编码
            block_size: 覆盖默认块大小

        返回:
            是否成功

        异常:
            FileNotFoundError: 文件不存在
            PermissionDeniedError: 权限不足
        """
        # 关闭之前的文件
        if self.is_open:
            self.close()

        if not os.path.exists(source):
            raise FileNotFoundError(f"文件不存在: {source}")

        if not os.path.isfile(source):
            raise FileNotFoundError(f"路径不是文件: {source}")

        self._filepath = os.path.abspath(source)

        if block_size:
            self._block_size = max(MIN_BLOCK_SIZE,
                                   min(block_size, MAX_BLOCK_SIZE))

        # 检查权限
        try:
            st = os.stat(self._filepath)
            self._readonly = readonly or not os.access(self._filepath, os.W_OK)
            # 记住"磁盘上是否可写"，用于需要写入时把映射升级为读写
            self._can_write = os.access(self._filepath, os.W_OK)
            self._size = st.st_size
            self._mtime = st.st_mtime
        except PermissionError as e:
            raise PermissionDeniedError(f"无法访问文件: {e}")

        # 打开文件句柄
        #
        # 关键（Windows 文件锁定缺陷）：
        #   原先在文件可写时用 `'r+b'` + `mmap.ACCESS_WRITE`，并且**一直
        #   持有**该映射。Windows 上写模式的内存映射会**独占锁定文件** ——
        #   于是编辑器一打开文件，其它程序（git、构建工具、另一个编辑器）
        #   就再也无法修改它，直到本编辑器关闭该文件。
        #
        #   这直接让"外部文件变更检测/三方合并"失去意义：那种情况**永远
        #   不会发生**。实测：打开文件后 `Path.write_text()` 抛
        #   `OSError: [Errno 22] Invalid argument`。
        #
        #   现在**默认只读打开**（共享读，不阻断外部写入）；只有真正需要
        #   就地写入脏块时才由 `_ensure_writable()` 升级为读写映射，
        #   且写入完成后即可释放（见 `release_write_handle()`）。
        try:
            self._file = open(self._filepath, 'rb')
        except PermissionError as e:
            raise PermissionDeniedError(f"无法打开文件: {e}")

        # 创建 mmap（默认只读 —— 不锁文件）
        #
        # 只对**大文件**建映射（与 `read_block` / `_ensure_handle` 一致）。
        # 小文件直接 read() 的开销可忽略，而且**不建立映射就不会锁住文件**
        # —— Windows 上即使只读映射也会阻止外部程序覆盖写，那会让
        # "外部变更检测 / 三方合并"永远不会触发。
        if self._size > MMAP_MIN_SIZE:
            try:
                self._mmap = mmap.mmap(
                    self._file.fileno(), 0, access=mmap.ACCESS_READ
                )
            except (ValueError, OSError) as e:
                # 空文件或无法映射
                self._mmap = None

        # 计算总块数
        self._total_blocks = max(
            1,
            (self._size + self._block_size - 1) // self._block_size
        )

        # 检测编码和行尾符
        self._detect_encoding_and_eol(encoding, detect_encoding)

        # 初始化状态
        self._dirty_blocks.clear()
        self._loaded_blocks.clear()
        self._state = FileState.READONLY if self._readonly else FileState.OPENED

        return True

    # --------------------------------------------------------
    # 编码与行尾符检测
    # --------------------------------------------------------
    def _detect_encoding_and_eol(self, forced_encoding: Optional[str],
                                 detect: bool):
        """检测编码和行尾符"""
        # 读取文件头部样本
        sample_size = min(4096, self._size)
        sample = b''

        if sample_size > 0:
            if self._mmap:
                sample = self._mmap[:sample_size]
            elif self._file:
                self._file.seek(0)
                sample = self._file.read(sample_size)
                self._file.seek(0)

        # 1. BOM 检测
        self._has_bom = False
        for bom, enc in BOMS.items():
            if sample.startswith(bom):
                self._encoding = enc
                self._has_bom = True
                break

        # 2. 指定编码
        if not self._has_bom and forced_encoding:
            self._encoding = forced_encoding

        # 3. 自动检测
        elif not self._has_bom and detect:
            self._encoding = self._detect_encoding(sample)
            # 3b. ASCII 必须验证**整个文件**（P0-A 相关修复）
            #
            # 缺陷背景（实测）：采样只有 4096 字节，若前 4KB 全是 ASCII
            # 而后面才是中文，chardet 会高置信度地判成 ascii。随后
            #   decode(errors='replace') → 汉字变 U+FFFD
            #   encode(errors='replace') → U+FFFD 变 '?'（ascii 下不可编码）
            # 于是**一保存整个文件的中文全部被销毁**。
            #
            # 因此：只有当 ASCII 声明在整个文件上都成立时才接受它。
            if self._encoding == ENCODING_ASCII and self._size > len(sample):
                if self._has_non_ascii_beyond(sample):
                    # 在后续内容上重新检测（含非 ASCII 字节，chardet 能识别）
                    tail = self._read_verify_bytes()
                    self._encoding = self._detect_encoding(tail)

        # 4. 行尾符检测
        self._eol = self._detect_eol(sample)

    def _detect_encoding(self, sample: bytes) -> str:
        """
        自动检测编码。

        优先使用 chardet，其次使用简单启发式规则。
        """
        if not sample:
            return ENCODING_UTF8

        # 尝试使用 chardet
        try:
            import chardet
            result = chardet.detect(sample)
            if result and result.get('confidence', 0) > 0.7:
                enc = result['encoding']
                if enc:
                    # 规范化编码名
                    enc = enc.lower().replace('_', '-')
                    if enc == 'ascii':
                        return ENCODING_ASCII
                    return enc
        except ImportError:
            pass
        except Exception:
            pass

        # 简单启发式规则
        # 1. 尝试 UTF-8
        try:
            sample.decode('utf-8')
            return ENCODING_UTF8
        except UnicodeDecodeError:
            pass

        # 2. 尝试 GBK
        try:
            sample.decode('gbk')
            return ENCODING_GBK
        except UnicodeDecodeError:
            pass

        # 3. 尝试 Latin-1（永远成功）
        return ENCODING_LATIN1

    # 验证 ASCII 声明时要扫描的最大字节数（避免大文件全量扫描拖慢打开）
    _ASCII_VERIFY_LIMIT = 32 * 1024 * 1024

    def _read_verify_bytes(self) -> bytes:
        """读取用于编码复检的字节（跳过已采样的头部）

        优先返回**含非 ASCII 字节**的那一小段，这样 chardet 才能据此
        判出真实编码；全部都是 ASCII 时返回空 bytes。
        """
        try:
            if self._size <= self._ASCII_VERIFY_LIMIT:
                if self._mmap:
                    return bytes(self._mmap[:])
                if self._file:
                    pos = self._file.tell()
                    self._file.seek(0)
                    data = self._file.read()
                    self._file.seek(pos)
                    return data
        except Exception:
            pass

        # 大文件：分块扫描，返回第一个含非 ASCII 字节的块
        chunk = 256 * 1024
        try:
            src = self._mmap
            if src is not None:
                for off in range(0, self._size, chunk):
                    part = bytes(src[off:off + chunk])
                    if not part.isascii():        # C 实现，见下方说明
                        return part
                return b''
            if self._file:
                pos = self._file.tell()
                self._file.seek(0)
                for _ in range(0, self._size, chunk):
                    part = self._file.read(chunk)
                    if not part:
                        break
                    if not part.isascii():        # C 实现，见下方说明
                        return part
                self._file.seek(pos)
        except Exception:
            pass
        return b''

    def _has_non_ascii_beyond(self, sample: bytes) -> bool:
        """检查采样之后的文件内容里是否存在非 ASCII 字节

        ★ 性能缺陷（大文件打开 4~12s 的**真正根因**，cProfile 实测）：

            原实现用 `any(b > 127 for b in part)` 判断。这是**纯 Python
            逐字节生成器**：每字节一次生成器迭代 + 比较。对 10MB 文件，
            `_ASCII_VERIFY_LIMIT` 是 32MB，因此会扫描整个文件
            —— 实测 **2080 万次生成器调用、约 11 秒**，
            而 QScintilla 真正的 `setText` 只要 **0.22 秒**。

        修复：`bytes.isascii()` 是 CPython 的 **C 实现**（3.7+），
        语义完全等价（所有字节 < 128），速度快 2~3 个数量级。
        """
        try:
            if self._mmap:
                start = len(sample)
                end = min(self._size, start + self._ASCII_VERIFY_LIMIT)
                part = bytes(self._mmap[start:end])
                return not part.isascii()
            if self._file:
                pos = self._file.tell()
                self._file.seek(len(sample))
                remaining = min(self._size - len(sample),
                                self._ASCII_VERIFY_LIMIT)
                found = False
                while remaining > 0:
                    part = self._file.read(min(256 * 1024, remaining))
                    if not part:
                        break
                    remaining -= len(part)
                    if not part.isascii():        # C 实现，见下方说明
                        found = True
                        break
                self._file.seek(pos)
                return found
        except Exception:
            pass
        # 检测失败时保守认为"可能存在非 ASCII"，避免误判为 ascii
        return True

    def _detect_eol(self, sample: bytes) -> str:
        """检测行尾符"""
        if not sample:
            return EOL_LF

        crlf_count = sample.count(b'\r\n')
        lf_count = sample.count(b'\n') - crlf_count
        cr_count = sample.count(b'\r') - crlf_count

        if crlf_count >= lf_count and crlf_count >= cr_count:
            return EOL_CRLF
        elif cr_count > lf_count:
            return EOL_CR
        return EOL_LF

    # --------------------------------------------------------
    # 块读取
    # --------------------------------------------------------
    def read_block(self, block_id: int) -> bytes:
        """
        读取指定块。

        参数:
            block_id: 块索引（从 0 开始）

        返回:
            块的字节内容（**完整字符对齐**，不会以半个多字节字符结尾）

        注意（P0-A 修复）：
            原先固定按 `block_id * block_size` 切分，横跨边界的 UTF-8
            字符会被解码成 U+FFFD 并在保存时永久损坏原文件。
            现在使用 `_aligned_block_bounds()` 返回的字符对齐边界。
        """
        if not self.is_open:
            raise ProviderClosedError("提供者未打开")

        if block_id < 0 or block_id >= self._total_blocks:
            return b''

        # 优先返回脏块
        if block_id in self._dirty_blocks:
            return bytes(self._dirty_blocks[block_id])

        # 字符对齐边界（多字节编码下避免跨块损坏；单字节编码下等同于原偏移）
        if self._needs_boundary_alignment():
            bounds = self._aligned_block_bounds()
            if block_id < len(bounds):
                start, end = bounds[block_id]
            else:
                start = block_id * self._block_size
                end = min(start + self._block_size, self._size)
        else:
            start = block_id * self._block_size
            end = min(start + self._block_size, self._size)

        if start >= self._size:
            return b''

        # 按需重建句柄/映射（release_mmap 之后仍能快速读取）
        #
        # 只对**大文件**建立映射：小文件直接读更快，而且不留驻映射就
        # 不会锁住文件（Windows 上映射会阻止外部程序覆盖写）。
        # 这是"外部变更检测/三方合并"能真正触发的前提。
        if self._size <= MMAP_MIN_SIZE:
            if self._file is None or self._file.closed:
                self._ensure_handle()
            if self._file:
                try:
                    self._file.seek(start)
                    data = self._file.read(end - start)
                    self._loaded_blocks.add(block_id)
                    return data
                except (ValueError, OSError):
                    pass
        else:
            if self._file is None or self._mmap is None:
                self._ensure_handle()

        # mmap 读取
        if self._mmap:
            try:
                data = self._mmap[start:end]
                self._loaded_blocks.add(block_id)
                return data
            except (ValueError, OSError):
                pass

        # 回退到文件读取
        if self._file:
            try:
                self._file.seek(start)
                data = self._file.read(end - start)
                self._loaded_blocks.add(block_id)
                return data
            except Exception as e:
                print(f"[LocalFileProvider] 读取失败: {e}")

        return b''

    # --------------------------------------------------------
    # 块写入
    # --------------------------------------------------------
    def write_block(self, block_id: int, data: bytes) -> bool:
        """
        写入指定块（写入脏块缓冲区，不立即落盘）。

        参数:
            block_id: 块索引
            data: 新的字节内容

        返回:
            是否成功
        """
        if not self.is_open:
            raise ProviderClosedError("提供者未打开")

        if self._readonly:
            return False

        if block_id < 0 or block_id >= self._total_blocks:
            return False

        self._dirty_blocks[block_id] = bytearray(data)
        self._state = FileState.MODIFIED

        # 内存限制：脏块过多时提示
        if len(self._dirty_blocks) > MAX_LOADED_BLOCKS:
            print(f"[LocalFileProvider] 警告: 脏块数量过多 "
                  f"({len(self._dirty_blocks)})")

        return True

    def write_text(self, text: str, block_id: int = 0):
        """写入文本到指定块（便捷方法）"""
        self.write_block(block_id, self.encode(text))

    # --------------------------------------------------------
    # 保存
    # --------------------------------------------------------
    def save(self, filepath: Optional[str] = None) -> bool:
        """
        持久化内容到磁盘。**始终使用原子写入**（临时文件 + fsync + 替换），
        因此中途失败（磁盘满、断电、进程被杀）都不会损坏原文件。

        参数:
            filepath: 另存为路径（None 则覆盖原文件）

        返回:
            是否成功

        修复记录（P1-D，原实现与 docstring 不符）：
            原 docstring 声称"使用原子写入（临时文件 + 重命名）避免中途失败
            损坏文件"，但实际只有"另存为不同路径"才走 `_save_as_full()`；
            常规覆盖保存走的是 `_save_dirty_blocks()` —— 那是**原地写**：
                open(target, 'r+b') -> seek/write -> truncate(new_size)
            没有任何临时文件或备份副本。

            更严重的是上层 `EditorProxy._sync_content_to_provider()` 在保存前
            会把**全部块**标脏，所以每次 Ctrl+S 实际上都是"整文件原地重写"。
            一旦在写盘过程中失败，原文件已被截断/覆盖，用户数据无法回退。

            现在无条件走 `_save_as_full()`。代价是每次都重写整个文件
            （本来也是这样），换来的是"要么全成、要么原文件不动"。
        """
        if not self.is_open:
            raise ProviderClosedError("提供者未打开")

        if self._readonly:
            raise PermissionDeniedError("文件为只读")

        if not self._dirty_blocks and filepath is None:
            # 无修改，无需保存
            return True

        target = filepath or self._filepath
        if not target:
            return False

        target = os.path.abspath(target)

        try:
            # 统一走原子全量写入（含 mkstemp + fsync + os.replace）
            return self._save_as_full(target)

        except Exception as e:
            print(f"[LocalFileProvider] 保存失败: {e}")
            return False

    def _save_dirty_blocks(self, target: str) -> bool:
        """仅写入脏块（原地更新）。

        A4 修复：先释放 mmap 再开文件。

        原实现在写完脏块后才 mmap.flush()，但在写入过程中
        mmap 仍持有文件映射。Windows 上 open('r+b') 会因
        文件被 mmap 锁定而抛 PermissionError。Linux/macOS
        允许，但 flush 语义也不可靠。

        A5 修复（数据损坏）：
            原实现只按块 seek+write，**从不截断文件**。当新
            内容比原文件短时，新内容之后会残留旧字节，重新
            打开文件会看到"已删除的内容又回来了"。
            例如把 55890 字节的文件删到 12 字节后保存，
            文件仍是 55890 字节（新内容 + 旧尾部）。

            修复方法：按脏块内容计算出真实长度 new_size，
            写完后若 new_size < 原大小则 f.truncate(new_size)，
            并用 new_size 覆盖 self._size，保证内存状态与磁盘
            一致后重建 mmap。

        修复流程：
            1. 先 mmap.flush() + mmap.close()，释放文件锁
            2. open('r+b') 写脏块 + 按新长度截断
            3. 重新建立 mmap（保持 provider 可读）
        """
        # ---- 1. 释放 mmap ----
        if self._mmap:
            try:
                self._mmap.flush()
                self._mmap.close()
            except Exception:
                pass
            self._mmap = None

        # 落盘后的真实长度（脏块覆盖范围的最大末尾）
        new_size = 0
        for block_id, data in self._dirty_blocks.items():
            new_size = max(
                new_size, block_id * self._block_size + len(data)
            )

        # ---- 2. 写脏块 + 截断 ----
        try:
            # 使用可写文件句柄
            with open(target, 'r+b') as f:
                for block_id, data in self._dirty_blocks.items():
                    offset = block_id * self._block_size
                    f.seek(offset)
                    f.write(bytes(data))

                # A5: 内容变短时必须截断，否则旧字节残留在尾部。
                # 注意：必须用磁盘上的真实大小比较，不能用
                # self._size —— 编辑器在保存前会先调用
                # _replace_full_content()，那里已经把 self._size
                # 改成了新长度，用它比较会漏掉截断。
                try:
                    on_disk = os.fstat(f.fileno()).st_size
                except Exception:
                    on_disk = self._size
                if new_size < on_disk:
                    f.truncate(new_size)

                f.flush()
                os.fsync(f.fileno())

            # 更新状态
            self._dirty_blocks.clear()
            self._state = (FileState.READONLY if self._readonly
                           else FileState.OPENED)

            # 更新 mtime / size（size 以磁盘实际大小为准）
            self._size = new_size
            self._total_blocks = max(
                1,
                (new_size + self._block_size - 1) // self._block_size
            )
            try:
                self._mtime = os.path.getmtime(target)
                self._size = os.path.getsize(target)
            except Exception:
                pass

            # ---- 3. 重建 mmap ----
            self._reopen_mmap()

            return True

        except Exception as e:
            print(f"[LocalFileProvider] 脏块保存失败: {e}")
            # 失败时也要尽量恢复 mmap 状态
            self._mmap = None
            self._reopen_mmap()
            return False

    def release_mmap(self):
        """释放内存映射（保留文件描述符与全部状态）

        为什么需要（Windows 文件锁定）：
            即使只读的 `mmap` 也会**阻止文件被另一进程覆盖写**（`open(w)`
            截断会失败，报 `OSError: [Errno 22] Invalid argument`）。
            于是"编辑器打开着某个文件"就足以让 git / 构建工具 / 其它编辑器
            无法修改它 —— 外部变更检测与三方合并永远不会触发。

            因此把映射做成**可释放**的：读取时存在（快），需要让外部程序
            写入（保存后、检测变更前、重新加载后）就释放；`read_block()`
            在无映射时会回退到文件读取，所以释放后功能完全不受影响。

        注意：文件描述符也一起释放 —— Windows 上"读句柄"同样会阻止
        `open(path, 'w')` 截断。

        安全说明：小文件（<= `MMAP_MIN_SIZE`）本就不建立映射，因此本方法
        对它们只关句柄；大文件才需要真正解开映射。映射的显式 `close()`
        在 Qt 事件循环下曾经引发段错误（0xC0000005），所以这里改为
        **丢弃引用**，由 CPython 的 mmap 析构器安全回收（析构本身是安全的，
        危险的是与 Qt 视图生命周期交织时的提前显式关闭）。
        """
        self._mmap = None
        fh = self._file
        self._file = None
        if fh is not None:
            try:
                if not getattr(fh, 'closed', True):
                    fh.close()
            except Exception:
                pass

    def _ensure_handle(self) -> bool:
        """确保文件句柄与 mmap 可用（按需重建）

        `release_mmap()` 之后调用本方法即可恢复快速读取路径。
        重建使用**只读**模式（写模式会锁文件，见 `open` 的说明）。
        """
        if not self._filepath or not os.path.exists(self._filepath):
            return False
        try:
            if self._file is None or self._file.closed:
                self._file = open(self._filepath, 'rb')
            # 只对大文件建映射：小文件不留驻映射，避免锁住文件
            # （Windows 上映射会阻止外部程序覆盖写）。
            if (self._mmap is None and self._size > MMAP_MIN_SIZE):
                try:
                    self._mmap = mmap.mmap(
                        self._file.fileno(), 0, access=mmap.ACCESS_READ
                    )
                except (ValueError, OSError) as e:
                    logger.debug("重建 mmap 失败: %s", e)
            return True
        except Exception as e:
            logger.debug("重建文件句柄失败: %s", e)
            return False

    def _reopen_mmap(self):
        """重建 mmap（A4 新增，供 _save_dirty_blocks 内部调用）。

        在关闭 mmap 写盘后调用，保持 provider 后续读操作可用。

        A5 修复：调用前先显式把 self._mmap 置 None，避免
        0 长度文件（self._size <= 0 提前返回）时残留已关闭的
        mmap 对象，导致后续 read_block 对已关闭映射取值。
        """
        if not self._file:
            return

        # 已关闭的 mmap 必须先丢弃
        if self._mmap is not None:
            try:
                self._mmap.close()
            except Exception:
                pass
            self._mmap = None

        if self._size <= 0:
            return
        try:
            # 一律只读映射：写映射会独占锁住文件（Windows），使外部程序
            # 无法修改已打开的文件 —— 那样"外部变更"永远不会发生。
            # 写入路径不依赖写映射（见 `_save_as_full` 的原子替换）。
            self._mmap = mmap.mmap(
                self._file.fileno(), 0, access=mmap.ACCESS_READ
            )
        except (ValueError, OSError):
            self._mmap = None

    def _apply_eol(self, data: bytes) -> bytes:
        """按用户显式设置的行尾符转换（保存时调用）

        缺陷背景（INV-E1，已由审计测试复现）：
            `Document.set_eol()` 只改 `meta.eol` + 标脏，其 docstring 声称
            "实际转换在保存时进行"，但**保存路径从不做转换**；
            `Document.convert_eol()` 在生产代码里**零调用**；
            `encode()` 也不碰行尾。于是用户在状态栏把 LF 切成 CRLF、
            保存后磁盘上仍是 LF —— 设置完全不生效。

        ⚠️ 只在 `_eol_explicit` 为真时转换（关键）：
            `_eol` 在打开文件时由探测得出，而探测**并不可靠** ——
            例如整篇没有换行的文件，`crlf_count(0) >= lf_count(0)` 成立，
            会默认取 CRLF。若无条件按 `_eol` 转换，这种文件的保存会把
            **原文根本没有的换行**改写掉（实测曾让 `'short\n'` 变成
            `'short\r\n'`，破坏了"保存不改动内容"的不变量）。
            因此只有用户**显式切换过**行尾才转换。

        实现说明（为什么在文本层而非字节层转换）：
            - 文本层转换对**任何**编码都正确；字节层替换会在 UTF-16 等
              编码下破坏数据（其中换行是 0x000A 两字节）。
            - 编码仍统一走 `self.encode()`，保证与保存路径一致。
        """
        if not getattr(self, '_eol_explicit', False):
            return data
        try:
            target = self._eol or EOL_LF
        except Exception:
            return data
        if target == EOL_LF:
            # 用户显式选了 LF：也需要把内容里的 CRLF 归一为 LF
            target = EOL_LF
        try:
            text = self.decode(data)
        except Exception:
            return data
        normalized = text.replace('\r\n', '\n').replace('\r', '\n')
        if target == EOL_CRLF:
            converted = normalized.replace('\n', '\r\n')
        elif target == EOL_CR:
            converted = normalized.replace('\n', '\r')
        elif target == EOL_LF:
            converted = normalized
        else:
            return data
        if converted == text:
            return data
        return self.encode(converted)

    def _replace_with_retry(self, tmp_path: str, target: str,
                            attempts: int = 10, base_delay: float = 0.02):
        """用重试的方式把临时文件替换为目标文件（Windows 必需）

        ★ 真实缺陷（混合场景压测实测发现）：

            连续"打开 → 编辑 → 保存"时，`os.replace(tmp, target)` 会**间歇性**
            抛 `PermissionError: [WinError 5] 拒绝访问`，保存直接失败。
            实测频率不低（6 轮里 1~4 轮失败），且**与文件监视器、
            自动保存无关**（两者都关掉后仍复现）—— 属于 Windows 上
            临时性共享冲突（杀毒软件/索引服务/搜索索引会在文件刚写入时
            短暂持有句柄）。

            失败时数据没丢（脏块保留、`save_file()` 返回 False），
            但用户按 Ctrl+S 会**静默失败**，这是不可接受的。

            修复：短退避重试（10 次 × 递增 20ms，总计约 1.1 秒）。
            这是 Windows 上处理"临时性共享冲突"的标准做法 ——
            不掩盖权限问题（持续失败仍会抛出并返回 False），
            只吸收毫秒级的瞬态占用。
        """
        last_error = None
        for i in range(max(1, attempts)):
            try:
                os.replace(tmp_path, target)
                if i:
                    print("[LocalFileProvider] 保存重试第 %d 次成功" % i)
                return True
            except PermissionError as e:
                last_error = e
                time.sleep(base_delay * (i + 1))
            except OSError as e:
                # Windows 上"共享冲突"有时表现为 WinError 32
                if getattr(e, "winerror", None) == 32:
                    last_error = e
                    time.sleep(base_delay * (i + 1))
                else:
                    raise
        if last_error is not None:
            raise last_error
        return False

    def _save_as_full(self, target: str) -> bool:
        """另存为完整文件（原子写入）"""
        import tempfile

        try:
            # 读取所有内容（含脏块）
            full_data = self.read_all()

            # 按文档设置的行尾符转换后再落盘（INV-E1 修复）
            full_data = self._apply_eol(full_data)

            # A5 修复：os.replace/rename 会替换 inode，而
            # self._file 仍指向旧 inode（POSIX 下即已被删除的
            # 文件），后续 mmap 重建会映射到旧内容。
            # 因此在替换前先释放 mmap + 文件句柄。
            if self._mmap:
                try:
                    self._mmap.flush()
                    self._mmap.close()
                except Exception:
                    pass
                self._mmap = None

            if self._file:
                try:
                    self._file.close()
                except Exception:
                    pass
                self._file = None

            # 写入临时文件
            dirpath = os.path.dirname(target)
            os.makedirs(dirpath, exist_ok=True)

            fd, tmp_path = tempfile.mkstemp(
                dir=dirpath, prefix='.qingcao_save_', suffix='.tmp'
            )
            try:
                with os.fdopen(fd, 'wb') as f:
                    f.write(full_data)
                    f.flush()
                    os.fsync(f.fileno())

                # 原子重命名（带瞬态占用重试，见 `_replace_with_retry`）
                self._replace_with_retry(tmp_path, target)

            except Exception:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                raise

            # 更新状态
            self._dirty_blocks.clear()
            self._filepath = target
            self._state = FileState.OPENED
            self._total_blocks = max(
                1,
                (len(full_data) + self._block_size - 1) // self._block_size
            )
            try:
                self._mtime = os.path.getmtime(target)
                self._size = os.path.getsize(target)
            except Exception:
                pass

            # A5: 重新打开新 inode 并重建 mmap，保证后续读取正确
            self._reopen_file_handle()
            self._reopen_mmap()

            return True

        except Exception as e:
            print(f"[LocalFileProvider] 另存为失败: {e}")
            # 尽量恢复可用状态
            try:
                self._reopen_file_handle()
                self._reopen_mmap()
            except Exception:
                pass
            return False

    def _reopen_file_handle(self) -> bool:
        """重新打开文件句柄（另存为替换 inode 后使用）。

        返回:
            是否成功重新打开
        """
        if not self._filepath:
            return False
        try:
            # 始终只读打开：写模式下 Windows 会独占锁住文件，
            # 使外部程序（git / 构建工具 / 其它编辑器）无法修改它，
            # 从而让"外部变更检测"永远失效。写入走
            # `_save_as_full` 的临时文件 + 原子替换，不需要写模式句柄。
            self._file = open(self._filepath, 'rb')
            return True
        except Exception as e:
            print(f"[LocalFileProvider] 重开文件句柄失败: {e}")
            self._file = None
            return False

    # --------------------------------------------------------
    # 关闭
    # --------------------------------------------------------
    def close(self):
        """关闭文件并释放资源"""
        # 关闭 mmap
        if self._mmap:
            try:
                self._mmap.close()
            except Exception:
                pass
            self._mmap = None

        # 关闭文件句柄
        if self._file:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None

        # 清空状态
        self._dirty_blocks.clear()
        self._loaded_blocks.clear()
        self._state = FileState.CLOSED

    # --------------------------------------------------------
    # 文件变更检测
    # --------------------------------------------------------
    def check_external_change(self) -> bool:
        """
        检查文件是否被外部程序修改。

        返回:
            True 表示文件已被外部修改
        """
        if not self._filepath or not os.path.exists(self._filepath):
            return False

        try:
            current_mtime = os.path.getmtime(self._filepath)
            return abs(current_mtime - self._mtime) > 0.001
        except Exception as e:
            # 不能把"检查失败"当成"没被改过"（fail-open）：
            # 那样外部篡改会被静默忽略，用户下次保存就覆盖掉别人的修改。
            # 这里改为**保守判定为已变更**（fail-safe），并把原因打出来。
            print(f"[LocalFileProvider] 外部变更检查失败（保守判定为已变更）: {e}")
            return True

    def reload(self) -> bool:
        """重新加载文件内容"""
        if not self._filepath:
            return False
        filepath = self._filepath
        encoding = self._encoding
        readonly = self._readonly

        self.close()
        try:
            self.open(filepath, encoding=encoding, readonly=readonly,
                      detect_encoding=False)
            return True
        except Exception as e:
            print(f"[LocalFileProvider] 重新加载失败: {e}")
            return False

    # --------------------------------------------------------
    # 文件信息
    # --------------------------------------------------------
    def get_file_info(self) -> Dict[str, Any]:
        """获取文件详细信息"""
        info = self.get_info()
        info.update({
            'file_size': self._size,
            'file_size_mb': round(self._size / 1024 / 1024, 2),
            'mtime': self._mtime,
            'is_large': self._size > LARGE_FILE_THRESHOLD,
            'is_huge': self._size > HUGE_FILE_THRESHOLD,
            'loaded_blocks': len(self._loaded_blocks),
            'readonly_reason': (
                '用户指定' if self._readonly and not os.access(
                    self._filepath or '', os.W_OK
                ) else '文件权限' if self._readonly else None
            ),
        })
        return info

    def get_readonly_status(self) -> bool:
        """返回是否只读"""
        return self._readonly

    def set_readonly(self, readonly: bool) -> bool:
        """设置只读状态"""
        if not self._filepath:
            return False

        if readonly:
            self._readonly = True
            self._state = FileState.READONLY
            return True

        # 尝试切换为可写
        if not os.access(self._filepath, os.W_OK):
            return False

        self._readonly = False
        if self._state == FileState.READONLY:
            self._state = FileState.OPENED
        return True


# ============================================================
# 内存提供者
# ============================================================
class MemoryProvider(ContentProvider):
    """
    内存内容提供者。

    用于临时缓冲区、未保存文档、剪贴板缓冲区等场景。
    """

    def __init__(self, block_size: int = DEFAULT_BLOCK_SIZE):
        super().__init__()
        self._block_size = block_size
        self._buffer: bytearray = bytearray()
        self._state = FileState.CLOSED

    def open(self, source: Any = None, initial_text: str = '',
             encoding: str = ENCODING_UTF8, **kwargs) -> bool:
        """
        打开内存缓冲区。

        参数:
            source: 忽略（保留接口兼容）
            initial_text: 初始文本
            encoding: 编码
        """
        self._filepath = None
        self._encoding = encoding
        self._readonly = False

        if initial_text:
            self._buffer = bytearray(self.encode(initial_text))
        else:
            self._buffer = bytearray()

        self._size = len(self._buffer)
        self._total_blocks = max(
            1,
            (self._size + self._block_size - 1) // self._block_size
        )

        self._state = FileState.OPENED
        self._dirty_blocks.clear()

        return True

    def read_block(self, block_id: int) -> bytes:
        """读取指定块"""
        if self._state == FileState.CLOSED:
            raise ProviderClosedError("提供者未打开")

        if block_id in self._dirty_blocks:
            return bytes(self._dirty_blocks[block_id])

        start = block_id * self._block_size
        end = min(start + self._block_size, len(self._buffer))
        if start >= len(self._buffer):
            return b''
        return bytes(self._buffer[start:end])

    def write_block(self, block_id: int, data: bytes) -> bool:
        """写入指定块"""
        if self._state == FileState.CLOSED:
            raise ProviderClosedError("提供者未打开")

        self._dirty_blocks[block_id] = bytearray(data)
        self._state = FileState.MODIFIED

        # 立即更新内存缓冲区
        start = block_id * self._block_size
        end = start + len(data)

        # 扩展缓冲区
        if end > len(self._buffer):
            self._buffer.extend(b'\x00' * (end - len(self._buffer)))

        self._buffer[start:end] = data
        self._size = len(self._buffer)
        self._total_blocks = max(
            1,
            (self._size + self._block_size - 1) // self._block_size
        )

        return True

    def save(self, filepath: Optional[str] = None) -> bool:
        """
        保存内存内容。

        参数:
            filepath: 如果提供，则另存为本地文件
        """
        if filepath:
            try:
                os.makedirs(
                    os.path.dirname(os.path.abspath(filepath)) or '.',
                    exist_ok=True
                )
                with open(filepath, 'wb') as f:
                    f.write(bytes(self._buffer))
                self._filepath = os.path.abspath(filepath)
                self._dirty_blocks.clear()
                self._state = FileState.OPENED
                return True
            except Exception as e:
                print(f"[MemoryProvider] 另存为失败: {e}")
                return False

        # 无路径则仅清空脏块
        self._dirty_blocks.clear()
        self._state = FileState.OPENED
        return True

    def close(self):
        """清空缓冲区"""
        self._buffer.clear()
        self._dirty_blocks.clear()
        self._state = FileState.CLOSED

    def set_text(self, text: str):
        """设置全部文本（重新分配缓冲区）"""
        self._buffer = bytearray(self.encode(text))
        self._size = len(self._buffer)
        self._total_blocks = max(
            1,
            (self._size + self._block_size - 1) // self._block_size
        )
        self._dirty_blocks.clear()
        if self._state == FileState.CLOSED:
            self._state = FileState.OPENED

    def get_text(self) -> str:
        """获取全部文本"""
        return self.decode(bytes(self._buffer))

    def __repr__(self) -> str:
        return (f"<MemoryProvider size={self._size} "
                f"blocks={self._total_blocks} "
                f"state={self._state.name}>")


# ============================================================
# 流式提供者
# ============================================================
class StreamProvider(ContentProvider):
    """
    流式内容提供者。

    用于 stdin、网络流、管道等不可寻址的数据源。
    数据源一次性读入内存，之后按块提供。
    """

    def __init__(self, block_size: int = DEFAULT_BLOCK_SIZE):
        super().__init__()
        self._block_size = block_size
        self._buffer: bytearray = bytearray()
        self._state = FileState.CLOSED

    def open(self, source, encoding: str = ENCODING_UTF8,
             chunk_size: int = 8192, **kwargs) -> bool:
        """
        从流中读取数据。

        参数:
            source: 文件类对象（有 read 方法）
            encoding: 编码
            chunk_size: 每次读取的字节数
        """
        self._encoding = encoding
        self._readonly = True
        self._buffer = bytearray()

        try:
            while True:
                chunk = source.read(chunk_size)
                if not chunk:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode(encoding)
                self._buffer.extend(chunk)
        except Exception as e:
            print(f"[StreamProvider] 读取流失败: {e}")
            return False

        self._size = len(self._buffer)
        self._total_blocks = max(
            1,
            (self._size + self._block_size - 1) // self._block_size
        )
        self._state = FileState.OPENED
        self._dirty_blocks.clear()

        return True

    def read_block(self, block_id: int) -> bytes:
        """读取指定块"""
        if self._state == FileState.CLOSED:
            raise ProviderClosedError("提供者未打开")

        start = block_id * self._block_size
        end = min(start + self._block_size, len(self._buffer))
        if start >= len(self._buffer):
            return b''
        return bytes(self._buffer[start:end])

    def write_block(self, block_id: int, data: bytes) -> bool:
        """写入块（流式提供者通常只读）"""
        return False

    def save(self, filepath: Optional[str] = None) -> bool:
        """流式提供者通常不支持保存"""
        if not filepath:
            return False
        try:
            with open(filepath, 'wb') as f:
                f.write(bytes(self._buffer))
            return True
        except Exception as e:
            print(f"[StreamProvider] 保存失败: {e}")
            return False

    def close(self):
        """清空缓冲区"""
        self._buffer.clear()
        self._state = FileState.CLOSED


# ============================================================
# 提供者工厂
# ============================================================
class ProviderFactory:
    """
    内容提供者工厂。

    根据源类型自动选择合适的提供者。
    """

    _registry: Dict[str, type] = {
        'local': LocalFileProvider,
        'memory': MemoryProvider,
        'stream': StreamProvider,
    }

    @classmethod
    def register(cls, name: str, provider_class: type):
        """注册自定义提供者"""
        cls._registry[name] = provider_class

    @classmethod
    def create(cls, kind: str = 'local', **kwargs) -> ContentProvider:
        """
        根据类型创建提供者。

        参数:
            kind: 提供者类型（local / memory / stream）
            **kwargs: 传递给构造函数的参数

        返回:
            ContentProvider 实例
        """
        provider_class = cls._registry.get(kind)
        if provider_class is None:
            raise ValueError(f"未知的提供者类型: {kind}")
        return provider_class(**kwargs)

    @classmethod
    def create_for_file(cls, filepath: str, **kwargs) -> ContentProvider:
        """
        根据文件自动创建提供者。

        参数:
            filepath: 文件路径
            **kwargs: 额外参数

        返回:
            ContentProvider 实例
        """
        provider = LocalFileProvider()
        provider.open(filepath, **kwargs)
        return provider

    @classmethod
    def list_types(cls) -> List[str]:
        """列出所有已注册的提供者类型"""
        return list(cls._registry.keys())


# ============================================================
# 辅助函数
# ============================================================
def detect_file_encoding(filepath: str, sample_size: int = 4096) -> str:
    """
    检测文件编码（无需打开完整文件）。

    参数:
        filepath: 文件路径
        sample_size: 采样字节数

    返回:
        编码名称
    """
    try:
        with open(filepath, 'rb') as f:
            sample = f.read(sample_size)

        # BOM 检测
        for bom, enc in BOMS.items():
            if sample.startswith(bom):
                return enc

        # chardet 检测
        try:
            import chardet
            result = chardet.detect(sample)
            if result and result.get('confidence', 0) > 0.7:
                return result['encoding'].lower()
        except ImportError:
            pass

        # 简单启发式
        try:
            sample.decode('utf-8')
            return ENCODING_UTF8
        except UnicodeDecodeError:
            pass

        try:
            sample.decode('gbk')
            return ENCODING_GBK
        except UnicodeDecodeError:
            pass

        return ENCODING_LATIN1
    except Exception:
        return ENCODING_UTF8


def detect_file_eol(filepath: str, sample_size: int = 4096) -> str:
    """检测文件行尾符"""
    try:
        with open(filepath, 'rb') as f:
            sample = f.read(sample_size)
        crlf = sample.count(b'\r\n')
        lf = sample.count(b'\n') - crlf
        cr = sample.count(b'\r') - crlf
        if crlf >= lf and crlf >= cr:
            return EOL_CRLF
        elif cr > lf:
            return EOL_CR
        return EOL_LF
    except Exception:
        return EOL_LF


def is_binary_file(filepath: str, sample_size: int = 1024) -> bool:
    """
    检测文件是否为二进制。

    ★ 修复（混合场景压测实测发现）：原实现是"样本里有 NUL 字节 → 二进制"，
    于是**所有 UTF-16 / UTF-32 文本都被判成二进制**：
    ASCII 字符在 UTF-16 里就是 `61 00 62 00 ...`，换行 `0A 00` 也是 NUL 满布。

    实测后果（`app/tabs.py` 的打开路径会用它做拦截）：

        打开一个正常的 UTF-16 文本 → 弹「文件可能包含二进制内容，确定要打开吗？」
        → 用户选「否」→ **文件打不开**。

    现在改为 `is_binary_sample()` 的多级判断：
      1. 有文本 BOM → 一定是文本；
      2. 能按 UTF-8 严格解码 → 文本；
      3. 能按 UTF-16 LE/BE 解码且可打印比例高 → 文本；
      4. 否则看 NUL 比例（>5% 判二进制）。
    """
    try:
        with open(filepath, 'rb') as f:
            sample = f.read(sample_size)
        return is_binary_sample(sample)
    except Exception:
        return False


def is_binary_sample(sample: bytes, sample_limit: int = 1024) -> bool:
    """根据内容样本判断是否二进制（`is_binary_file` 的实现，便于单测）"""
    if not sample:
        return False
    sample = sample[:sample_limit]

    # 1) 文本 BOM → 明确是文本（UTF-16/32 的 NUL 是正常现象）
    for bom in BOMS:
        if sample.startswith(bom):
            return False

    # 2) 严格 UTF-8 可解码 → 文本（注意样本可能截断多字节字符，
    #    因此末尾最多回退 3 字节再试）
    for trim in range(0, 4):
        chunk = sample[:len(sample) - trim] if trim else sample
        try:
            chunk.decode(ENCODING_UTF8, errors='strict')
            return False
        except UnicodeDecodeError:
            continue

    # 3) 无 BOM 的 UTF-16：NUL 集中在同一奇偶位，且能解码出可打印文本
    if _looks_like_utf16(sample):
        return False

    # 4) 否则看 NUL 比例（二进制里 NUL 通常很多）
    nul = sample.count(b'\x00')
    return bool(nul) and (nul / len(sample)) > 0.05


def _looks_like_utf16(sample: bytes) -> bool:
    """判断样本是否像（无 BOM 的）UTF-16 文本"""
    if len(sample) < 4:
        return False
    even_nul = sum(1 for i in range(0, len(sample), 2) if sample[i] == 0)
    odd_nul = sum(1 for i in range(1, len(sample), 2) if sample[i] == 0)
    half = max(1, len(sample) // 2)
    ratio = max(even_nul, odd_nul) / half
    if ratio < 0.3:
        return False
    # NUL 集中在一侧 → 尝试用对应端序解码，并要求可打印比例够高
    enc = ENCODING_UTF16_BE if even_nul > odd_nul else ENCODING_UTF16_LE
    if len(sample) % 2:
        sample = sample[:-1]
    try:
        text = sample.decode(enc, errors='strict')
    except (UnicodeDecodeError, LookupError):
        return False
    if not text:
        return False
    printable = sum(1 for ch in text
                    if ch.isprintable() or ch in '\r\n\t')
    return printable / len(text) > 0.9


def get_file_hash(filepath: str, algorithm: str = 'sha256',
                  chunk_size: int = 8192) -> Optional[str]:
    """
    计算文件哈希。

    参数:
        filepath: 文件路径
        algorithm: 哈希算法
        chunk_size: 分块读取大小

    返回:
        十六进制哈希值或 None
    """
    try:
        h = hashlib.new(algorithm)
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import shutil
    import tempfile

    print("=== 测试 LocalFileProvider ===")

    # 创建临时测试文件
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_provider_test_")
    test_file = os.path.join(tmp_dir, "test.txt")

    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("Hello, 青草编辑器!\n")
        f.write("测试内容，包含中文。\n")
        f.write("Line 3: 继续测试。\n")

    provider = LocalFileProvider()
    provider.open(test_file)

    print(f"提供者: {provider}")
    print(f"文件信息: {provider.get_file_info()}")
    print(f"编码: {provider.encoding}")
    print(f"行尾符: {repr(provider.eol)}")
    print(f"总块数: {provider.total_blocks}")
    print(f"大小: {provider.size} 字节")
    print()

    # 读取全部内容
    text = provider.read_text()
    print(f"内容:\n{text}")

    # 修改块 0
    print("=== 测试写入 ===")
    original = provider.read_block(0)
    new_data = "修改后的内容!\n".encode('utf-8')
    provider.write_block(0, new_data)
    print(f"脏块数: {provider.dirty_block_count}")
    print(f"状态: {provider.state.name}")

    # 保存
    print(f"保存: {provider.save()}")
    print(f"状态: {provider.state.name}")

    # 重新读取验证
    with open(test_file, encoding='utf-8') as f:
        print(f"保存后文件内容: {f.read()}")

    # 测试外部变更检测
    print(f"外部变更检测: {provider.check_external_change()}")

    provider.close()
    print()

    print("=== 测试 MemoryProvider ===")
    mem = MemoryProvider()
    mem.open(initial_text="内存中的文本\n第二行\n")
    print(f"提供者: {mem}")
    print(f"文本: {mem.get_text()}")
    print(f"大小: {mem.size} 字节")
    # 关键：验证基类默认方法
    print(f"check_external_change: {mem.check_external_change()}")
    print(f"reload: {mem.reload()}")

    mem.write_block(0, "新内容".encode('utf-8'))
    print(f"修改后文本: {mem.get_text()}")

    # 另存为
    memory_file = os.path.join(tmp_dir, "from_memory.txt")
    print(f"另存为: {mem.save(memory_file)}")
    print(f"文件存在: {os.path.exists(memory_file)}")
    mem.close()
    print()

    print("=== 测试辅助函数 ===")
    print(f"检测编码: {detect_file_encoding(test_file)}")
    print(f"检测行尾: {repr(detect_file_eol(test_file))}")
    print(f"是否二进制: {is_binary_file(test_file)}")
    print(f"文件哈希: {get_file_hash(test_file)}")

    print()
    print(f"已注册的提供者: {ProviderFactory.list_types()}")

    # 清理
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print()
    print("测试完成。")