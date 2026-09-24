#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
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

import os
import sys
import json
import time
import threading
from typing import Optional, Dict, List, Any, Tuple, Callable
from enum import Enum, auto
from urllib.parse import urlparse, unquote

from PyQt5.QtCore import (
    QObject, QProcess, QProcessEnvironment, pyqtSignal, QTimer
)


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
    STOPPED = auto()       # 未启动
    STARTING = auto()      # 启动中
    INITIALIZING = auto()  # 初始化中
    RUNNING = auto()       # 正常运行
    SHUTTING_DOWN = auto() # 关闭中
    ERROR = auto()         # 错误
    RESTARTING = auto()    # 重启中


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

    def __init__(self, request_id: int, method: str,
                 callback: Optional[Callable] = None,
                 timeout_ms: int = DEFAULT_REQUEST_TIMEOUT):
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
class LspClient(QObject):
    """
    LSP 客户端。

    使用 QProcess 与语言服务器进行 JSON-RPC 通信。

    信号:
        state_changed(str): 状态变更
        initialized(dict): 初始化完成（服务器能力）
        diagnostics_updated(str, list): 诊断更新（uri, diagnostics）
        completion_ready(list): 补全结果
        hover_ready(dict): 悬停结果
        definition_ready(list): 跳转定义结果
        references_ready(list): 查找引用结果
        rename_ready(dict): 重命名结果
        document_symbols_ready(list): 文档符号结果
        code_actions_ready(list): 代码操作结果
        formatting_ready(list): 格式化结果
        signature_help_ready(dict): 签名帮助结果
        log_message(str, int): 服务器日志（消息, 类型）
        error_occurred(str): 错误
        server_crashed(int): 服务器崩溃（退出码）
        server_restarted(): 服务器重启成功
    """

    # 状态信号
    state_changed = pyqtSignal(str)
    initialized = pyqtSignal(dict)

    # 结果信号
    diagnostics_updated = pyqtSignal(str, list)
    completion_ready = pyqtSignal(list)
    hover_ready = pyqtSignal(dict)
    definition_ready = pyqtSignal(list)
    references_ready = pyqtSignal(list)
    rename_ready = pyqtSignal(dict)
    document_symbols_ready = pyqtSignal(list)
    code_actions_ready = pyqtSignal(list)
    formatting_ready = pyqtSignal(list)
    signature_help_ready = pyqtSignal(dict)

    # 日志与错误
    log_message = pyqtSignal(str, int)
    error_occurred = pyqtSignal(str)
    server_crashed = pyqtSignal(int)
    server_restarted = pyqtSignal()

    # --------------------------------------------------------
    # 构造函数
    # --------------------------------------------------------
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

        # 状态
        self._state = LspState.STOPPED
        self._state_lock = threading.Lock()

        # QProcess
        self._process: Optional[QProcess] = None

        # 服务器命令
        self._command: List[str] = []
        self._working_dir: Optional[str] = None
        self._env: Optional[Dict[str, str]] = None

        # 消息缓冲
        self._buffer: bytes = b''
        self._content_length: int = 0
        self._reading_header: bool = True
        self._header_buffer: bytes = b''

        # 请求 ID 计数器
        self._next_id: int = 1
        self._id_lock = threading.Lock()

        # 待处理请求
        self._pending: Dict[int, PendingRequest] = {}

        # 通知回调
        self._notification_handlers: Dict[str, List[Callable]] = {}

        # 文档版本号
        self._doc_versions: Dict[str, int] = {}

        # 已打开的文档
        self._open_documents: Dict[str, str] = {}  # uri -> language_id

        # 服务器能力
        self.capabilities: Dict[str, Any] = {}

        # 服务器信息
        self.server_info: Dict[str, Any] = {}

        # 根 URI
        self._root_uri: str = ""

        # 重启计数
        self._restart_count: int = 0

        # 超时检查定时器
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setInterval(5000)
        self._timeout_timer.timeout.connect(self._check_timeouts)

        # 初始化完成标志
        self._init_completed = False

    # ========================================================
    # 状态管理
    # ========================================================
    @property
    def state(self) -> LspState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == LspState.RUNNING

    @property
    def is_initialized(self) -> bool:
        return self._init_completed

    def _set_state(self, state: LspState):
        """设置状态并发射信号"""
        if self._state != state:
            self._state = state
            try:
                self.state_changed.emit(state.name)
            except Exception:
                pass

    # ========================================================
    # 启动与停止
    # ========================================================
    def start(self, command: List[str],
              working_dir: Optional[str] = None,
              env: Optional[Dict[str, str]] = None):
        """
        启动语言服务器。

        参数:
            command: 启动命令列表（如 ["pylsp"]）
            working_dir: 工作目录
            env: 环境变量（追加到现有环境）
        """
        if self._state in (LspState.RUNNING, LspState.STARTING):
            self.stop()

        self._command = list(command)
        self._working_dir = working_dir
        self._env = env

        self._set_state(LspState.STARTING)

        # 创建 QProcess
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.finished.connect(self._on_process_finished)
        self._process.errorOccurred.connect(self._on_process_error)

        # 设置工作目录
        if working_dir:
            self._process.setWorkingDirectory(working_dir)

        # 设置环境变量
        if env:
            process_env = QProcessEnvironment.systemEnvironment()
            for k, v in env.items():
                process_env.insert(k, v)
            self._process.setProcessEnvironment(process_env)

        # 启动进程
        try:
            self._process.start(command[0], command[1:])
            if not self._process.waitForStarted(5000):
                self._set_state(LspState.ERROR)
                self.error_occurred.emit(
                    f"无法启动语言服务器: {command[0]}"
                )
                return
        except Exception as e:
            self._set_state(LspState.ERROR)
            self.error_occurred.emit(f"启动失败: {e}")
            return

        # 启动超时检查
        self._timeout_timer.start()

        # 状态变更
        self._set_state(LspState.INITIALIZING)

    def stop(self):
        """停止语言服务器"""
        if not self._process:
            return

        self._set_state(LspState.SHUTTING_DOWN)

        # 发送 shutdown 请求
        if self.is_initialized:
            try:
                self._send_request("shutdown", None, timeout_ms=2000)
                self._send_notification("exit", None)
            except Exception:
                pass

        # 等待进程退出
        try:
            if self._process.state() != QProcess.NotRunning:
                self._process.terminate()
                if not self._process.waitForFinished(3000):
                    self._process.kill()
                    self._process.waitForFinished(1000)
        except Exception:
            pass

        # 清理
        self._cleanup()

    def restart(self):
        """重启语言服务器"""
        if self._restart_count >= MAX_RESTART_ATTEMPTS:
            self._set_state(LspState.ERROR)
            self.error_occurred.emit(
                f"重启次数超过上限 ({MAX_RESTART_ATTEMPTS})"
            )
            return

        self._restart_count += 1
        self._set_state(LspState.RESTARTING)

        # 停止旧进程
        self.stop()

        # 延迟重启
        QTimer.singleShot(RESTART_DELAY_MS, self._do_restart)

    def _do_restart(self):
        """执行重启"""
        try:
            command = self._command
            working_dir = self._working_dir
            env = self._env

            self.start(command, working_dir, env)

            # 重新初始化
            if self._root_uri:
                self.initialize(self._root_uri)

            self.server_restarted.emit()

        except Exception as e:
            self._set_state(LspState.ERROR)
            self.error_occurred.emit(f"重启失败: {e}")

    def _cleanup(self):
        """清理资源"""
        # 取消所有待处理请求
        for req in self._pending.values():
            req.fail(LspError(-1, "客户端已停止"))
        self._pending.clear()

        # 清空缓冲
        self._buffer = b''
        self._header_buffer = b''
        self._content_length = 0
        self._reading_header = True

        # 清空状态
        self._init_completed = False
        self._doc_versions.clear()
        self._open_documents.clear()
        self.capabilities = {}
        self.server_info = {}

        # 停止定时器
        self._timeout_timer.stop()

        # 重置进程
        if self._process:
            try:
                self._process.deleteLater()
            except Exception:
                pass
            self._process = None

        self._set_state(LspState.STOPPED)

    # ========================================================
    # 生命周期
    # ========================================================
    def initialize(self, root_uri: str,
                   capabilities: Optional[Dict[str, Any]] = None,
                   initialization_options: Optional[Dict[str, Any]] = None):
        """
        初始化语言服务器。

        参数:
            root_uri: 项目根 URI（如 "file:///home/user/project"）
            capabilities: 客户端能力
            initialization_options: 初始化选项
        """
        if not self._process:
            self.error_occurred.emit("进程未启动")
            return

        self._root_uri = root_uri

        # 默认客户端能力
        if capabilities is None:
            capabilities = self._default_capabilities()

        params = {
            "processId": os.getpid(),
            "rootUri": root_uri,
            "rootPath": self._uri_to_path(root_uri),
            "capabilities": capabilities,
        }

        if initialization_options:
            params["initializationOptions"] = initialization_options

        # 发送 initialize 请求
        self._send_request(
            "initialize", params,
            callback=self._on_initialize_response,
            timeout_ms=DEFAULT_INIT_TIMEOUT
        )

    def _default_capabilities(self) -> Dict[str, Any]:
        """默认客户端能力"""
        return {
            "workspace": {
                "applyEdit": True,
                "workspaceEdit": {
                    "documentChanges": True,
                },
                "didChangeConfiguration": {
                    "dynamicRegistration": False,
                },
                "didChangeWatchedFiles": {
                    "dynamicRegistration": False,
                },
                "symbol": {
                    "dynamicRegistration": False,
                },
                "executeCommand": {
                    "dynamicRegistration": False,
                },
            },
            "textDocument": {
                "synchronization": {
                    "dynamicRegistration": False,
                    "willSave": True,
                    "willSaveWaitUntil": True,
                    "didSave": True,
                },
                "completion": {
                    "dynamicRegistration": False,
                    "completionItem": {
                        "snippetSupport": True,
                        "commitCharactersSupport": True,
                        "documentationFormat": ["markdown", "plaintext"],
                        "resolveSupport": {
                            "properties": ["documentation", "detail"],
                        },
                    },
                    "completionItemKind": {
                        "valueSet": list(range(1, 26)),
                    },
                },
                "hover": {
                    "dynamicRegistration": False,
                    "contentFormat": ["markdown", "plaintext"],
                },
                "signatureHelp": {
                    "dynamicRegistration": False,
                    "signatureInformation": {
                        "documentationFormat": ["markdown", "plaintext"],
                        "parameterInformation": {
                            "labelOffsetSupport": True,
                        },
                    },
                },
                "references": {
                    "dynamicRegistration": False,
                },
                "documentHighlight": {
                    "dynamicRegistration": False,
                },
                "documentSymbol": {
                    "dynamicRegistration": False,
                    "hierarchicalDocumentSymbolSupport": True,
                    "symbolKind": {
                        "valueSet": list(range(1, 27)),
                    },
                },
                "formatting": {
                    "dynamicRegistration": False,
                },
                "rangeFormatting": {
                    "dynamicRegistration": False,
                },
                "onTypeFormatting": {
                    "dynamicRegistration": False,
                },
                "definition": {
                    "dynamicRegistration": False,
                    "linkSupport": True,
                },
                "codeAction": {
                    "dynamicRegistration": False,
                    "codeActionLiteralSupport": {
                        "codeActionKind": {
                            "valueSet": [
                                "quickfix",
                                "refactor",
                                "refactor.extract",
                                "refactor.inline",
                                "refactor.rewrite",
                                "source",
                                "source.organizeImports",
                            ],
                        },
                    },
                },
                "codeLens": {
                    "dynamicRegistration": False,
                },
                "documentLink": {
                    "dynamicRegistration": False,
                },
                "rename": {
                    "dynamicRegistration": False,
                    "prepareSupport": True,
                },
                "publishDiagnostics": {
                    "relatedInformation": True,
                    "versionSupport": True,
                    "tagSupport": {
                        "valueSet": [1, 2],
                    },
                },
            },
            "window": {
                "workDoneProgress": True,
                "showMessage": {},
                "showDocument": {
                    "support": True,
                },
            },
            "general": {
                "positionEncodings": ["utf-16"],
            },
        }

    def _on_initialize_response(self, result: Any):
        """initialize 响应回调"""
        if isinstance(result, dict):
            self.capabilities = result.get("capabilities", {})
            self.server_info = result.get("serverInfo", {})
        else:
            self.capabilities = {}
            self.server_info = {}

        # 发送 initialized 通知
        self._send_notification("initialized", {})

        self._init_completed = True
        self._set_state(LspState.RUNNING)

        self.initialized.emit(self.capabilities)

    # ========================================================
    # 文档同步
    # ========================================================
    def did_open(self, uri: str, language_id: str, text: str,
                 version: int = 1):
        """
        通知服务器文档已打开。

        参数:
            uri: 文档 URI
            language_id: 语言 ID（如 "python"）
            text: 文档内容
            version: 版本号
        """
        self._doc_versions[uri] = version
        self._open_documents[uri] = language_id

        params = {
            "textDocument": {
                "uri": uri,
                "languageId": language_id,
                "version": version,
                "text": text,
            }
        }

        self._send_notification("textDocument/didOpen", params)

    def did_change(self, uri: str, text: str,
                   version: Optional[int] = None,
                   range_data: Optional[Dict] = None):
        """
        通知服务器文档已变更。

        参数:
            uri: 文档 URI
            text: 新的内容（全量）或增量文本
            version: 版本号（自增）
            range_data: 增量变更的范围数据（可选）
        """
        if uri not in self._doc_versions:
            # 未打开，先记录
            self._doc_versions[uri] = 1

        if version is None:
            self._doc_versions[uri] += 1
            version = self._doc_versions[uri]
        else:
            self._doc_versions[uri] = version

        if range_data:
            # 增量变更
            content_change = {
                "range": range_data,
                "text": text,
            }
        else:
            # 全量变更
            content_change = {
                "text": text,
            }

        params = {
            "textDocument": {
                "uri": uri,
                "version": version,
            },
            "contentChanges": [content_change],
        }

        self._send_notification("textDocument/didChange", params)

    def did_save(self, uri: str, text: Optional[str] = None):
        """
        通知服务器文档已保存。

        参数:
            uri: 文档 URI
            text: 保存的文本（可选）
        """
        params = {
            "textDocument": {
                "uri": uri,
            }
        }
        if text is not None:
            params["text"] = text

        self._send_notification("textDocument/didSave", params)

    def did_close(self, uri: str):
        """通知服务器文档已关闭"""
        params = {
            "textDocument": {
                "uri": uri,
            }
        }

        self._send_notification("textDocument/didClose", params)

        self._doc_versions.pop(uri, None)
        self._open_documents.pop(uri, None)

    def did_change_configuration(self, settings: Dict[str, Any]):
        """通知服务器配置变更"""
        params = {"settings": settings}
        self._send_notification("workspace/didChangeConfiguration", params)

    def did_change_watched_files(self, changes: List[Dict[str, Any]]):
        """通知服务器监视文件变更"""
        params = {"changes": changes}
        self._send_notification(
            "workspace/didChangeWatchedFiles", params
        )

    # ========================================================
    # 语言功能请求
    # ========================================================
    def request_completion(self, uri: str, line: int, character: int,
                           context: Optional[Dict] = None):
        """
        请求补全。

        参数:
            uri: 文档 URI
            line: 行号（从 0 开始）
            character: 列号（从 0 开始）
            context: 补全上下文（可选）
        """
        if not self.is_running:
            return

        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
        }

        if context:
            params["context"] = context

        self._send_request(
            "textDocument/completion", params,
            callback=self._on_completion_response,
            timeout_ms=5000,
        )

    def _on_completion_response(self, result: Any):
        """补全响应回调"""
        if result is None:
            items = []
        elif isinstance(result, list):
            items = result
        elif isinstance(result, dict):
            items = result.get("items", [])
        else:
            items = []

        self.completion_ready.emit(items)

    def request_hover(self, uri: str, line: int, character: int):
        """请求悬停信息"""
        if not self.is_running:
            return

        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
        }

        self._send_request(
            "textDocument/hover", params,
            callback=self._on_hover_response,
            timeout_ms=5000,
        )

    def _on_hover_response(self, result: Any):
        """悬停响应回调"""
        self.hover_ready.emit(result if isinstance(result, dict) else {})

    def request_definition(self, uri: str, line: int, character: int):
        """请求跳转定义"""
        if not self.is_running:
            return

        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
        }

        self._send_request(
            "textDocument/definition", params,
            callback=self._on_definition_response,
            timeout_ms=5000,
        )

    def _on_definition_response(self, result: Any):
        """定义响应回调"""
        if result is None:
            locations = []
        elif isinstance(result, list):
            locations = result
        elif isinstance(result, dict):
            locations = [result]
        else:
            locations = []

        self.definition_ready.emit(locations)

    def request_references(self, uri: str, line: int, character: int,
                           include_declaration: bool = True):
        """请求查找引用"""
        if not self.is_running:
            return

        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "context": {
                "includeDeclaration": include_declaration,
            },
        }

        self._send_request(
            "textDocument/references", params,
            callback=self._on_references_response,
            timeout_ms=10000,
        )

    def _on_references_response(self, result: Any):
        """引用响应回调"""
        self.references_ready.emit(result if isinstance(result, list) else [])

    def request_rename(self, uri: str, line: int, character: int,
                       new_name: str):
        """请求重命名"""
        if not self.is_running:
            return

        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "newName": new_name,
        }

        self._send_request(
            "textDocument/rename", params,
            callback=self._on_rename_response,
            timeout_ms=10000,
        )

    def _on_rename_response(self, result: Any):
        """重命名响应回调"""
        self.rename_ready.emit(result if isinstance(result, dict) else {})

    def request_document_symbols(self, uri: str):
        """请求文档符号"""
        if not self.is_running:
            return

        params = {
            "textDocument": {"uri": uri},
        }

        self._send_request(
            "textDocument/documentSymbol", params,
            callback=self._on_document_symbols_response,
            timeout_ms=10000,
        )

    def _on_document_symbols_response(self, result: Any):
        """文档符号响应回调"""
        self.document_symbols_ready.emit(result if isinstance(result, list) else [])

    def request_code_actions(self, uri: str,
                             range_data: Dict[str, Any],
                             context: Dict[str, Any]):
        """请求代码操作"""
        if not self.is_running:
            return

        params = {
            "textDocument": {"uri": uri},
            "range": range_data,
            "context": context,
        }

        self._send_request(
            "textDocument/codeAction", params,
            callback=self._on_code_actions_response,
            timeout_ms=10000,
        )

    def _on_code_actions_response(self, result: Any):
        """代码操作响应回调"""
        self.code_actions_ready.emit(result if isinstance(result, list) else [])

    def request_formatting(self, uri: str,
                           options: Optional[Dict] = None):
        """请求格式化整个文档"""
        if not self.is_running:
            return

        if options is None:
            options = {
                "tabSize": 4,
                "insertSpaces": True,
            }

        params = {
            "textDocument": {"uri": uri},
            "options": options,
        }

        self._send_request(
            "textDocument/formatting", params,
            callback=self._on_formatting_response,
            timeout_ms=15000,
        )

    def _on_formatting_response(self, result: Any):
        """格式化响应回调"""
        self.formatting_ready.emit(result if isinstance(result, list) else [])

    def request_signature_help(self, uri: str, line: int, character: int):
        """请求签名帮助"""
        if not self.is_running:
            return

        params = {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
        }

        self._send_request(
            "textDocument/signatureHelp", params,
            callback=self._on_signature_help_response,
            timeout_ms=5000,
        )

    def _on_signature_help_response(self, result: Any):
        """签名帮助响应回调"""
        self.signature_help_ready.emit(result if isinstance(result, dict) else {})

    # ========================================================
    # 消息发送
    # ========================================================
    def _next_request_id(self) -> int:
        """获取下一个请求 ID"""
        with self._id_lock:
            rid = self._next_id
            self._next_id += 1
            return rid

    def _send_request(self, method: str, params: Any,
                      callback: Optional[Callable] = None,
                      timeout_ms: int = DEFAULT_REQUEST_TIMEOUT) -> Optional[int]:
        """
        发送请求（需要响应）。

        参数:
            method: 方法名
            params: 参数
            callback: 响应回调
            timeout_ms: 超时（毫秒）

        返回:
            请求 ID 或 None（失败时）
        """
        if not self._process or self._process.state() == QProcess.NotRunning:
            if callback:
                try:
                    callback(None)
                except Exception:
                    pass
            return None

        request_id = self._next_request_id()

        message = {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "method": method,
            "params": params if params is not None else {},
        }

        # 记录待处理请求
        pending = PendingRequest(request_id, method, callback, timeout_ms)
        self._pending[request_id] = pending

        # 发送
        if not self._write_message(message):
            self._pending.pop(request_id, None)
            return None

        return request_id

    def _send_notification(self, method: str, params: Any) -> bool:
        """
        发送通知（无需响应）。

        参数:
            method: 方法名
            params: 参数

        返回:
            是否成功发送
        """
        if not self._process or self._process.state() == QProcess.NotRunning:
            return False

        message = {
            "jsonrpc": JSONRPC_VERSION,
            "method": method,
        }
        if params is not None:
            message["params"] = params

        return self._write_message(message)

    def _write_message(self, message: Dict[str, Any]) -> bool:
        """
        写入消息到进程。

        使用 Content-Length 头的标准 LSP 分帧格式。

        参数:
            message: 消息字典

        返回:
            是否成功
        """
        if not self._process:
            return False

        try:
            # 序列化 JSON
            body = json.dumps(message, ensure_ascii=False)
            body_bytes = body.encode('utf-8')

            # 构建消息
            header = f"Content-Length: {len(body_bytes)}\r\n\r\n"
            header_bytes = header.encode('ascii')

            full_message = header_bytes + body_bytes

            # 写入
            written = self._process.write(full_message)

            if written == -1:
                self.error_occurred.emit("写入进程失败")
                return False

            return True

        except Exception as e:
            self.error_occurred.emit(f"发送消息失败: {e}")
            return False

    # ========================================================
    # 消息接收
    # ========================================================
    def _on_stdout(self):
        """标准输出回调（接收消息）"""
        if not self._process:
            return

        try:
            data = self._process.readAllStandardOutput().data()
            if data:
                self._buffer += data
                self._process_buffer()
        except Exception as e:
            self.error_occurred.emit(f"读取输出失败: {e}")

    def _on_stderr(self):
        """标准错误回调（记录日志）"""
        if not self._process:
            return

        try:
            data = self._process.readAllStandardError().data()
            if data:
                text = data.decode('utf-8', errors='replace')
                self.log_message.emit(text.strip(), 1)
        except Exception:
            pass

    def _process_buffer(self):
        """处理缓冲区（解析消息）"""
        while True:
            if self._reading_header:
                # 寻找 \r\n\r\n
                idx = self._buffer.find(b'\r\n\r\n')
                if idx < 0:
                    # 检查消息是否过大
                    if len(self._buffer) > 8192:
                        self.error_occurred.emit("消息头异常")
                        self._buffer = b''
                    return

                header = self._buffer[:idx].decode('ascii', errors='replace')
                self._buffer = self._buffer[idx + 4:]

                # 解析 Content-Length
                self._content_length = 0
                for line in header.split('\r\n'):
                    if line.lower().startswith('content-length:'):
                        try:
                            self._content_length = int(line.split(':', 1)[1].strip())
                        except (ValueError, IndexError):
                            pass

                if self._content_length <= 0:
                    # 无效消息
                    self._reading_header = True
                    continue

                if self._content_length > MAX_MESSAGE_SIZE:
                    self.error_occurred.emit(
                        f"消息过大: {self._content_length} 字节"
                    )
                    self._buffer = b''
                    self._reading_header = True
                    continue

                self._reading_header = False

            else:
                # 读取消息体
                if len(self._buffer) < self._content_length:
                    return

                body = self._buffer[:self._content_length]
                self._buffer = self._buffer[self._content_length:]
                self._reading_header = True

                # 解析 JSON
                try:
                    message = json.loads(body.decode('utf-8'))
                    self._handle_message(message)
                except json.JSONDecodeError as e:
                    self.error_occurred.emit(f"JSON 解析失败: {e}")
                except Exception as e:
                    self.error_occurred.emit(f"处理消息失败: {e}")

    def _handle_message(self, message: Dict[str, Any]):
        """
        处理接收到的消息。

        根据消息类型分派：
        - 有 id 和 result：响应
        - 有 id 和 error：错误响应
        - 只有 method：通知
        - 有 method 和 id：服务器请求
        """
        # 响应
        if "id" in message and ("result" in message or "error" in message):
            self._handle_response(message)
            return

        # 通知
        if "method" in message and "id" not in message:
            self._handle_notification(message)
            return

        # 服务器请求（需要响应）
        if "method" in message and "id" in message:
            self._handle_server_request(message)
            return

    def _handle_response(self, message: Dict[str, Any]):
        """处理响应消息"""
        request_id = message.get("id")
        if request_id is None:
            return

        pending = self._pending.pop(request_id, None)
        if pending is None:
            # 未知请求 ID（可能已超时）
            return

        if "error" in message:
            error_data = message["error"]
            error = LspError(
                error_data.get("code", -1),
                error_data.get("message", "未知错误"),
                error_data.get("data"),
            )
            pending.fail(error)

            # 调用回调（带错误）
            if pending.callback:
                try:
                    pending.callback(None)
                except Exception:
                    pass

            self.error_occurred.emit(
                f"请求 {pending.method} 失败: {error.message}"
            )
        else:
            result = message.get("result")
            pending.complete(result)

            # 调用回调
            if pending.callback:
                try:
                    pending.callback(result)
                except Exception as e:
                    self.error_occurred.emit(f"回调异常: {e}")

    def _handle_notification(self, message: Dict[str, Any]):
        """处理通知消息"""
        method = message.get("method", "")
        params = message.get("params", {})

        # 内置处理
        if method == "textDocument/publishDiagnostics":
            uri = params.get("uri", "")
            diagnostics = params.get("diagnostics", [])
            self.diagnostics_updated.emit(uri, diagnostics)

        elif method == "window/showMessage":
            msg = params.get("message", "")
            msg_type = params.get("type", 1)
            self.log_message.emit(msg, msg_type)

        elif method == "window/logMessage":
            msg = params.get("message", "")
            msg_type = params.get("type", 4)
            self.log_message.emit(msg, msg_type)

        elif method == "telemetry/event":
            # 遥测，忽略
            pass

        elif method == "$/progress":
            # 进度报告
            pass

        # 调用自定义处理器
        handlers = self._notification_handlers.get(method, [])
        for handler in handlers:
            try:
                handler(params)
            except Exception as e:
                self.error_occurred.emit(f"通知处理器异常: {e}")

    def _handle_server_request(self, message: Dict[str, Any]):
        """处理服务器主动请求"""
        request_id = message.get("id")
        method = message.get("method", "")
        params = message.get("params", {})

        # 默认响应
        response: Any = None

        if method == "workspace/applyEdit":
            # 应用编辑（暂不实现）
            response = {"applied": False}

        elif method == "window/showMessageRequest":
            # 显示消息请求
            response = None

        elif method == "workspace/configuration":
            # 配置请求
            items = params.get("items", [])
            response = [{} for _ in items]

        elif method == "client/registerCapability":
            # 注册能力
            response = None

        elif method == "client/unregisterCapability":
            # 注销能力
            response = None

        # 发送响应
        if request_id is not None:
            response_message = {
                "jsonrpc": JSONRPC_VERSION,
                "id": request_id,
                "result": response,
            }
            self._write_message(response_message)

    # ========================================================
    # 通知订阅
    # ========================================================
    def register_notification_handler(self, method: str,
                                       handler: Callable[[Dict], None]):
        """
        注册自定义通知处理器。

        参数:
            method: 通知方法名
            handler: 回调函数（接收 params 字典）
        """
        self._notification_handlers.setdefault(method, []).append(handler)

    def unregister_notification_handler(self, method: str,
                                         handler: Callable):
        """注销通知处理器"""
        handlers = self._notification_handlers.get(method, [])
        if handler in handlers:
            handlers.remove(handler)

    # ========================================================
    # 超时检查
    # ========================================================
    def _check_timeouts(self):
        """检查超时的请求"""
        expired = []
        for request_id, pending in self._pending.items():
            if pending.is_expired():
                expired.append(request_id)

        for request_id in expired:
            pending = self._pending.pop(request_id, None)
            if pending:
                error = LspTimeoutError(pending.method)
                pending.fail(error)

                if pending.callback:
                    try:
                        pending.callback(None)
                    except Exception:
                        pass

                self.error_occurred.emit(
                    f"请求超时: {pending.method}"
                )

    # ========================================================
    # 进程事件
    # ========================================================
    def _on_process_finished(self, exit_code: int, exit_status):
        """进程退出回调"""
        was_running = self._state in (LspState.RUNNING, LspState.INITIALIZING)

        self._cleanup()

        if was_running:
            self.server_crashed.emit(exit_code)
            self.error_occurred.emit(
                f"语言服务器意外退出 (退出码: {exit_code})"
            )

            # 自动重启
            if self._restart_count < MAX_RESTART_ATTEMPTS:
                QTimer.singleShot(RESTART_DELAY_MS, self.restart)

    def _on_process_error(self, error):
        """进程错误回调"""
        error_map = {
            QProcess.FailedToStart: "启动失败",
            QProcess.Crashed: "进程崩溃",
            QProcess.Timedout: "超时",
            QProcess.WriteError: "写入错误",
            QProcess.ReadError: "读取错误",
            QProcess.UnknownError: "未知错误",
        }
        error_msg = error_map.get(error, f"错误码 {error}")

        self._set_state(LspState.ERROR)
        self.error_occurred.emit(f"进程错误: {error_msg}")

    # ========================================================
    # URI 工具
    # ========================================================
    @staticmethod
    def path_to_uri(filepath: str) -> str:
        """
        将文件路径转换为 URI。

        参数:
            filepath: 文件路径

        返回:
            file:// 格式的 URI

        修复说明（P1-7）:
            - 原实现在 Windows 路径处理时会再给已带前导 `/` 的路径
              加一次 `/`，导致 `file:////C:/...`（多了一个斜杠）。
            - 已删除多余的盘符加斜杠逻辑，`file://` + `/C:/...`
              即得到正确的 `file:///C:/...`。
        """
        if not filepath:
            return ""

        # Windows 路径处理
        if sys.platform == 'win32':
            filepath = filepath.replace('\\', '/')
            if not filepath.startswith('/'):
                filepath = '/' + filepath

        # URL 编码
        from urllib.parse import quote
        # 只编码路径部分，保留 /:
        encoded = quote(filepath, safe='/:')

        return f"file://{encoded}"

    @staticmethod
    def uri_to_path(uri: str) -> str:
        """
        将 URI 转换为文件路径。

        参数:
            uri: file:// 格式的 URI

        返回:
            文件路径
        """
        if not uri:
            return ""

        try:
            parsed = urlparse(uri)
            path = unquote(parsed.path)

            # Windows 路径处理
            if sys.platform == 'win32':
                if path.startswith('/') and len(path) > 2 and path[2] == ':':
                    path = path[1:]

            return path
        except Exception:
            return uri

    # ========================================================
    # 信息查询
    # ========================================================
    def get_server_info(self) -> Dict[str, Any]:
        """获取服务器信息"""
        return {
            'state': self._state.name,
            'initialized': self._init_completed,
            'capabilities': self.capabilities,
            'server_info': self.server_info,
            'pending_requests': len(self._pending),
            'open_documents': len(self._open_documents),
            'restart_count': self._restart_count,
        }

    def supports(self, capability: str) -> bool:
        """
        检查服务器是否支持指定能力。

        参数:
            capability: 能力路径，如 "completionProvider" 或
                        "textDocumentSync.change"

        返回:
            是否支持
        """
        parts = capability.split('.')
        current = self.capabilities

        for part in parts:
            if not isinstance(current, dict):
                return False
            if part not in current:
                return False
            current = current[part]

        return bool(current) if current is not None else True

    def get_completion_trigger_characters(self) -> List[str]:
        """获取补全触发字符"""
        provider = self.capabilities.get("completionProvider", {})
        return provider.get("triggerCharacters", [])

    def get_signature_trigger_characters(self) -> List[str]:
        """获取签名帮助触发字符"""
        provider = self.capabilities.get("signatureHelpProvider", {})
        return provider.get("triggerCharacters", [])

    def get_sync_kind(self) -> int:
        """获取文档同步方式（0=无, 1=全量, 2=增量）"""
        sync = self.capabilities.get("textDocumentSync")
        if isinstance(sync, int):
            return sync
        elif isinstance(sync, dict):
            return sync.get("change", 0)
        return 0

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出客户端信息"""
        info = self.get_server_info()
        lines = ["LspClient", "=" * 60]
        lines.append(f"状态: {info['state']}")
        lines.append(f"已初始化: {info['initialized']}")
        lines.append(f"待处理请求: {info['pending_requests']}")
        lines.append(f"已打开文档: {info['open_documents']}")
        lines.append(f"重启次数: {info['restart_count']}")
        lines.append("")

        if self.server_info:
            name = self.server_info.get('name', '未知')
            version = self.server_info.get('version', '?')
            lines.append(f"服务器: {name} v{version}")

        lines.append("")
        lines.append("服务器能力:")
        for key in sorted(self.capabilities.keys()):
            lines.append(f"  - {key}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<LspClient state={self._state.name} "
                f"initialized={self._init_completed} "
                f"pending={len(self._pending)}>")


# ============================================================
# LSP 服务器注册表
# ============================================================
class LspServerRegistry:
    """
    LSP 服务器注册表。

    管理不同语言的 LSP 服务器命令。
    """

    _servers: Dict[str, Dict[str, Any]] = {
        'python': {
            'command': ['pylsp'],
            'extensions': ['.py', '.pyw'],
            'install': [sys.executable, '-m', 'pip', 'install',
                        'python-lsp-server'],
            'language_id': 'python',
        },
        'javascript': {
            'command': ['typescript-language-server', '--stdio'],
            'extensions': ['.js', '.jsx', '.ts', '.tsx'],
            'install': ['npm', 'install', '-g',
                        'typescript-language-server', 'typescript'],
            'language_id': 'javascript',
        },
        'rust': {
            'command': ['rust-analyzer'],
            'extensions': ['.rs'],
            'install': ['rustup', 'component', 'add', 'rust-analyzer'],
            'language_id': 'rust',
        },
        'go': {
            'command': ['gopls'],
            'extensions': ['.go'],
            'install': ['go', 'install',
                        'golang.org/x/tools/gopls@latest'],
            'language_id': 'go',
        },
        'cpp': {
            'command': ['clangd'],
            'extensions': ['.cpp', '.cc', '.cxx', '.h', '.hpp', '.c'],
            'install': [],  # 需手动安装
            'language_id': 'cpp',
        },
        'java': {
            'command': ['jdtls'],
            'extensions': ['.java'],
            'install': [],
            'language_id': 'java',
        },
    }

    @classmethod
    def register(cls, language: str, config: Dict[str, Any]):
        """注册语言服务器"""
        cls._servers[language] = config

    @classmethod
    def get(cls, language: str) -> Optional[Dict[str, Any]]:
        """获取语言服务器配置"""
        return cls._servers.get(language)

    @classmethod
    def detect_language(cls, filepath: str) -> Optional[str]:
        """
        根据文件路径检测语言。

        参数:
            filepath: 文件路径

        返回:
            语言标识或 None
        """
        if not filepath:
            return None

        ext = os.path.splitext(filepath)[1].lower()

        for lang, config in cls._servers.items():
            if ext in config.get('extensions', []):
                return lang

        return None

    @classmethod
    def get_command(cls, language: str) -> Optional[List[str]]:
        """获取指定语言的启动命令"""
        config = cls._servers.get(language)
        if config:
            return config.get('command')
        return None

    @classmethod
    def list_languages(cls) -> List[str]:
        """列出所有支持的语言"""
        return list(cls._servers.keys())


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QTimer

    app = QApplication(sys.argv)

    print("=== 测试 LspClient ===")

    client = LspClient()

    # 连接信号
    client.state_changed.connect(
        lambda s: print(f"[状态] {s}")
    )
    client.initialized.connect(
        lambda c: print(f"[初始化] 服务器能力: {len(c)} 项")
    )
    client.log_message.connect(
        lambda msg, t: print(f"[日志 {t}] {msg[:100]}")
    )
    client.error_occurred.connect(
        lambda e: print(f"[错误] {e}")
    )
    client.diagnostics_updated.connect(
        lambda uri, diags: print(f"[诊断] {uri}: {len(diags)} 条")
    )
    client.completion_ready.connect(
        lambda items: print(f"[补全] {len(items)} 项")
    )

    # 检测 Python 语言
    lang = LspServerRegistry.detect_language(__file__)
    print(f"检测到的语言: {lang}")

    command = LspServerRegistry.get_command(lang)
    print(f"启动命令: {command}")

    # 检查 pylsp 是否已安装
    import shutil
    if command and shutil.which(command[0]):
        print(f"pylsp 已安装，可以测试完整流程")

        # 启动
        client.start(command)

        # 延迟初始化
        def do_init():
            if client.is_running or client.state == LspState.INITIALIZING:
                root_uri = LspClient.path_to_uri(os.path.dirname(__file__))
                print(f"根 URI: {root_uri}")
                client.initialize(root_uri)

        QTimer.singleShot(2000, do_init)

        # 延迟关闭
        def do_stop():
            print()
            print(client.dump())
            client.stop()
            app.quit()

        QTimer.singleShot(8000, do_stop)
    else:
        print("pylsp 未安装，跳过实际连接测试")
        print("安装命令: pip install python-lsp-server")

        # 测试 URI 工具
        print()
        print("=== 测试 URI 工具 ===")
        test_paths = [
            '/home/user/test.py',
            'C:\\Users\\test\\file.py' if sys.platform == 'win32'
            else '/tmp/file.py',
            '/path with space/file.py',
        ]
        for p in test_paths:
            uri = LspClient.path_to_uri(p)
            back = LspClient.uri_to_path(uri)
            print(f"  {p} -> {uri} -> {back}")

        print()
        print("=== 测试服务器注册表 ===")
        for lang in LspServerRegistry.list_languages():
            config = LspServerRegistry.get(lang)
            cmd = config.get('command', [])
            print(f"  {lang}: {' '.join(cmd)}")

        app.quit()

    sys.exit(app.exec())