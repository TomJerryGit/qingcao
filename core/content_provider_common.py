#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
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
DEFAULT_BLOCK_SIZE = 64 * 1024  # 默认块大小 64KB
MAX_BLOCK_SIZE = 1024 * 1024  # 最大块大小 1MB
MIN_BLOCK_SIZE = 4096  # 最小块大小 4KB
MAX_LOADED_BLOCKS = 2000  # 最多同时加载的块数
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
MMAP_MIN_SIZE = 4 * 1024 * 1024  # 4MB
# 常见编码
ENCODING_UTF8 = "utf-8"
ENCODING_UTF8_BOM = "utf-8-sig"
ENCODING_GBK = "gbk"
ENCODING_GB18030 = "gb18030"
ENCODING_BIG5 = "big5"
ENCODING_SHIFT_JIS = "shift_jis"
ENCODING_EUC_KR = "euc-kr"
ENCODING_LATIN1 = "latin-1"
ENCODING_ASCII = "ascii"
ENCODING_UTF16_LE = "utf-16-le"
ENCODING_UTF16_BE = "utf-16-be"
# BOM 标记
BOMS = {
    b"\xef\xbb\xbf": "utf-8-sig",
    b"\xff\xfe\x00\x00": "utf-32-le",
    b"\x00\x00\xfe\xff": "utf-32-be",
    b"\xff\xfe": "utf-16-le",
    b"\xfe\xff": "utf-16-be",
}
# 行尾符
EOL_LF = "\n"
EOL_CRLF = "\r\n"
EOL_CR = "\r"
# BOM 字符（U+FEFF）
_BOM_CHAR = "\ufeff"
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
_BOM_STRIPPED_ENCODINGS = frozenset(
    {
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "utf-32",
        "utf-32-le",
        "utf-32-be",
    }
)
# 裸端序编码 → 它应该带上的 BOM
#
# 用途见 `encode()` 的说明：这类编码的 `str.encode()` 不补 BOM，
# 保存时必须手动补回，否则"编辑过的 UTF-16 文件"会丢 BOM。
# `utf-16`/`utf-32`（不带端序后缀）的编码器**自己会加 BOM**，故不在此表。
_BARE_ENDIAN_BOM = {
    "utf-16-le": b"\xff\xfe",
    "utf-16-be": b"\xfe\xff",
    "utf-32-le": b"\xff\xfe\x00\x00",
    "utf-32-be": b"\x00\x00\xfe\xff",
}


def _strip_leading_bom(text: str, encoding: str) -> str:
    """剥掉解码结果**开头**的 BOM（仅首字符，不动正文里的 U+FEFF）"""
    if text and text[0] == _BOM_CHAR:
        if str(encoding or "").lower() in _BOM_STRIPPED_ENCODINGS:
            return text[1:]
    return text


# ============================================================
# 异常定义
# ============================================================
def _strip_leading_bom(text: str, encoding: str) -> str:
    """剥掉解码结果**开头**的 BOM（仅首字符，不动正文里的 U+FEFF）"""
    if text and text[0] == _BOM_CHAR:
        if str(encoding or "").lower() in _BOM_STRIPPED_ENCODINGS:
            return text[1:]
    return text


# ============================================================
# 异常定义
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
        with open(filepath, "rb") as f:
            sample = f.read(sample_size)
        # BOM 检测
        for bom, enc in BOMS.items():
            if sample.startswith(bom):
                return enc
        # chardet 检测
        try:
            import chardet

            result = chardet.detect(sample)
            if result and result.get("confidence", 0) > 0.7:
                return result["encoding"].lower()
        except ImportError:
            pass
        # 简单启发式
        try:
            sample.decode("utf-8")
            return ENCODING_UTF8
        except UnicodeDecodeError:
            pass
        try:
            sample.decode("gbk")
            return ENCODING_GBK
        except UnicodeDecodeError:
            pass
        return ENCODING_LATIN1
    except Exception:
        return ENCODING_UTF8


def detect_file_eol(filepath: str, sample_size: int = 4096) -> str:
    """检测文件行尾符"""
    try:
        with open(filepath, "rb") as f:
            sample = f.read(sample_size)
        crlf = sample.count(b"\r\n")
        lf = sample.count(b"\n") - crlf
        cr = sample.count(b"\r") - crlf
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
        with open(filepath, "rb") as f:
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
        chunk = sample[: len(sample) - trim] if trim else sample
        try:
            chunk.decode(ENCODING_UTF8, errors="strict")
            return False
        except UnicodeDecodeError:
            continue
    # 3) 无 BOM 的 UTF-16：NUL 集中在同一奇偶位，且能解码出可打印文本
    if _looks_like_utf16(sample):
        return False
    # 4) 否则看 NUL 比例（二进制里 NUL 通常很多）
    nul = sample.count(b"\x00")
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
        text = sample.decode(enc, errors="strict")
    except (UnicodeDecodeError, LookupError):
        return False
    if not text:
        return False
    printable = sum(1 for ch in text if ch.isprintable() or ch in "\r\n\t")
    return printable / len(text) > 0.9


def get_file_hash(
    filepath: str, algorithm: str = "sha256", chunk_size: int = 8192
) -> Optional[str]:
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
        with open(filepath, "rb") as f:
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

    CLOSED = auto()  # 未打开
    OPENED = auto()  # 已打开
    MODIFIED = auto()  # 已修改
    READONLY = auto()  # 只读
    ERROR = auto()  # 错误


# ============================================================
# 内容提供者抽象基类
# ============================================================

__all__ = [n for n in dir() if not n.startswith("__")]
