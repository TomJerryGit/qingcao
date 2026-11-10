#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：TomJerry
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为 LSP（Language Server Protocol）客户端模块，包含：
- LspClient：语言服务器客户端（JSON-RPC over stdio）
- QProcess 进程管理
- 消息分帧与解析（Content-Length 头）
- 请求/响应关联
- 通知订阅
- 生命周期管理（initialize/shutdown/exit）
- 文档同步（didOpen/didChange/didClose/didSave）
- 诊断（publishDiagnostics）
- 补全（completion）
- 悬停（hover）
- 跳转定义（definition）
- 查找引用（references）
- 重命名（rename）
- 文档符号（documentSymbol）
- 代码操作（codeAction）
- 格式化（formatting）
- 签名帮助（signatureHelp）
- 崩溃自动重启
- 服务器能力查询
- 进度报告
- 错误处理与日志

修复记录:
- path_to_uri: 删除多余的盘符加斜杠逻辑，修复 Windows 路径
  变成 "file:////C:/..." 的 bug（P1-7）
"""

import json
import os
import sys
import threading
import time
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from PyQt5.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, pyqtSignal


# ============================================================
# 常量
# ============================================================
# JSON-RPC 协议版本
JSONRPC_VERSION = "2.0"

# LSP 默认超时（毫秒）
DEFAULT_REQUEST_TIMEOUT = 30000
DEFAULT_INIT_TIMEOUT = 15000
DEFAULT_SHUTDOWN_TIMEOUT = 3000

# 自动重启最大次数
MAX_RESTART_ATTEMPTS = 3
RESTART_DELAY_MS = 2000

# 消息大小上限（防止恶意大消息）
MAX_MESSAGE_SIZE = 50 * 1024 * 1024  # 50MB


# ============================================================
# LSP 状态枚举
# ============================================================


class LspState(Enum):
    """LSP 客户端状态"""

    STOPPED = auto()  # 未启动
    STARTING = auto()  # 启动中
    INITIALIZING = auto()  # 初始化中
    RUNNING = auto()  # 正常运行
    SHUTTING_DOWN = auto()  # 关闭中
    ERROR = auto()  # 错误
    RESTARTING = auto()  # 重启中


# ============================================================
# LSP 错误码
# ============================================================


class LspErrorCode:
    """JSON-RPC 标准错误码"""

    ParseError = -32700
    InvalidRequest = -32600
    MethodNotFound = -32601
    InvalidParams = -32602
    InternalError = -32603
    ServerNotInitialized = -32002
    UnknownErrorCode = -32001
    RequestCancelled = -32800
    ContentModified = -32801
    RequestFailed = -32803


# ============================================================
# LSP 异常
# ============================================================


class LspError(Exception):
    """LSP 异常基类"""

    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def __repr__(self):
        return f"LspError(code={self.code}, message={self.message!r})"


class LspTimeoutError(LspError):
    """LSP 请求超时"""

    def __init__(self, method: str):
        super().__init__(-1, f"请求超时: {method}")
        self.method = method


class LspNotRunningError(LspError):
    """LSP 未运行"""

    def __init__(self):
        super().__init__(-1, "LSP 客户端未运行")


# ============================================================
# 待处理请求
# ============================================================


class PendingRequest:
    """待处理请求"""

    def __init__(
        self,
        request_id: int,
        method: str,
        callback: Optional[Callable] = None,
        timeout_ms: int = DEFAULT_REQUEST_TIMEOUT,
    ):
        self.id = request_id
        self.method = method
        self.callback = callback
        self.timeout_ms = timeout_ms
        self.created_at = time.time()
        self.completed = False
        self.result: Any = None
        self.error: Optional[LspError] = None

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) * 1000 > self.timeout_ms

    def complete(self, result: Any):
        self.result = result
        self.completed = True

    def fail(self, error: LspError):
        self.error = error
        self.completed = True


# ============================================================
# LSP 客户端
# ============================================================

__all__ = [n for n in dir() if not n.startswith("__")]
