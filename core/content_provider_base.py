# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
"""内容提供者基类（v2.24 从 content_provider.py 拆出）。"""
from core.content_provider_common import *  # noqa: F401,F403,F405


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
