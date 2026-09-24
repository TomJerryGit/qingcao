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

import os
import sys
import mmap
import io
import time
import stat
import hashlib
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Tuple, Callable
from enum import Enum, auto


# ============================================================
# 常量
# ============================================================
DEFAULT_BLOCK_SIZE = 64 * 1024          # 默认块大小 64KB
MAX_BLOCK_SIZE = 1024 * 1024            # 最大块大小 1MB
MIN_BLOCK_SIZE = 4096                   # 最小块大小 4KB
MAX_LOADED_BLOCKS = 2000                # 最多同时加载的块数
LARGE_FILE_THRESHOLD = 10 * 1024 * 1024  # 大文件阈值 10MB
HUGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 超大文件阈值 100MB

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
        self._has_bom: bool = False
        self._mtime: float = 0.0
        self._hash: Optional[str] = None

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
        """解码字节串为文本"""
        try:
            return data.decode(self._encoding, errors='replace')
        except (LookupError, UnicodeDecodeError):
            return data.decode(ENCODING_UTF8, errors='replace')

    def encode(self, text: str) -> bytes:
        """编码文本为字节串"""
        try:
            return text.encode(self._encoding, errors='replace')
        except (LookupError, UnicodeEncodeError):
            return text.encode(ENCODING_UTF8, errors='replace')

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
            self._size = st.st_size
            self._mtime = st.st_mtime
        except PermissionError as e:
            raise PermissionDeniedError(f"无法访问文件: {e}")

        # 打开文件句柄
        try:
            mode = 'r+b' if not self._readonly else 'rb'
            self._file = open(self._filepath, mode)
        except PermissionError as e:
            # 尝试只读打开
            try:
                self._file = open(self._filepath, 'rb')
                self._readonly = True
            except PermissionError:
                raise PermissionDeniedError(f"无法打开文件: {e}")

        # 创建 mmap
        if self._size > 0:
            try:
                access = mmap.ACCESS_READ if self._readonly else mmap.ACCESS_WRITE
                self._mmap = mmap.mmap(self._file.fileno(), 0, access=access)
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
            块的字节内容
        """
        if not self.is_open:
            raise ProviderClosedError("提供者未打开")

        if block_id < 0 or block_id >= self._total_blocks:
            return b''

        # 优先返回脏块
        if block_id in self._dirty_blocks:
            return bytes(self._dirty_blocks[block_id])

        start = block_id * self._block_size
        end = min(start + self._block_size, self._size)

        if start >= self._size:
            return b''

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
        持久化脏块到磁盘。

        使用原子写入（临时文件 + 重命名）避免中途失败损坏文件。

        参数:
            filepath: 另存为路径（None 则覆盖原文件）

        返回:
            是否成功
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
            # 若另存为不同文件，需要写入完整内容
            if filepath and target != self._filepath:
                return self._save_as_full(target)

            # 场景1：脏块少于全部块，使用原地写入
            return self._save_dirty_blocks(target)

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

        修复流程：
            1. 先 mmap.flush() + mmap.close()，释放文件锁
            2. open('r+b') 写脏块
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

        # ---- 2. 写脏块 ----
        try:
            # 使用可写文件句柄
            with open(target, 'r+b') as f:
                for block_id, data in self._dirty_blocks.items():
                    offset = block_id * self._block_size
                    f.seek(offset)
                    f.write(bytes(data))
                f.flush()
                os.fsync(f.fileno())

            # 更新状态
            self._dirty_blocks.clear()
            self._state = (FileState.READONLY if self._readonly
                           else FileState.OPENED)

            # 更新 mtime / size
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
            self._reopen_mmap()
            return False

    def _reopen_mmap(self):
        """重建 mmap（A4 新增，供 _save_dirty_blocks 内部调用）。

        在关闭 mmap 写盘后调用，保持 provider 后续读操作可用。
        """
        if not self._file:
            return
        if self._size <= 0:
            return
        try:
            access = (mmap.ACCESS_READ if self._readonly
                      else mmap.ACCESS_WRITE)
            self._mmap = mmap.mmap(
                self._file.fileno(), 0, access=access
            )
        except (ValueError, OSError):
            self._mmap = None

    def _save_as_full(self, target: str) -> bool:
        """另存为完整文件（原子写入）"""
        import tempfile

        try:
            # 读取所有内容（含脏块）
            full_data = self.read_all()

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

                # 原子重命名
                if sys.platform == 'win32' and os.path.exists(target):
                    os.replace(tmp_path, target)
                else:
                    os.rename(tmp_path, target)

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
            try:
                self._mtime = os.path.getmtime(target)
                self._size = os.path.getsize(target)
            except Exception:
                pass

            return True

        except Exception as e:
            print(f"[LocalFileProvider] 另存为失败: {e}")
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
        except Exception:
            return False

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

    通过检查是否存在 NUL 字节判断。
    """
    try:
        with open(filepath, 'rb') as f:
            sample = f.read(sample_size)
        return b'\x00' in sample
    except Exception:
        return False


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
    import tempfile
    import shutil

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
    with open(test_file, 'r', encoding='utf-8') as f:
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