#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为搜索引擎模块，包含：
- SearchEngine：单文件搜索引擎（多线程、Hyperscan 可选）
- SearchOptions：搜索选项（正则、大小写、全词、转义）
- SearchMatch：单个匹配结果
- SearchResult：搜索结果集合
- SearchStatistics：搜索统计
- FileSearcher：多文件搜索（全局搜索）
- ReplaceEngine：替换引擎
- 增量搜索与流式匹配
- 搜索取消与超时控制
- 跨块匹配处理
- 行号与列号计算
- 搜索结果高亮辅助

修复记录:
- _position_to_line_col: 改用惰性构建的行索引 + 二分查找（P2-9）。
  原实现对每次匹配都从头读取到 position，大文件搜索时复杂度为
  O(N × file_size)。现在首次 O(file_size) 构建索引，之后每次
  O(log lines)，N 个匹配总复杂度降为 O(file_size + N × log(lines))。
- _build_line_index: 新增方法，分块读取 provider，采用 UTF-8 友好
  的边界保护（保留 8 字节）避免多字节字符被块边界切断。
- _read_text_up_to: 保留作为兼容接口，标记为 deprecated。
"""

import os
import re
import time
import threading
from typing import Optional, List, Dict, Any, Tuple, Callable, Iterator, Set
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict

from PyQt5.QtCore import QObject, pyqtSignal, QThread


# ============================================================
# 常量
# ============================================================
# 默认线程数
DEFAULT_THREADS = 4
MAX_THREADS = 16

# 单次搜索超时（秒）
DEFAULT_SEARCH_TIMEOUT = 30

# 搜索结果上限（防止内存爆炸）
MAX_MATCHES = 1000000

# 单个文件最大搜索字节数
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB

# 上下文预览字符数
CONTEXT_PREVIEW_LENGTH = 80

# 行索引构建时，块边界保留的字节数（避免多字节字符被切断）
_LINE_INDEX_KEEP_BYTES = 8

# Hyperscan 支持检测
try:
    import hyperscan
    HYPERSCAN_AVAILABLE = True
except ImportError:
    HYPERSCAN_AVAILABLE = False


# ============================================================
# 搜索选项
# ============================================================
@dataclass
class SearchOptions:
    """
    搜索选项。

    所有搜索行为的参数集合。
    """

    pattern: str = ""
    is_regex: bool = False
    case_sensitive: bool = False
    whole_word: bool = False
    escape_pattern: bool = False
    multi_line: bool = False
    dot_matches_newline: bool = False

    # 范围限制
    start_pos: int = 0
    end_pos: int = -1  # -1 表示到文件末尾

    # 搜索行为
    max_results: int = MAX_MATCHES
    timeout_seconds: float = DEFAULT_SEARCH_TIMEOUT
    use_hyperscan: bool = True
    threads: int = DEFAULT_THREADS

    # 替换（用于 ReplaceEngine）
    replace_text: str = ""

    def to_regex_flags(self) -> int:
        """转换为 Python re 模块标志"""
        flags = 0
        if not self.case_sensitive:
            flags |= re.IGNORECASE
        if self.multi_line:
            flags |= re.MULTILINE
        if self.dot_matches_newline:
            flags |= re.DOTALL
        return flags

    def build_pattern(self) -> str:
        """构建最终的正则表达式字符串"""
        pattern = self.pattern

        if self.escape_pattern:
            pattern = re.escape(pattern)

        if self.whole_word:
            pattern = rf'\b{pattern}\b'

        return pattern

    def describe(self) -> str:
        """返回选项描述"""
        parts = [f"pattern={self.pattern!r}"]
        if self.is_regex:
            parts.append("regex")
        if self.case_sensitive:
            parts.append("case")
        if self.whole_word:
            parts.append("whole-word")
        if self.escape_pattern:
            parts.append("escaped")
        return " ".join(parts)


# ============================================================
# 匹配结果
# ============================================================
@dataclass
class SearchMatch:
    """
    单个匹配结果。

    包含匹配的位置信息、文本内容和上下文。
    """

    start: int                    # 起始字符位置
    end: int                      # 结束字符位置（不含）
    text: str = ""                # 匹配的文本
    line: int = 0                 # 行号（1 开始）
    col: int = 0                  # 列号（0 开始）
    line_text: str = ""           # 所在行的完整文本
    context: str = ""             # 上下文预览
    groups: Tuple[str, ...] = ()  # 正则捕获组

    @property
    def length(self) -> int:
        """匹配长度"""
        return self.end - self.start

    def contains(self, pos: int) -> bool:
        """检查指定位置是否在匹配范围内"""
        return self.start <= pos < self.end

    def overlaps(self, other: 'SearchMatch') -> bool:
        """检查是否与另一匹配重叠"""
        return not (self.end <= other.start or other.end <= self.start)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            'start': self.start,
            'end': self.end,
            'text': self.text,
            'line': self.line,
            'col': self.col,
            'line_text': self.line_text,
            'context': self.context,
            'groups': list(self.groups),
        }

    def __repr__(self) -> str:
        preview = self.text[:30].replace('\n', '\\n')
        if len(self.text) > 30:
            preview += "..."
        return f"<Match line={self.line} col={self.col} '{preview}'>"


# ============================================================
# 搜索结果
# ============================================================
@dataclass
class SearchResult:
    """
    搜索结果集合。

    包含所有匹配及搜索统计信息。
    """

    matches: List[SearchMatch] = field(default_factory=list)
    pattern: str = ""
    elapsed_ms: float = 0.0
    cancelled: bool = False
    error: Optional[str] = None
    total_scanned: int = 0  # 扫描的总字节数
    total_matches: int = 0  # 实际匹配数量（可能超过 max_results）

    # 分文件统计（用于 FileSearcher）
    file_results: Dict[str, List[SearchMatch]] = field(default_factory=dict)

    @property
    def count(self) -> int:
        """匹配数量"""
        return len(self.matches)

    @property
    def is_empty(self) -> bool:
        """是否无匹配"""
        return len(self.matches) == 0

    @property
    def success(self) -> bool:
        """是否成功"""
        return self.error is None

    def add_match(self, match: SearchMatch) -> bool:
        """
        添加匹配。

        返回:
            True 表示已添加，False 表示超出上限被忽略
        """
        self.total_matches += 1
        if len(self.matches) >= MAX_MATCHES:
            return False
        self.matches.append(match)
        return True

    def get_first(self) -> Optional[SearchMatch]:
        """获取第一个匹配"""
        return self.matches[0] if self.matches else None

    def get_last(self) -> Optional[SearchMatch]:
        """获取最后一个匹配"""
        return self.matches[-1] if self.matches else None

    def get_match_at(self, pos: int) -> Optional[SearchMatch]:
        """获取指定位置的匹配"""
        for m in self.matches:
            if m.contains(pos):
                return m
        return None

    def get_next_match(self, pos: int) -> Optional[SearchMatch]:
        """获取指定位置之后的下一个匹配"""
        for m in self.matches:
            if m.start > pos:
                return m
        return None

    def get_prev_match(self, pos: int) -> Optional[SearchMatch]:
        """获取指定位置之前的上一个匹配"""
        for m in reversed(self.matches):
            if m.end <= pos:
                return m
        return None

    def get_lines_with_matches(self) -> List[int]:
        """获取所有包含匹配的行号（去重排序）"""
        return sorted(set(m.line for m in self.matches))

    def get_matches_in_line(self, line: int) -> List[SearchMatch]:
        """获取指定行的所有匹配"""
        return [m for m in self.matches if m.line == line]

    def get_file_count(self) -> int:
        """获取涉及的文件数量"""
        return len(self.file_results)

    def get_summary(self) -> str:
        """获取摘要"""
        if self.error:
            return f"搜索失败: {self.error}"
        status = "已取消" if self.cancelled else "完成"
        return (f"搜索{status}: {self.count} 个匹配, "
                f"耗时 {self.elapsed_ms:.0f} ms")

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            'pattern': self.pattern,
            'count': self.count,
            'total_matches': self.total_matches,
            'elapsed_ms': self.elapsed_ms,
            'cancelled': self.cancelled,
            'error': self.error,
            'matches': [m.to_dict() for m in self.matches],
        }

    def __iter__(self) -> Iterator[SearchMatch]:
        return iter(self.matches)

    def __len__(self) -> int:
        return len(self.matches)

    def __getitem__(self, index) -> SearchMatch:
        return self.matches[index]

    def __repr__(self) -> str:
        return (f"<SearchResult matches={self.count} "
                f"elapsed={self.elapsed_ms:.0f}ms>")


# ============================================================
# 搜索统计
# ============================================================
class SearchStatistics:
    """搜索统计器"""

    def __init__(self):
        self.total_searches = 0
        self.total_matches = 0
        self.total_bytes_scanned = 0
        self.total_time_ms = 0.0
        self.failed_searches = 0
        self.cancelled_searches = 0
        self._lock = threading.Lock()

    def record(self, result: SearchResult):
        """记录一次搜索结果"""
        with self._lock:
            self.total_searches += 1
            self.total_matches += result.total_matches
            self.total_bytes_scanned += result.total_scanned
            self.total_time_ms += result.elapsed_ms

            if result.error:
                self.failed_searches += 1
            if result.cancelled:
                self.cancelled_searches += 1

    def reset(self):
        """重置统计"""
        with self._lock:
            self.__init__()

    def get_summary(self) -> Dict[str, Any]:
        """获取统计摘要"""
        with self._lock:
            avg_time = (self.total_time_ms / self.total_searches
                        if self.total_searches > 0 else 0)
            return {
                'total_searches': self.total_searches,
                'total_matches': self.total_matches,
                'total_bytes_scanned': self.total_bytes_scanned,
                'total_time_ms': round(self.total_time_ms, 2),
                'avg_time_ms': round(avg_time, 2),
                'failed_searches': self.failed_searches,
                'cancelled_searches': self.cancelled_searches,
            }

    def dump(self) -> str:
        """导出统计信息"""
        info = self.get_summary()
        lines = ["搜索统计", "=" * 60]
        for k, v in info.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)


# ============================================================
# 单文件搜索引擎
# ============================================================
class SearchEngine:
    """
    单文件搜索引擎。

    支持:
    - 正则表达式匹配
    - 大小写敏感/不敏感
    - 全词匹配
    - 多线程并行搜索
    - Hyperscan 加速（如可用）
    - 结果超时与取消
    - 增量返回（流式）
    """

    def __init__(self, provider, options: Optional[SearchOptions] = None):
        """
        参数:
            provider: 内容提供者（ContentProvider）
            options: 搜索选项
        """
        self.provider = provider
        self.options = options or SearchOptions()

        # 取消标志
        self._cancel_event = threading.Event()

        # 统计
        self.statistics = SearchStatistics()

        # 编译后的正则
        self._regex: Optional[re.Pattern] = None
        self._hyperscan_db = None

        # 行索引缓存（P2-9：用于 _position_to_line_col 加速）
        # 存储每一行（0-based）的起始**字符**位置。
        # index[0] 恒为 0；index[i+1] = 第 i 行末尾换行符的字符位置 + 1。
        # 惰性构建：首次调用 _position_to_line_col 时构建。
        self._line_offsets: Optional[List[int]] = None
        self._line_index_lock = threading.Lock()

    # --------------------------------------------------------
    # 编译
    # --------------------------------------------------------
    def compile(self) -> bool:
        """
        编译搜索模式。

        返回:
            是否成功
        """
        if not self.options.pattern:
            return False

        try:
            pattern_str = self.options.build_pattern()
            flags = self.options.to_regex_flags()
            self._regex = re.compile(pattern_str, flags)

            # 尝试编译 Hyperscan
            if (HYPERSCAN_AVAILABLE and
                    self.options.use_hyperscan and
                    self.options.is_regex):
                try:
                    self._compile_hyperscan(pattern_str, flags)
                except Exception:
                    self._hyperscan_db = None

            return True

        except re.error as e:
            print(f"[SearchEngine] 正则编译失败: {e}")
            return False
        except Exception as e:
            print(f"[SearchEngine] 编译失败: {e}")
            return False

    def _compile_hyperscan(self, pattern: str, flags: int):
        """编译 Hyperscan 数据库"""
        hs_flags = hyperscan.HS_FLAG_SOM_LEFTMOST
        if not (flags & re.IGNORECASE):
            hs_flags |= hyperscan.HS_FLAG_CASELESS
        if flags & re.MULTILINE:
            hs_flags |= hyperscan.HS_FLAG_MULTILINE
        if flags & re.DOTALL:
            hs_flags |= hyperscan.HS_FLAG_DOTALL

        db = hyperscan.Database()
        db.compile(
            expressions=[pattern.encode('utf-8')],
            ids=[0],
            flags=[hs_flags],
        )
        self._hyperscan_db = db

    # --------------------------------------------------------
    # 取消控制
    # --------------------------------------------------------
    def cancel(self):
        """取消当前搜索"""
        self._cancel_event.set()

    def is_cancelled(self) -> bool:
        """是否已取消"""
        return self._cancel_event.is_set()

    def reset_cancel(self):
        """重置取消标志"""
        self._cancel_event.clear()

    # --------------------------------------------------------
    # 搜索入口
    # --------------------------------------------------------
    def search(self) -> SearchResult:
        """
        执行搜索（同步）。

        返回:
            SearchResult
        """
        result = SearchResult(pattern=self.options.pattern)
        start_time = time.time()

        self.reset_cancel()

        try:
            # 编译
            if not self.compile():
                result.error = "搜索模式编译失败"
                return result

            # 检查提供者
            if not self.provider or not self.provider.is_open:
                result.error = "提供者未打开"
                return result

            # 执行搜索
            if self.options.threads > 1 and not self.options.is_regex:
                self._search_multi_threaded(result)
            else:
                self._search_single_threaded(result)

            # 记录耗时
            result.elapsed_ms = (time.time() - start_time) * 1000
            result.cancelled = self.is_cancelled()

        except Exception as e:
            result.error = str(e)
            print(f"[SearchEngine] 搜索失败: {e}")

        # 记录统计
        self.statistics.record(result)

        return result

    def search_streaming(self,
                          callback: Callable[[SearchMatch], bool]
                          ) -> SearchResult:
        """
        流式搜索（每找到一个匹配调用一次回调）。

        参数:
            callback: 处理匹配的回调，返回 False 可停止搜索

        返回:
            SearchResult（不包含所有匹配，仅统计信息）
        """
        result = SearchResult(pattern=self.options.pattern)
        start_time = time.time()

        self.reset_cancel()

        try:
            if not self.compile():
                result.error = "搜索模式编译失败"
                return result

            if not self.provider or not self.provider.is_open:
                result.error = "提供者未打开"
                return result

            # 流式搜索
            for match in self.iter_matches():
                if self.is_cancelled():
                    result.cancelled = True
                    break

                result.total_matches += 1

                if callback:
                    try:
                        if not callback(match):
                            break
                    except Exception as e:
                        print(f"[SearchEngine] 回调异常: {e}")

            result.elapsed_ms = (time.time() - start_time) * 1000

        except Exception as e:
            result.error = str(e)

        self.statistics.record(result)
        return result

    def iter_matches(self) -> Iterator[SearchMatch]:
        """
        迭代所有匹配（生成器）。

        适用于流式处理，避免一次性加载所有结果。
        """
        if not self._regex:
            return

        # 逐块读取
        block_size = self.provider.block_size
        total_blocks = self.provider.total_blocks

        # 跨块缓冲
        carry_over = b''
        carry_offset = 0

        count = 0

        for bid in range(total_blocks):
            if self.is_cancelled():
                return

            if count >= self.options.max_results:
                return

            # 读取块
            try:
                block_data = self.provider.read_block(bid)
            except Exception:
                continue

            # 合并跨块数据
            combined = carry_over + block_data
            combined_offset = carry_offset

            # 解码
            try:
                text = combined.decode(self.provider.encoding, errors='replace')
            except Exception:
                continue

            # 匹配
            for m in self._regex.finditer(text):
                if self.is_cancelled():
                    return
                if count >= self.options.max_results:
                    return

                # 计算全局位置
                global_start = combined_offset + m.start()
                global_end = combined_offset + m.end()

                # 检查范围
                if global_start < self.options.start_pos:
                    continue
                if (self.options.end_pos >= 0 and
                        global_start >= self.options.end_pos):
                    return

                # 构建匹配对象
                match = self._build_match(global_start, global_end, m, text)
                yield match
                count += 1

            # 保留最后一部分作为跨块缓冲（防止跨块匹配丢失）
            if len(block_data) > 0:
                overlap_size = max(256, block_size // 4)
                if len(combined) > overlap_size:
                    carry_over = combined[-overlap_size:].encode(
                        self.provider.encoding, errors='replace'
                    )
                    carry_offset = combined_offset + len(combined) - overlap_size
                else:
                    carry_over = b''
                    carry_offset = 0

    # --------------------------------------------------------
    # 单线程搜索
    # --------------------------------------------------------
    def _search_single_threaded(self, result: SearchResult):
        """单线程搜索"""
        for match in self.iter_matches():
            if self.is_cancelled():
                result.cancelled = True
                break
            if not result.add_match(match):
                break

    # --------------------------------------------------------
    # 多线程搜索
    # --------------------------------------------------------
    def _search_multi_threaded(self, result: SearchResult):
        """多线程搜索"""
        total_blocks = self.provider.total_blocks
        threads = min(self.options.threads, MAX_THREADS, total_blocks)

        if threads <= 1:
            self._search_single_threaded(result)
            return

        # 分配块范围给各线程
        chunk_size = max(1, total_blocks // threads)
        chunks = []
        for i in range(threads):
            start = i * chunk_size
            end = min(start + chunk_size, total_blocks) if i < threads - 1 else total_blocks
            if start < end:
                chunks.append((start, end))

        # 并行搜索
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {
                executor.submit(self._search_range, start, end): (start, end)
                for start, end in chunks
            }

            all_matches: Dict[int, List[SearchMatch]] = {}

            for future in as_completed(futures):
                if self.is_cancelled():
                    result.cancelled = True
                    break

                start, end = futures[future]
                try:
                    matches = future.result()
                    all_matches[start] = matches
                except Exception as e:
                    print(f"[SearchEngine] 线程失败: {e}")

        # 按块顺序合并结果
        for start in sorted(all_matches.keys()):
            for match in all_matches[start]:
                if not result.add_match(match):
                    return

    def _search_range(self, start_block: int,
                       end_block: int) -> List[SearchMatch]:
        """搜索指定块范围"""
        matches = []

        if not self._regex:
            return matches

        block_size = self.provider.block_size
        carry_over = b''
        carry_offset = 0

        for bid in range(start_block, end_block):
            if self.is_cancelled():
                return matches

            try:
                block_data = self.provider.read_block(bid)
            except Exception:
                continue

            combined = carry_over + block_data
            combined_offset = carry_offset

            try:
                text = combined.decode(self.provider.encoding, errors='replace')
            except Exception:
                continue

            for m in self._regex.finditer(text):
                if self.is_cancelled():
                    return matches

                global_start = combined_offset + m.start()
                global_end = combined_offset + m.end()

                if global_start < self.options.start_pos:
                    continue
                if (self.options.end_pos >= 0 and
                        global_start >= self.options.end_pos):
                    return matches

                match = self._build_match(global_start, global_end, m, text)
                matches.append(match)

            # 保留跨块缓冲
            if len(block_data) > 0:
                overlap_size = max(256, block_size // 4)
                if len(combined) > overlap_size:
                    carry_over = combined[-overlap_size:].encode(
                        self.provider.encoding, errors='replace'
                    )
                    carry_offset = combined_offset + len(combined) - overlap_size
                else:
                    carry_over = b''
                    carry_offset = 0

        return matches

    # --------------------------------------------------------
    # 匹配构建
    # --------------------------------------------------------
    def _build_match(self, start: int, end: int,
                      re_match, text: str) -> SearchMatch:
        """构建 SearchMatch 对象"""
        # 计算行号列号
        line, col = self._position_to_line_col(start)

        # 获取所在行文本
        line_text = self._get_line_text(line)

        # 上下文预览
        context = self._make_context(text, re_match.start(), re_match.end())

        # 捕获组
        groups = tuple(g for g in re_match.groups()) if re_match.groups() else ()

        return SearchMatch(
            start=start,
            end=end,
            text=re_match.group(0),
            line=line,
            col=col,
            line_text=line_text,
            context=context,
            groups=groups,
        )

    # --------------------------------------------------------
    # 行索引（P2-9 性能优化）
    # --------------------------------------------------------
    def _build_line_index(self) -> List[int]:
        """
        构建行起始字符位置索引（P2-9 性能优化）。

        返回:
            List[int]，index[i] 表示第 i 行（0-based）的起始字符位置。

        说明:
            - 惰性构建，使用 threading.Lock 保证线程安全。
            - 分块读取 provider，避免一次性将超大文件读入单个字符串。
            - 采用块边界保护：每块末尾保留 _LINE_INDEX_KEEP_BYTES 字节，
              与下一块拼接后再解码，避免多字节字符被切断。
            - 构建后缓存于 self._line_offsets，
              在 SearchEngine 生命周期内复用（一次性对象，不跨内容变更）。
        """
        # 快速路径（无锁读，命中率最高）
        if self._line_offsets is not None:
            return self._line_offsets

        with self._line_index_lock:
            # double-check
            if self._line_offsets is not None:
                return self._line_offsets

            index: List[int] = [0]

            try:
                total_blocks = self.provider.total_blocks
                encoding = getattr(self.provider, 'encoding', 'utf-8') or 'utf-8'
                keep_bytes = _LINE_INDEX_KEEP_BYTES

                pending = b''
                char_cursor = 0  # 已处理文本的字符总数

                for bid in range(total_blocks):
                    try:
                        data = self.provider.read_block(bid)
                    except Exception:
                        continue

                    if not data:
                        continue

                    pending += data

                    # 非最后一块：保留末尾 keep_bytes 供下次拼接
                    if bid < total_blocks - 1 and len(pending) > keep_bytes:
                        to_decode = pending[:-keep_bytes]
                        pending = pending[-keep_bytes:]
                    else:
                        to_decode = pending
                        pending = b''

                    if not to_decode:
                        continue

                    try:
                        text = to_decode.decode(
                            encoding, errors='replace'
                        )
                    except Exception:
                        # 解码失败：跳过本批，避免影响整体流程
                        continue

                    # 扫描 '\n'，使用 find 循环（比 split 更省内存）
                    start = 0
                    while True:
                        pos = text.find('\n', start)
                        if pos < 0:
                            break
                        index.append(char_cursor + pos + 1)
                        start = pos + 1

                    char_cursor += len(text)

                # 处理剩余未解码字节
                if pending:
                    try:
                        text = pending.decode(encoding, errors='replace')
                        start = 0
                        while True:
                            pos = text.find('\n', start)
                            if pos < 0:
                                break
                            index.append(char_cursor + pos + 1)
                            start = pos + 1
                    except Exception:
                        pass

            except Exception as e:
                print(f"[SearchEngine] 构建行索引失败: {e}")

            self._line_offsets = index
            return index

    def _position_to_line_col(self, position: int) -> Tuple[int, int]:
        """
        将字符位置转换为 (行, 列)。

        参数:
            position: 字符偏移（0-based）

        返回:
            (行号（1-based）, 列号（0-based））

        修复说明（P2-9）:
            - 原实现每次调用都会从头读取文件到 position，
              复杂度 O(position)，多个匹配时总复杂度 O(N × file_size)。
            - 现在改用惰性构建的行索引 + 二分查找：
              * 首次调用 O(file_size) 构建索引；
              * 之后每次调用 O(log lines)。
        """
        try:
            index = self._build_line_index()

            if not index:
                return (1, 0)

            if position <= 0:
                return (1, 0)

            # 二分查找：找到最大的 i 使 index[i] <= position
            import bisect
            line_idx = bisect.bisect_right(index, position) - 1
            if line_idx < 0:
                line_idx = 0

            col = position - index[line_idx]
            # line 是 1-based
            return (line_idx + 1, col)
        except Exception:
            return (1, 0)

    def _read_text_up_to(self, position: int) -> str:
        """
        [已弃用] 读取指定位置之前的文本。

        保留作为兼容接口。P2-9 后 _position_to_line_col 不再使用此方法，
        而是使用 _build_line_index 构建的索引。

        警告：对超大文件，此方法可能产生显著内存开销。新代码不应调用。
        """
        if position <= 0:
            return ""

        block_size = self.provider.block_size
        end_block = position // block_size

        chunks = []
        for bid in range(end_block + 1):
            if bid == end_block:
                # 最后一块只取到 position
                data = self.provider.read_block(bid)
                offset_in_block = position - bid * block_size
                data = data[:offset_in_block]
            else:
                data = self.provider.read_block(bid)

            try:
                chunks.append(data.decode(self.provider.encoding,
                                          errors='replace'))
            except Exception:
                pass

        return ''.join(chunks)

    def _get_line_text(self, line: int) -> str:
        """获取指定行的文本"""
        try:
            # 读取全文
            text = self.provider.read_text()
            lines = text.splitlines()
            if 1 <= line <= len(lines):
                return lines[line - 1]
        except Exception:
            pass
        return ""

    def _make_context(self, text: str, start: int, end: int,
                       max_len: int = CONTEXT_PREVIEW_LENGTH) -> str:
        """生成匹配的上下文预览"""
        try:
            # 找到行边界
            line_start = text.rfind('\n', 0, start)
            line_start = line_start + 1 if line_start >= 0 else 0

            line_end = text.find('\n', end)
            line_end = line_end if line_end >= 0 else len(text)

            line_text = text[line_start:line_end]

            # 如果太长，截取匹配附近
            if len(line_text) > max_len:
                match_center = start - line_start
                half = max_len // 2
                ctx_start = max(0, match_center - half)
                ctx_end = min(len(line_text), match_center + half)

                prefix = "..." if ctx_start > 0 else ""
                suffix = "..." if ctx_end < len(line_text) else ""

                return prefix + line_text[ctx_start:ctx_end] + suffix

            return line_text
        except Exception:
            return ""

    # --------------------------------------------------------
    # 替换
    # --------------------------------------------------------
    def replace_all(self, replacement: str,
                     result: Optional[SearchResult] = None) -> int:
        """
        替换所有匹配（在提供者中）。

        注意：此方法直接修改提供者的内容，但不会立即保存。

        参数:
            replacement: 替换文本（支持正则反向引用 \1 \2 等）
            result: 可选的搜索结果（None 则先执行搜索）

        返回:
            替换的数量
        """
        if not self._regex:
            if not self.compile():
                return 0

        if result is None:
            result = self.search()

        if result.is_empty:
            return 0

        # 从后往前替换，避免位置偏移
        count = 0
        for match in reversed(result.matches):
            try:
                # 计算替换文本
                if self.options.is_regex:
                    # 使用捕获组替换
                    re_match = self._regex.match(match.text)
                    if re_match:
                        new_text = re_match.expand(replacement)
                    else:
                        new_text = replacement
                else:
                    new_text = replacement

                # 更新提供者内容
                self._replace_range(match.start, match.end, new_text)
                count += 1

            except Exception as e:
                print(f"[SearchEngine] 替换失败: {e}")
                continue

        return count

    def _replace_range(self, start: int, end: int, new_text: str):
        """
        替换指定范围的文本。

        由于 ContentProvider 是块结构，需要特殊处理。
        """
        try:
            # 读取全部内容
            text = self.provider.read_text()

            # 替换
            new_content = text[:start] + new_text + text[end:]

            # 写回提供者
            encoded = self.provider.encode(new_content)
            block_size = self.provider.block_size
            total_blocks = max(1, (len(encoded) + block_size - 1) // block_size)

            # 清空并重写
            self.provider.clear_dirty()

            for bid in range(total_blocks):
                bstart = bid * block_size
                bend = min(bstart + block_size, len(encoded))
                self.provider.write_block(bid, encoded[bstart:bend])

            # 更新块数
            if hasattr(self.provider, '_total_blocks'):
                self.provider._total_blocks = total_blocks
            if hasattr(self.provider, '_size'):
                self.provider._size = len(encoded)

        except Exception as e:
            print(f"[SearchEngine] 替换范围失败: {e}")

    # --------------------------------------------------------
    # 信息查询
    # --------------------------------------------------------
    def get_pattern(self) -> str:
        """获取搜索模式"""
        return self.options.pattern

    def get_options(self) -> SearchOptions:
        """获取搜索选项"""
        return self.options

    def is_compiled(self) -> bool:
        """是否已编译"""
        return self._regex is not None

    def __repr__(self) -> str:
        return (f"<SearchEngine pattern={self.options.pattern!r} "
                f"regex={self.options.is_regex} "
                f"compiled={self.is_compiled()}>")


# ============================================================
# 多文件搜索引擎（全局搜索）
# ============================================================
class FileSearcher(QObject):
    """
    多文件搜索引擎（在项目中查找）。

    支持:
    - 目录递归遍历
    - 文件类型过滤
    - 多线程并行搜索
    - 结果分批推送
    - 搜索取消
    - 进度报告

    信号:
        search_started(str, int): 搜索开始（pattern, 文件数）
        file_result(str, list): 单个文件结果（路径, 匹配列表）
        search_progress(int, int): 进度（已搜索文件数, 总文件数）
        search_finished(SearchResult): 搜索完成
        search_error(str): 搜索错误
    """

    search_started = pyqtSignal(str, int)
    file_result = pyqtSignal(str, list)
    search_progress = pyqtSignal(int, int)
    search_finished = pyqtSignal(object)
    search_error = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

        # 当前搜索状态
        self._searching: bool = False
        self._cancel_event = threading.Event()
        self._worker: Optional[threading.Thread] = None

        # 统计
        self.statistics = SearchStatistics()

    @property
    def is_searching(self) -> bool:
        """是否正在搜索"""
        return self._searching

    # --------------------------------------------------------
    # 搜索入口
    # --------------------------------------------------------
    def search(self, root_dir: str, options: SearchOptions,
               file_filter: str = "*.*",
               exclude_dirs: Optional[List[str]] = None,
               include_hidden: bool = False) -> SearchResult:
        """
        执行多文件搜索（异步）。

        参数:
            root_dir: 根目录
            options: 搜索选项
            file_filter: 文件过滤（如 "*.py" 或 "*.py;*.txt"）
            exclude_dirs: 排除的目录名列表
            include_hidden: 是否包含隐藏文件

        返回:
            SearchResult（异步执行，实际结果通过信号返回）
        """
        if self._searching:
            result = SearchResult(pattern=options.pattern)
            result.error = "搜索正在进行中"
            return result

        self._cancel_event.clear()
        self._searching = True

        # 收集文件列表
        try:
            files = self._collect_files(
                root_dir, file_filter, exclude_dirs, include_hidden
            )
        except Exception as e:
            self._searching = False
            result = SearchResult(pattern=options.pattern)
            result.error = f"收集文件失败: {e}"
            return result

        # 启动后台线程
        self._worker = threading.Thread(
            target=self._do_search,
            args=(files, options),
            daemon=True,
        )
        self._worker.start()

        # 返回空结果（实际结果通过信号）
        return SearchResult(pattern=options.pattern)

    def search_sync(self, root_dir: str, options: SearchOptions,
                     file_filter: str = "*.*",
                     exclude_dirs: Optional[List[str]] = None,
                     include_hidden: bool = False) -> SearchResult:
        """
        同步执行多文件搜索。

        参数同上，返回完整结果。
        """
        start_time = time.time()
        result = SearchResult(pattern=options.pattern)

        try:
            files = self._collect_files(
                root_dir, file_filter, exclude_dirs, include_hidden
            )

            for filepath in files:
                if self._cancel_event.is_set():
                    result.cancelled = True
                    break

                file_matches = self._search_file(filepath, options)
                if file_matches:
                    result.file_results[filepath] = file_matches
                    for m in file_matches:
                        result.add_match(m)

            result.elapsed_ms = (time.time() - start_time) * 1000

        except Exception as e:
            result.error = str(e)

        self.statistics.record(result)
        return result

    def cancel(self):
        """取消搜索"""
        self._cancel_event.set()

    def _do_search(self, files: List[str], options: SearchOptions):
        """后台搜索线程"""
        start_time = time.time()
        result = SearchResult(pattern=options.pattern)

        try:
            self.search_started.emit(options.pattern, len(files))

            total = len(files)
            for i, filepath in enumerate(files):
                if self._cancel_event.is_set():
                    result.cancelled = True
                    break

                # 搜索单个文件
                file_matches = self._search_file(filepath, options)

                if file_matches:
                    result.file_results[filepath] = file_matches
                    for m in file_matches:
                        result.add_match(m)

                    # 发射文件结果
                    self.file_result.emit(filepath, file_matches)

                # 进度
                self.search_progress.emit(i + 1, total)

            result.elapsed_ms = (time.time() - start_time) * 1000

        except Exception as e:
            result.error = str(e)
            self.search_error.emit(str(e))

        finally:
            self._searching = False
            self.statistics.record(result)
            self.search_finished.emit(result)

    def _search_file(self, filepath: str,
                      options: SearchOptions) -> List[SearchMatch]:
        """搜索单个文件"""
        matches = []

        try:
            # 检查文件大小
            if os.path.getsize(filepath) > MAX_FILE_SIZE:
                return matches

            # 检查是否二进制
            if self._is_binary(filepath):
                return matches

            # 创建临时提供者
            from core.content_provider import LocalFileProvider
            provider = LocalFileProvider()
            provider.open(filepath, detect_encoding=True)

            try:
                engine = SearchEngine(provider, options)
                result = engine.search()

                # 调整行号（相对于文件）
                matches = result.matches

            finally:
                provider.close()

        except Exception:
            pass

        return matches

    def _collect_files(self, root_dir: str, file_filter: str,
                        exclude_dirs: Optional[List[str]],
                        include_hidden: bool) -> List[str]:
        """收集符合条件的文件"""
        files = []

        if not os.path.isdir(root_dir):
            return files

        exclude_dirs = exclude_dirs or [
            '.git', '.svn', '.hg', '__pycache__',
            'node_modules', '.venv', 'venv', '.idea', '.vscode',
        ]

        # 解析文件过滤
        patterns = self._parse_filter(file_filter)

        for dirpath, dirnames, filenames in os.walk(root_dir):
            # 排除目录
            dirnames[:] = [
                d for d in dirnames
                if d not in exclude_dirs
                and (include_hidden or not d.startswith('.'))
            ]

            for filename in filenames:
                if not include_hidden and filename.startswith('.'):
                    continue

                if patterns and not self._match_filter(filename, patterns):
                    continue

                full_path = os.path.join(dirpath, filename)
                files.append(full_path)

        return files

    @staticmethod
    def _parse_filter(file_filter: str) -> List[str]:
        """解析文件过滤字符串"""
        if not file_filter or file_filter == "*.*" or file_filter == "*":
            return []

        patterns = []
        for part in file_filter.split(';'):
            part = part.strip()
            if part:
                patterns.append(part)
        return patterns

    @staticmethod
    def _match_filter(filename: str, patterns: List[str]) -> bool:
        """检查文件名是否匹配过滤条件"""
        import fnmatch
        for pattern in patterns:
            if fnmatch.fnmatch(filename.lower(), pattern.lower()):
                return True
        return False

    @staticmethod
    def _is_binary(filepath: str, sample_size: int = 1024) -> bool:
        """检查是否为二进制文件"""
        try:
            with open(filepath, 'rb') as f:
                sample = f.read(sample_size)
            return b'\x00' in sample
        except Exception:
            return True


# ============================================================
# 替换引擎
# ============================================================
class ReplaceEngine:
    """
    替换引擎。

    封装搜索与替换的完整流程，支持：
    - 单个替换
    - 全部替换
    - 预览替换结果
    - 批量替换多文件
    """

    def __init__(self, provider):
        """
        参数:
            provider: 内容提供者
        """
        self.provider = provider

    def replace_one(self, match: SearchMatch, replacement: str) -> bool:
        """
        替换单个匹配。

        参数:
            match: 匹配对象
            replacement: 替换文本

        返回:
            是否成功
        """
        try:
            # 读取全文
            text = self.provider.read_text()

            # 执行替换
            new_text = text[:match.start] + replacement + text[match.end:]

            # 写回
            self._write_back(new_text)
            return True

        except Exception as e:
            print(f"[ReplaceEngine] 替换失败: {e}")
            return False

    def replace_all(self, result: SearchResult,
                     replacement: str,
                     is_regex: bool = False,
                     pattern: str = "") -> int:
        """
        替换所有匹配。

        参数:
            result: 搜索结果
            replacement: 替换文本
            is_regex: 是否使用正则替换
            pattern: 原始正则（用于反向引用）

        返回:
            替换的数量
        """
        if result.is_empty:
            return 0

        count = 0

        try:
            text = self.provider.read_text()
            regex = re.compile(pattern) if (is_regex and pattern) else None

            # 从后往前替换
            new_text = text
            for match in reversed(result.matches):
                try:
                    if is_regex and regex:
                        # 正则替换
                        original = text[match.start:match.end]
                        re_match = regex.fullmatch(original)
                        if re_match:
                            repl = re_match.expand(replacement)
                        else:
                            repl = replacement
                    else:
                        repl = replacement

                    new_text = (new_text[:match.start] + repl +
                                new_text[match.end:])
                    count += 1

                except Exception:
                    continue

            # 写回
            self._write_back(new_text)

        except Exception as e:
            print(f"[ReplaceEngine] 全部替换失败: {e}")

        return count

    def preview_replace(self, result: SearchResult,
                         replacement: str,
                         max_preview: int = 5
                         ) -> List[Tuple[str, str]]:
        """
        预览替换结果。

        返回:
            [(原文, 替换后), ...] 最多 max_preview 条
        """
        previews = []

        for match in result.matches[:max_preview]:
            original = match.text
            if result.pattern:
                try:
                    regex = re.compile(result.pattern)
                    re_match = regex.fullmatch(original)
                    if re_match:
                        new_text = re_match.expand(replacement)
                    else:
                        new_text = replacement
                except Exception:
                    new_text = replacement
            else:
                new_text = replacement

            previews.append((original, new_text))

        return previews

    def _write_back(self, new_text: str):
        """将新文本写回提供者"""
        encoded = self.provider.encode(new_text)
        block_size = self.provider.block_size
        total_blocks = max(1, (len(encoded) + block_size - 1) // block_size)

        self.provider.clear_dirty()

        for bid in range(total_blocks):
            start = bid * block_size
            end = min(start + block_size, len(encoded))
            self.provider.write_block(bid, encoded[start:end])

        if hasattr(self.provider, '_total_blocks'):
            self.provider._total_blocks = total_blocks
        if hasattr(self.provider, '_size'):
            self.provider._size = len(encoded)


# ============================================================
# 辅助函数
# ============================================================
def build_search_options(pattern: str, **kwargs) -> SearchOptions:
    """
    构建搜索选项的便捷函数。

    用法:
        options = build_search_options("hello", case_sensitive=True)
    """
    options = SearchOptions(pattern=pattern)
    for key, value in kwargs.items():
        if hasattr(options, key):
            setattr(options, key, value)
    return options


def quick_search(provider, pattern: str, **kwargs) -> SearchResult:
    """
    快速搜索的便捷函数。

    用法:
        result = quick_search(provider, "hello", is_regex=True)
    """
    options = build_search_options(pattern, **kwargs)
    engine = SearchEngine(provider, options)
    return engine.search()


def find_in_files(root_dir: str, pattern: str,
                   file_filter: str = "*.py",
                   **kwargs) -> SearchResult:
    """
    在文件中搜索的便捷函数。

    用法:
        result = find_in_files("/path", "TODO", "*.py")
    """
    options = build_search_options(pattern, **kwargs)
    searcher = FileSearcher()
    return searcher.search_sync(root_dir, options, file_filter)


def highlight_matches_in_text(text: str, matches: List[SearchMatch],
                                left: str = "<<", right: str = ">>") -> str:
    """
    在文本中标记匹配位置（用于调试）。

    参数:
        text: 原始文本
        matches: 匹配列表
        left: 左标记
        right: 右标记

    返回:
        标记后的文本
    """
    if not matches:
        return text

    # 按位置排序
    sorted_matches = sorted(matches, key=lambda m: m.start)

    result = []
    last_pos = 0
    for m in sorted_matches:
        if m.start < last_pos:
            continue  # 跳过重叠
        result.append(text[last_pos:m.start])
        result.append(left + m.text + right)
        last_pos = m.end

    result.append(text[last_pos:])
    return ''.join(result)


def count_matches_in_text(text: str, pattern: str,
                           is_regex: bool = False) -> int:
    """统计文本中匹配数量（不构建 SearchMatch 对象）"""
    try:
        if not is_regex:
            pattern = re.escape(pattern)
        return len(re.findall(pattern, text))
    except Exception:
        return 0


def extract_lines(text: str, matches: List[SearchMatch]) -> Dict[int, str]:
    """提取所有包含匹配的行的文本"""
    lines = text.splitlines()
    result = {}
    for m in matches:
        if 1 <= m.line <= len(lines):
            result[m.line] = lines[m.line - 1]
    return result


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import tempfile
    import shutil

    print("=== 测试 SearchOptions ===")

    options = SearchOptions(
        pattern="hello",
        case_sensitive=False,
        whole_word=True,
    )
    print(f"选项: {options.describe()}")
    print(f"正则: {options.build_pattern()}")
    print(f"标志: {options.to_regex_flags()}")
    print()

    print("=== 测试 SearchEngine（内存提供者）===")

    from core.content_provider import MemoryProvider

    # 创建内存提供者
    text_content = """Hello World!
This is a test file.
hello again, hello there.
TODO: fix this bug.
The word hello appears multiple times.
Case insensitive HELLO should match too.
"""

    provider = MemoryProvider()
    provider.open(initial_text=text_content)

    # 测试简单搜索
    options = SearchOptions(
        pattern="hello",
        case_sensitive=False,
        whole_word=True,
    )
    engine = SearchEngine(provider, options)
    result = engine.search()

    print(f"搜索: {engine}")
    print(f"结果: {result.get_summary()}")
    print(f"匹配数: {result.count}")
    for m in result:
        print(f"  {m}")
    print()

    # 测试正则搜索
    options2 = SearchOptions(
        pattern=r"h\w+o",
        is_regex=True,
        case_sensitive=False,
    )
    engine2 = SearchEngine(provider, options2)
    result2 = engine2.search()

    print(f"正则搜索: {result2.get_summary()}")
    for m in result2:
        print(f"  {m}")
    print()

    # 测试统计
    print(engine.statistics.dump())
    print()

    # 测试辅助函数
    print("=== 测试辅助函数 ===")
    matched_text = highlight_matches_in_text(
        text_content, result.matches, "[", "]"
    )
    print("高亮标记:")
    print(matched_text[:200])
    print()

    print(f"匹配行数: {len(result.get_lines_with_matches())}")
    print(f"匹配行: {result.get_lines_with_matches()}")
    print()

    print("=== 测试替换引擎 ===")
    replace_engine = ReplaceEngine(provider)
    count = replace_engine.replace_all(result, "HI", is_regex=False)
    print(f"替换数量: {count}")
    new_text = provider.read_text()
    print(f"替换后前 200 字符:\n{new_text[:200]}")
    print()

    # 清理
    provider.close()

    print("=== 测试多文件搜索 ===")

    # 创建临时测试目录
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_search_test_")
    try:
        # 创建测试文件
        for i in range(3):
            filepath = os.path.join(tmp_dir, f"test{i}.py")
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# Test file {i}\n")
                f.write("def hello():\n")
                f.write("    print('hello world')\n")
                f.write("    # TODO: fix\n")

        # 搜索
        options = SearchOptions(pattern="hello", case_sensitive=False)
        searcher = FileSearcher()
        result = searcher.search_sync(tmp_dir, options, "*.py")

        print(f"多文件搜索: {result.get_summary()}")
        print(f"涉及文件: {result.get_file_count()}")
        for filepath, matches in result.file_results.items():
            print(f"  {os.path.basename(filepath)}: {len(matches)} 个匹配")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print()
    print("测试完成。")