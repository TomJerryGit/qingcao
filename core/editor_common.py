# -*- coding: utf-8 -*-
# ruff: noqa: F401, F403, F405
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为编辑器代理模块，包含：
- EditorProxy：编辑器操作代理（UI 与文档模型之间的桥梁）
- 撤销/重做命令管理
- 多光标与列模式
- 智能括号与自动缩进
- 代码片段展开
- 书签与折叠
- LSP 客户端集成
- 宏录制回调
- 搜索高亮
- 事件总线联动
- 光标拖尾与智能单词高亮

修复记录:
- _on_scintilla_modified: text 可能为 None/bytes，统一规范化
- _move_line / duplicate_line: 使用 self.sc.text() 替代
  QsciScintilla.SCI_GETRANGE（PyQt5 未导出该常量）
- 所有 SCI_INSERTTEXT 调用确保传入 bytes
"""

import datetime
import logging
import os
import re
import shutil
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt5.Qsci import QsciLexerCPP, QsciLexerPython, QsciScintilla
from PyQt5.QtCore import QDateTime, QObject, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont

from app.event_bus import (
    CursorEvent,
    FileEvent,
    FileModifiedEvent,
    FileSavedEvent,
    RedoEvent,
    SearchFinishedEvent,
    SearchStartedEvent,
    SelectionEvent,
    StatusMessageEvent,
    TextEditEvent,
    UndoEvent,
    bus,
)
from core.commands import (
    CommandFactory,
    CommandPool,
    DeleteCmd,
    GroupCmd,
    InsertCmd,
    ReplaceCmd,
    merge_commands,
)
from core.document import Document
from core.lsp_client import LspClient, LspServerRegistry
from core.search import SearchEngine, SearchOptions
from core.undo import UndoManager


logger = logging.getLogger(__name__)


# ============================================================
# 常量
# ============================================================
# 指示器 ID
INDICATOR_SEARCH = 0  # 搜索高亮
INDICATOR_CURRENT_MATCH = 1  # 当前匹配
INDICATOR_LSP_ERROR = 2  # LSP 错误波浪线
INDICATOR_SNIPPET = 3  # 代码片段占位符
INDICATOR_CURSOR_TRAIL = 5  # 光标拖尾
INDICATOR_SMART_HIGHLIGHT = 7  # 智能单词高亮

# 标记 ID
MARKER_BOOKMARK = 0  # 书签
MARKER_GIT_ADDED = 1  # Git 新增行
MARKER_GIT_MODIFIED = 2  # Git 修改行
MARKER_GIT_DELETED = 3  # Git 删除行
MARKER_BREAKPOINT = 4  # 调试断点
MARKER_DEBUG_LINE = 5  # 调试器当前停住的行（D3）

# 多光标合并时间窗口（毫秒）
MULTI_CURSOR_MERGE_INTERVAL = 300

# 智能高亮防抖延迟（毫秒）
SMART_HIGHLIGHT_DELAY = 300

# P0-2: 文档变更 → LSP didChange 的防抖延迟（毫秒）
LSP_SYNC_DELAY = 300

# 缓冲区 → Document.provider 的同步防抖延迟（毫秒）
#
# 取 0：QTimer 会自动重启，连续击键仍只触发一次；而 0ms 意味着
# 事件循环下一轮即生效，不依赖用户等待 —— 查找/替换/另存为/插件
# 读到的内容因此与屏幕一致。
# 这样"编辑器缓冲区"与"provider 快照"两份内容源的问题被消除。
PROVIDER_SYNC_DELAY = 0

# 文件扩展名 → LSP languageId 映射（与
# LspServerRegistry._servers 中的 language_id 保持一致）
LSP_LANGUAGE_BY_EXT = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".java": "java",
    ".json": "json",
    ".md": "markdown",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".sh": "shellscript",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".sql": "sql",
}

# 光标拖尾保留时长（秒）
CURSOR_TRAIL_DURATION = 0.2


# ============================================================
# P6: LSP 接线辅助函数
# ============================================================
def lsp_language_for_file(filepath: Optional[str]) -> Optional[str]:
    """文件路径 → LSP languageId（不认识则 None）。

    P6 修复：``toggle_lsp`` 原先硬编码 ``ext not in ('.py', '.pyw')``，
    与本模块的 ``LSP_LANGUAGE_BY_EXT``（20+ 种语言）自相矛盾。
    统一以本函数（即 LSP_LANGUAGE_BY_EXT）作为"是否支持"的唯一判据。
    """
    if not filepath:
        return None
    ext = os.path.splitext(filepath)[1].lower()
    return LSP_LANGUAGE_BY_EXT.get(ext)


def lsp_server_language_for_file(filepath: Optional[str]) -> Optional[str]:
    """文件路径 → :class:`LspServerRegistry` 中的服务器键。

    languageId 与注册表键不总是同名（例如 .ts 的 languageId 是
    ``typescript``，而 QScintilla/注册表里的服务器键是
    ``javascript``），因此先按 languageId 精确查，查不到再退化为
    按扩展名匹配注册表。
    """
    language = lsp_language_for_file(filepath)
    if language is None:
        return None
    try:
        if LspServerRegistry.get(language) is not None:
            return language
        return LspServerRegistry.detect_language(filepath)
    except Exception:
        return None


def lsp_install_hint(language: Optional[str]) -> str:
    """返回语言的安装提示，例如 ``pip install python-lsp-server``。"""
    if not language:
        return ""
    try:
        config = LspServerRegistry.get(language) or {}
    except Exception:
        config = {}
    command = config.get("command") or []
    executable = command[0] if command else language
    install = list(config.get("install") or [])
    if install:
        # python 的 install 形如
        # [sys.executable, '-m', 'pip', 'install', 'python-lsp-server']，
        # 去掉解释器前缀，给出用户可直接复制执行的命令。
        if len(install) >= 3 and install[1] == "-m":
            return " ".join(install[2:])
        return " ".join(install)
    return f"请手动安装 {executable}"


def lsp_command_available(command: Optional[List[str]]) -> bool:
    """启动命令是否可用（PATH 查找 / 绝对路径存在性检查）。"""
    if not command:
        return False
    program = command[0]
    try:
        if os.path.isabs(program):
            return os.path.isfile(program)
        return shutil.which(program) is not None
    except Exception:
        return False


# ============================================================
# 偏好辅助（P8: 统一走 Preferences，不再散落裸 QSettings）
# ============================================================
DEFAULT_DATE_FORMAT = "%Y-%m-%d"
DEFAULT_TIME_FORMAT = "%H:%M:%S"


def resolve_datetime_format(date_format: Optional[str], time_format: Optional[str]) -> str:
    """组合 ``date_format`` / ``time_format`` 得到"插入日期时间"的格式。

    历史默认值 ``date_format`` 已经自带时间部分
    (``"%Y-%m-%d %H:%M:%S"``)。因此只有在用户把它改成**纯日期**
    （如 ``"%Y-%m-%d"``）时才追加 ``time_format``，否则会出现
    ``"%Y-%m-%d %H:%M:%S %H:%M:%S"`` 这种重复时间。
    """
    date_fmt = date_format or DEFAULT_DATE_FORMAT
    time_fmt = time_format or DEFAULT_TIME_FORMAT
    if any(token in date_fmt for token in ("%H", "%I", "%M", "%S")):
        return date_fmt
    return f"{date_fmt} {time_fmt}"


# ============================================================
# 辅助函数
# ============================================================
def _normalize_bytes(data) -> bytes:
    """将输入统一转为 bytes"""
    if data is None:
        return b""
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if isinstance(data, str):
        return data.encode("utf-8", errors="replace")
    return str(data).encode("utf-8", errors="replace")


# 行尾符号（顺序重要：先匹配 \r\n）
_EOL_SPLIT_RE = re.compile(r"(\r\n|\r|\n)")


def _trim_trailing_ws_keep_eol(text: str) -> str:
    """裁掉每行**行尾空白**，但原样保留每行的行尾符号

    为什么不用 `splitlines()` + `'\\n'.join(...)`（原实现的写法）：
        那会把 CRLF / CR / LF 统一成 LF —— 用户只是改一个字保存，
        整个文件的行尾风格却被悄悄改写：
            `b'a\\r\\n' + b'b\\n' + b'c\\r'`  →  `b'a\\nb\\nc\\n'`
        git diff 会显示全文件改动，CRLF 项目整体被污染。

    本函数按行尾符号切分（保留分隔符），只对"行内容"做 `rstrip(' \\t\\f\\v')`，
    这样：
        * 空白清理照旧生效；
        * 每行的行尾符号（`\\r\\n` / `\\r` / `\\n`）保持原样；
        * 混合换行文件保存后仍是混合换行（与 Notepad++ 行为一致）。
    """
    if not text:
        return text
    parts = _EOL_SPLIT_RE.split(text)
    out = []
    for part in parts:
        if part in ("\r\n", "\r", "\n"):
            out.append(part)
        else:
            # 只裁空格/制表符等"行尾空白"，绝不碰 \r / \n
            out.append(part.rstrip(" \t\f\v"))
    return "".join(out)


# ============================================================
# 编辑器代理
# ============================================================
