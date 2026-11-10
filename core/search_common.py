#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
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
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple

from PyQt5.QtCore import QObject, QThread, pyqtSignal


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
SEARCH_LARGE_FILE_LIMIT = 10 * 1024 * 1024  # 搜索跳过 >10MB 大文件（v2.17.x）


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
            pattern = rf"\b{pattern}\b"

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

    # --------------------------------------------------------
    # 偏好接线（P7）
    # --------------------------------------------------------
    @classmethod
    def from_preferences(cls, **overrides) -> "SearchOptions":
        """
        构造 SearchOptions，并从 Preferences 读取性能相关默认值。

        接线的偏好键（app/preferences.py 的 DEFAULTS）:
            search_threads  -> threads
            use_hyperscan   -> use_hyperscan
            search_timeout  -> timeout_seconds

        背景（P7）:
            修复前这三个键在首选项里有定义、用户可写，但
            SearchOptions 永远使用硬编码的 DEFAULT_THREADS（4）、
            DEFAULT_SEARCH_TIMEOUT（30）与 use_hyperscan=True，
            用户改了毫无反应 —— 典型的"假开关"。

        容错:
            读取失败（无 QSettings / 无 Preferences / 值类型异常）
            一律静默回退到 dataclass 默认值，绝不能让搜索启动失败。
        """
        options = cls(**overrides)
        try:
            from app.preferences import get_preferences

            prefs = get_preferences()

            threads = int(prefs.get("search_threads", DEFAULT_THREADS))
            options.threads = max(1, min(MAX_THREADS, threads))

            options.use_hyperscan = bool(prefs.get("use_hyperscan", HYPERSCAN_AVAILABLE))

            timeout = float(prefs.get("search_timeout", DEFAULT_SEARCH_TIMEOUT))
            if timeout > 0:
                options.timeout_seconds = timeout
        except Exception:
            # 偏好不可用：保持 dataclass 默认值
            pass
        return options


# ============================================================
# 匹配结果
# ============================================================


@dataclass
class SearchMatch:
    """
    单个匹配结果。

    位置说明（P1-1）:
        start / end           字节偏移（Scintilla 用）
        char_start / char_end 字符偏移（Python 字符串索引用）

        纯 ASCII 文本两者相等；含中文时字节偏移 > 字符偏移。
    """

    start: int  # 字节偏移（Scintilla）
    end: int  # 字节偏移（不含）
    char_start: int = 0  # 字符偏移（Python 索引）
    char_end: int = 0  # 字符偏移（不含）
    text: str = ""  # 匹配的文本
    line: int = 0  # 行号（1 开始）
    col: int = 0  # 列号（0 开始）
    line_text: str = ""  # 所在行的完整文本
    context: str = ""  # 上下文预览
    groups: Tuple[str, ...] = ()  # 正则捕获组

    @property
    def length(self) -> int:
        """匹配长度（字节）"""
        return self.end - self.start

    def contains(self, pos: int) -> bool:
        """检查指定字节位置是否在匹配范围内"""
        return self.start <= pos < self.end

    def overlaps(self, other: "SearchMatch") -> bool:
        """检查是否与另一匹配重叠"""
        return not (self.end <= other.start or other.end <= self.start)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "start": self.start,
            "end": self.end,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "text": self.text,
            "line": self.line,
            "col": self.col,
            "line_text": self.line_text,
            "context": self.context,
            "groups": list(self.groups),
        }

    def __repr__(self) -> str:
        preview = self.text[:30].replace("\n", "\\n")
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
        return f"搜索{status}: {self.count} 个匹配, 耗时 {self.elapsed_ms:.0f} ms"

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "pattern": self.pattern,
            "count": self.count,
            "total_matches": self.total_matches,
            "elapsed_ms": self.elapsed_ms,
            "cancelled": self.cancelled,
            "error": self.error,
            "matches": [m.to_dict() for m in self.matches],
        }

    def __iter__(self) -> Iterator[SearchMatch]:
        return iter(self.matches)

    def __len__(self) -> int:
        return len(self.matches)

    def __getitem__(self, index) -> SearchMatch:
        return self.matches[index]

    def __repr__(self) -> str:
        return f"<SearchResult matches={self.count} elapsed={self.elapsed_ms:.0f}ms>"


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
            avg_time = self.total_time_ms / self.total_searches if self.total_searches > 0 else 0
            return {
                "total_searches": self.total_searches,
                "total_matches": self.total_matches,
                "total_bytes_scanned": self.total_bytes_scanned,
                "total_time_ms": round(self.total_time_ms, 2),
                "avg_time_ms": round(avg_time, 2),
                "failed_searches": self.failed_searches,
                "cancelled_searches": self.cancelled_searches,
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

__all__ = [n for n in dir() if not n.startswith("__")]
