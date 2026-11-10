# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""流式提供者（v2.24 拆出）。"""
from core.content_provider_base import ContentProvider
from core.content_provider_common import *  # noqa: F401,F403,F405


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
