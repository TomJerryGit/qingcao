# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""内存提供者（v2.24 拆出）。"""
from core.content_provider_base import ContentProvider
from core.content_provider_common import *  # noqa: F401,F403,F405


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
