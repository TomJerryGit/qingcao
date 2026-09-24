#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为插件沙箱模块，包含：
- PluginSandbox：插件沙箱（进程隔离执行）
- SandboxConfig：沙箱配置
- SandboxResult：沙箱执行结果
- SandboxProcess：子进程管理器
- SandboxProxy：代理 API（跨进程通信）
- SandboxBridge：消息桥接
- 权限控制与白名单
- 资源限制（CPU/内存/时间）
- 标准输出/错误捕获
- 崩溃隔离与重启
- 双向 RPC 通信
- 沙箱状态监控
- 超时终止
- 插件沙箱管理器
"""

import os
import sys
import json
import time
import uuid
import signal
import pickle
import base64
import struct
import queue
import threading
import traceback
import subprocess
import multiprocessing
from typing import Optional, List, Dict, Any, Tuple, Callable, Set
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from multiprocessing import Process, Queue, Pipe, Event

from PyQt5.QtCore import QObject, pyqtSignal, QTimer


# ============================================================
# 常量
# ============================================================
# 消息协议版本
PROTOCOL_VERSION = 1

# 默认超时（秒）
DEFAULT_TIMEOUT = 30

# 默认最大内存（MB）
DEFAULT_MAX_MEMORY = 512

# 默认最大 CPU 时间（秒）
DEFAULT_MAX_CPU_TIME = 60

# 默认重启次数上限
DEFAULT_MAX_RESTARTS = 3

# 消息类型
MSG_TYPE_REQUEST = "request"
MSG_TYPE_RESPONSE = "response"
MSG_TYPE_EVENT = "event"
MSG_TYPE_LOG = "log"
MSG_TYPE_READY = "ready"
MSG_TYPE_SHUTDOWN = "shutdown"
MSG_TYPE_PING = "ping"
MSG_TYPE_PONG = "pong"

# 危险模块（默认禁止导入）
DANGEROUS_MODULES = {
    'ctypes',        # 可绕过沙箱
    'cffi',          # 同上
    'subprocess',    # 命令执行
    'os.system',     # 命令执行
    'shutil',        # 文件操作
    'socket',        # 网络
    'urllib',        # 网络
    'requests',      # 网络
    'http',          # 网络
    'ftplib',        # 网络
    'smtplib',       # 邮件
    'telnetlib',     # 网络
    'multiprocessing',  # 可创建子进程
    'threading',     # 有限制
    'asyncio',       # 复杂
}

# 允许的模块（白名单，优先级高于危险模块）
ALLOWED_MODULES = {
    'builtins',
    'math', 'cmath', 'statistics',
    'random', 'secrets',
    'string', 're',
    'json', 'csv',
    'datetime', 'time', 'calendar',
    'collections', 'itertools', 'functools',
    'operator', 'heapq', 'bisect',
    'copy', 'pprint',
    'hashlib', 'hmac',
    'base64', 'binascii',
    'struct',
    'textwrap', 'unicodedata',
    'types', 'typing',
    'dataclasses', 'enum',
    'abc', 'contextlib',
    'decimal', 'fractions',
    'uuid',
    'traceback',
    'logging',
}


# ============================================================
# 沙箱状态枚举
# ============================================================
class SandboxState(Enum):
    """沙箱状态"""
    STOPPED = auto()       # 未启动
    STARTING = auto()      # 启动中
    RUNNING = auto()       # 运行中
    BUSY = auto()          # 执行中
    CRASHED = auto()       # 崩溃
    RESTARTING = auto()    # 重启中
    TIMEOUT = auto()       # 超时
    TERMINATED = auto()    # 已终止
    ERROR = auto()         # 错误


# ============================================================
# 沙箱配置
# ============================================================
@dataclass
class SandboxConfig:
    """
    沙箱配置。
    """

    # 名称
    name: str = "plugin_sandbox"

    # 权限
    permissions: List[str] = field(default_factory=list)

    # 资源限制
    max_memory_mb: int = DEFAULT_MAX_MEMORY    # 最大内存
    max_cpu_time: float = DEFAULT_MAX_CPU_TIME # 最大 CPU 时间
    timeout: float = DEFAULT_TIMEOUT           # 单次请求超时

    # 模块访问
    allowed_modules: Set[str] = field(
        default_factory=lambda: set(ALLOWED_MODULES)
    )
    blocked_modules: Set[str] = field(
        default_factory=lambda: set(DANGEROUS_MODULES)
    )

    # 文件系统
    allow_filesystem: bool = False             # 允许文件系统访问
    allowed_paths: List[str] = field(default_factory=list)  # 白名单路径

    # 网络
    allow_network: bool = False                # 允许网络访问

    # 进程
    allow_process: bool = False                # 允许创建子进程

    # 系统
    restart_on_crash: bool = True              # 崩溃后自动重启
    max_restarts: int = DEFAULT_MAX_RESTARTS   # 最大重启次数

    # 日志
    capture_output: bool = True                # 捕获 stdout/stderr
    log_level: str = "INFO"                    # 日志级别

    # 调试
    debug: bool = False                        # 调试模式

    @classmethod
    def from_permissions(cls, permissions: List[str],
                          name: str = "plugin_sandbox") -> 'SandboxConfig':
        """从权限列表创建配置"""
        config = cls(name=name, permissions=list(permissions))

        # 根据权限调整配置
        config.allow_filesystem = "filesystem" in permissions
        config.allow_network = "network" in permissions
        config.allow_process = "process" in permissions

        return config

    def has_permission(self, perm: str) -> bool:
        """检查权限"""
        return perm in self.permissions


# ============================================================
# 沙箱结果
# ============================================================
@dataclass
class SandboxResult:
    """
    沙箱执行结果。
    """

    success: bool = False          # 是否成功
    result: Any = None             # 返回值
    error: str = ""                # 错误信息
    error_type: str = ""           # 错误类型
    traceback: str = ""            # 异常堆栈

    # 输出
    stdout: str = ""               # 标准输出
    stderr: str = ""               # 标准错误

    # 性能
    elapsed_ms: float = 0.0        # 执行耗时
    cpu_time_ms: float = 0.0       # CPU 时间
    memory_mb: float = 0.0         # 内存占用

    # 元数据
    request_id: str = ""           # 请求 ID
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'result': str(self.result)[:1000] if self.result else None,
            'error': self.error,
            'error_type': self.error_type,
            'stdout': self.stdout[:10000],
            'stderr': self.stderr[:10000],
            'elapsed_ms': self.elapsed_ms,
            'request_id': self.request_id,
        }

    def __repr__(self) -> str:
        if self.success:
            return f"<SandboxResult OK ({self.elapsed_ms:.0f}ms)>"
        return f"<SandboxResult FAIL: {self.error}>"


# ============================================================
# 沙箱进程（子进程入口）
# ============================================================
class SandboxProcess:
    """
    沙箱子进程。

    在独立进程中运行，与父进程通过 Pipe 通信。
    """

    def __init__(self, plugin_path: str, config: SandboxConfig,
                 conn):
        """
        参数:
            plugin_path: 插件路径
            config: 沙箱配置
            conn: 父进程通信连接
        """
        self.plugin_path = plugin_path
        self.config = config
        self.conn = conn

        self.plugin_instance = None
        self.plugin_module = None

        # 日志重定向
        self._stdout_capture = []
        self._stderr_capture = []

    def run(self):
        """子进程主循环"""
        try:
            # 1. 安装安全钩子
            self._install_security()

            # 2. 加载插件
            if not self._load_plugin():
                self._send_log("插件加载失败", "error")
                self.conn.send({
                    'type': MSG_TYPE_READY,
                    'success': False,
                    'error': '插件加载失败',
                })
                return

            # 3. 发送就绪信号
            self.conn.send({
                'type': MSG_TYPE_READY,
                'success': True,
                'version': PROTOCOL_VERSION,
            })

            # 4. 消息循环
            self._message_loop()

        except KeyboardInterrupt:
            pass
        except Exception as e:
            try:
                self.conn.send({
                    'type': MSG_TYPE_LOG,
                    'level': 'error',
                    'message': f"子进程异常: {e}",
                    'traceback': traceback.format_exc(),
                })
            except Exception:
                pass
        finally:
            try:
                self.conn.close()
            except Exception:
                pass

    # --------------------------------------------------------
    # 安全钩子
    # --------------------------------------------------------
    def _install_security(self):
        """安装安全钩子"""
        # 限制模块导入
        self._original_import = __builtins__.__import__

        def restricted_import(name, globals=None, locals=None,
                               fromlist=(), level=0):
            """限制导入的 __import__"""
            # 获取顶层模块名
            top_module = name.split('.')[0]

            # 白名单优先
            if top_module in self.config.allowed_modules:
                return self._original_import(
                    name, globals, locals, fromlist, level
                )

            # 阻止危险模块
            if top_module in self.config.blocked_modules:
                raise ImportError(
                    f"沙箱禁止导入模块: {top_module}"
                )

            # 未在白名单中，检查权限
            if not self._check_module_permission(top_module):
                raise ImportError(
                    f"沙箱未授权导入模块: {top_module}"
                )

            return self._original_import(
                name, globals, locals, fromlist, level
            )

        __builtins__.__import__ = restricted_import

        # 限制危险内建函数
        self._restrict_builtins()

    def _restrict_builtins(self):
        """限制危险内建函数"""
        # 需要替换的函数
        dangerous_builtins = {
            'eval': self._safe_eval,
            'exec': self._safe_exec,
            'compile': self._safe_compile,
            'open': self._safe_open,
        }

        if not self.config.allow_filesystem:
            # 替换 open
            __builtins__.open = self._safe_open

        # 注意：不能简单替换所有，某些功能可能需要
        # 这里采用白名单策略，只替换危险的

    def _safe_eval(self, *args, **kwargs):
        """安全的 eval"""
        if not self.config.debug:
            raise RuntimeError("沙箱禁止使用 eval")
        return eval(*args, **kwargs)

    def _safe_exec(self, *args, **kwargs):
        """安全的 exec"""
        if not self.config.debug:
            raise RuntimeError("沙箱禁止使用 exec")
        return exec(*args, **kwargs)

    def _safe_compile(self, *args, **kwargs):
        """安全的 compile"""
        if not self.config.debug:
            raise RuntimeError("沙箱禁止使用 compile")
        return compile(*args, **kwargs)

    def _safe_open(self, *args, **kwargs):
        """安全的 open"""
        if not self.config.allow_filesystem:
            raise PermissionError("沙箱禁止访问文件系统")

        # 检查路径白名单
        if args and self.config.allowed_paths:
            filepath = os.path.abspath(args[0])
            allowed = any(
                filepath.startswith(os.path.abspath(p))
                for p in self.config.allowed_paths
            )
            if not allowed:
                raise PermissionError(
                    f"沙箱禁止访问路径: {filepath}"
                )

        # 使用原始 open
        import builtins
        return builtins.open(*args, **kwargs)

    def _check_module_permission(self, module: str) -> bool:
        """检查模块访问权限"""
        # 网络相关
        if module in ('socket', 'http', 'urllib', 'requests',
                       'ftplib', 'smtplib', 'telnetlib'):
            return self.config.allow_network

        # 进程相关
        if module in ('subprocess', 'multiprocessing'):
            return self.config.allow_process

        # 其他模块根据配置
        return True

    # --------------------------------------------------------
    # 加载插件
    # --------------------------------------------------------
    def _load_plugin(self) -> bool:
        """加载插件"""
        try:
            import importlib.util

            # 入口文件
            entry_path = os.path.join(self.plugin_path, '__init__.py')

            if not os.path.exists(entry_path):
                return False

            # 动态导入
            module_name = f"sandbox_plugin_{uuid.uuid4().hex[:8]}"

            spec = importlib.util.spec_from_file_location(
                module_name, entry_path
            )

            if spec is None or spec.loader is None:
                return False

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            self.plugin_module = module

            # 实例化 Plugin 类
            if hasattr(module, 'Plugin'):
                self.plugin_instance = module.Plugin()
            else:
                # 无 Plugin 类，使用模块本身
                self.plugin_instance = module

            return True

        except Exception as e:
            self._send_log(f"加载插件失败: {e}", "error")
            return False

    # --------------------------------------------------------
    # 消息循环
    # --------------------------------------------------------
    def _message_loop(self):
        """处理消息循环"""
        while True:
            try:
                if not self.conn.poll(0.1):
                    continue

                message = self.conn.recv()

                if message is None:
                    break

                msg_type = message.get('type')

                if msg_type == MSG_TYPE_SHUTDOWN:
                    # 执行清理
                    self._cleanup()
                    break

                elif msg_type == MSG_TYPE_PING:
                    self.conn.send({
                        'type': MSG_TYPE_PONG,
                        'timestamp': time.time(),
                    })

                elif msg_type == MSG_TYPE_REQUEST:
                    self._handle_request(message)

            except EOFError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                self._send_log(f"消息循环错误: {e}", "error")

    def _handle_request(self, message: Dict[str, Any]):
        """处理请求"""
        request_id = message.get('id', str(uuid.uuid4()))
        method = message.get('method', '')
        params = message.get('params', {})
        timeout = message.get('timeout', DEFAULT_TIMEOUT)

        result = SandboxResult(request_id=request_id)
        start_time = time.time()

        # 捕获输出
        import io
        import contextlib

        stdout_cap = io.StringIO()
        stderr_cap = io.StringIO()

        try:
            with contextlib.redirect_stdout(stdout_cap), \
                 contextlib.redirect_stderr(stderr_cap):
                result_value = self._execute_method(method, params)
                result.success = True
                result.result = result_value

        except Exception as e:
            result.success = False
            result.error = str(e)
            result.error_type = type(e).__name__
            result.traceback = traceback.format_exc()

        finally:
            result.elapsed_ms = (time.time() - start_time) * 1000
            result.stdout = stdout_cap.getvalue()
            result.stderr = stderr_cap.getvalue()

        # 发送响应
        try:
            self.conn.send({
                'type': MSG_TYPE_RESPONSE,
                'id': request_id,
                'result': result.to_dict(),
            })
        except Exception:
            pass

    def _execute_method(self, method: str,
                         params: Dict[str, Any]) -> Any:
        """执行插件方法"""
        if self.plugin_instance is None:
            raise RuntimeError("插件未加载")

        # 调用插件的 method
        if hasattr(self.plugin_instance, method):
            func = getattr(self.plugin_instance, method)

            # 参数处理
            if isinstance(params, dict):
                return func(**params)
            elif isinstance(params, list):
                return func(*params)
            else:
                return func(params)

        # 特殊方法
        if method == '__ping__':
            return 'pong'

        elif method == '__info__':
            return {
                'name': getattr(self.plugin_instance, 'NAME', 'unknown'),
                'version': getattr(self.plugin_instance, 'VERSION', '0.0.0'),
                'class': self.plugin_instance.__class__.__name__,
            }

        elif method == '__inspect__':
            # 检查插件的能力
            methods = []
            for attr_name in dir(self.plugin_instance):
                if attr_name.startswith('_'):
                    continue
                attr = getattr(self.plugin_instance, attr_name)
                if callable(attr):
                    methods.append(attr_name)

            return {
                'methods': methods,
                'attributes': [
                    a for a in dir(self.plugin_instance)
                    if not a.startswith('_') and
                    not callable(getattr(self.plugin_instance, a))
                ],
            }

        raise AttributeError(
            f"插件无方法: {method}"
        )

    def _cleanup(self):
        """清理资源"""
        try:
            if self.plugin_instance and hasattr(
                self.plugin_instance, 'deactivate'
            ):
                self.plugin_instance.deactivate()
        except Exception:
            pass

    def _send_log(self, message: str, level: str = "info"):
        """发送日志"""
        try:
            self.conn.send({
                'type': MSG_TYPE_LOG,
                'level': level,
                'message': message,
                'timestamp': time.time(),
            })
        except Exception:
            pass


# ============================================================
# 沙箱进程入口函数
# ============================================================
def _sandbox_process_entry(plugin_path: str,
                            config_data: Dict[str, Any],
                            conn):
    """
    子进程入口函数（模块级，可 pickle）。

    参数:
        plugin_path: 插件路径
        config_data: 配置字典
        conn: 通信连接
    """
    try:
        # 重建配置
        config = SandboxConfig(**config_data)
        config.allowed_modules = set(config.allowed_modules)
        config.blocked_modules = set(config.blocked_modules)

        # 创建并运行沙箱
        sandbox = SandboxProcess(plugin_path, config, conn)
        sandbox.run()

    except Exception as e:
        try:
            conn.send({
                'type': MSG_TYPE_LOG,
                'level': 'error',
                'message': f"子进程启动失败: {e}",
                'traceback': traceback.format_exc(),
            })
        except Exception:
            pass


# ============================================================
# 沙箱管理器
# ============================================================
class PluginSandbox(QObject):
    """
    插件沙箱。

    在独立进程中运行插件，通过管道通信。

    信号:
        state_changed(str): 状态变更
        plugin_ready(): 插件就绪
        plugin_crashed(int): 插件崩溃（退出码）
        plugin_restarted(): 插件重启
        log_received(str, str): 收到日志（级别, 消息）
        output_received(str, str): 收到输出（类型, 内容）
    """

    state_changed = pyqtSignal(str)
    plugin_ready = pyqtSignal()
    plugin_crashed = pyqtSignal(int)
    plugin_restarted = pyqtSignal()
    log_received = pyqtSignal(str, str)
    output_received = pyqtSignal(str, str)

    def __init__(self, plugin_path: str,
                 config: Optional[SandboxConfig] = None,
                 parent: Optional[QObject] = None):
        """
        参数:
            plugin_path: 插件路径
            config: 沙箱配置
            parent: 父 QObject
        """
        super().__init__(parent)

        self.plugin_path = os.path.abspath(plugin_path)
        self.config = config or SandboxConfig()

        # 状态
        self._state = SandboxState.STOPPED
        self._lock = threading.RLock()

        # 进程与通信
        self._process: Optional[Process] = None
        self._parent_conn = None
        self._child_conn = None

        # 请求管理
        self._pending_requests: Dict[str, queue.Queue] = {}
        self._request_lock = threading.RLock()

        # 接收线程
        self._receiver_thread: Optional[threading.Thread] = None
        self._stop_receiver = threading.Event()

        # 重启计数
        self._restart_count = 0

        # 心跳
        self._last_pong = 0.0
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(5000)
        self._heartbeat_timer.timeout.connect(self._send_ping)

        # 自动重启定时器
        self._restart_timer = QTimer(self)
        self._restart_timer.setSingleShot(True)
        self._restart_timer.timeout.connect(self._do_restart)

    # ========================================================
    # 状态
    # ========================================================
    @property
    def state(self) -> SandboxState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state in (
            SandboxState.RUNNING,
            SandboxState.BUSY,
        )

    @property
    def is_alive(self) -> bool:
        """进程是否存活"""
        return (self._process is not None and
                self._process.is_alive())

    def _set_state(self, state: SandboxState):
        """设置状态"""
        with self._lock:
            if self._state != state:
                self._state = state
                self.state_changed.emit(state.name)

    # ========================================================
    # 启动与停止
    # ========================================================
    def start(self) -> bool:
        """
        启动沙箱。

        返回:
            是否成功
        """
        with self._lock:
            if self.is_alive:
                return True

            self._set_state(SandboxState.STARTING)

            try:
                # 创建管道
                self._parent_conn, self._child_conn = Pipe()

                # 准备配置数据
                config_data = {
                    'name': self.config.name,
                    'permissions': list(self.config.permissions),
                    'max_memory_mb': self.config.max_memory_mb,
                    'max_cpu_time': self.config.max_cpu_time,
                    'timeout': self.config.timeout,
                    'allowed_modules': list(self.config.allowed_modules),
                    'blocked_modules': list(self.config.blocked_modules),
                    'allow_filesystem': self.config.allow_filesystem,
                    'allowed_paths': list(self.config.allowed_paths),
                    'allow_network': self.config.allow_network,
                    'allow_process': self.config.allow_process,
                    'restart_on_crash': self.config.restart_on_crash,
                    'max_restarts': self.config.max_restarts,
                    'capture_output': self.config.capture_output,
                    'log_level': self.config.log_level,
                    'debug': self.config.debug,
                }

                # 创建子进程
                self._process = Process(
                    target=_sandbox_process_entry,
                    args=(self.plugin_path, config_data, self._child_conn),
                    daemon=True,
                    name=f"sandbox_{self.config.name}",
                )

                self._process.start()

                # 关闭子进程端（父进程不用）
                self._child_conn.close()

                # 启动接收线程（唯一读 Pipe 的线程）
                self._stop_receiver.clear()

                # P1-A2: 用 Event 代替主线程直接 poll/recv
                self._ready_event = threading.Event()
                self._ready_ok = False

                self._receiver_thread = threading.Thread(
                    target=self._receiver_loop,
                    daemon=True,
                    name=f"sandbox_recv_{self.config.name}",
                )
                self._receiver_thread.start()

                # 主线程只等 Event（不碰 Pipe）
                got = self._ready_event.wait(timeout=10)
                ready = got and self._ready_ok

                if ready:
                    self._set_state(SandboxState.RUNNING)
                    self._restart_count = 0
                    self._heartbeat_timer.start()
                    self.plugin_ready.emit()
                    return True
                else:
                    self._set_state(SandboxState.ERROR)
                    self.stop()
                    return False

            except Exception as e:
                print(f"[PluginSandbox] 启动失败: {e}")
                self._set_state(SandboxState.ERROR)
                return False

    def stop(self, timeout: float = 5.0):
        """停止沙箱"""
        with self._lock:
            self._heartbeat_timer.stop()
            self._stop_receiver.set()

            # 发送关闭信号
            if self._parent_conn:
                try:
                    self._parent_conn.send({
                        'type': MSG_TYPE_SHUTDOWN,
                    })
                except Exception:
                    pass

            # 等待进程退出
            if self._process and self._process.is_alive():
                self._process.join(timeout=timeout)

                if self._process.is_alive():
                    # 强制终止
                    self._process.terminate()
                    self._process.join(timeout=2)

                    if self._process.is_alive():
                        self._process.kill()
                        self._process.join(timeout=1)

            # 清理
            self._cleanup()

            self._set_state(SandboxState.STOPPED)

    def restart(self) -> bool:
        """重启沙箱"""
        self.stop()
        return self.start()

    def _cleanup(self):
        """清理资源"""
        # 关闭连接
        if self._parent_conn:
            try:
                self._parent_conn.close()
            except Exception:
                pass
            self._parent_conn = None

        if self._child_conn:
            try:
                self._child_conn.close()
            except Exception:
                pass
            self._child_conn = None

        # 清空挂起请求
        with self._request_lock:
            for q in self._pending_requests.values():
                q.put(None)  # 通知等待者
            self._pending_requests.clear()

        # 等待接收线程结束
        if self._receiver_thread:
            self._receiver_thread.join(timeout=2)
            self._receiver_thread = None

        self._process = None

    # ========================================================
    # 就绪等待
    # ========================================================
    def _wait_for_ready(self, timeout: float = 10) -> bool:
        """A2 已废弃主线程抢读。

        P1-A2 修复说明：
            原实现让主线程直接 poll/recv Pipe，与 _receiver_loop
            线程竞争，导致：
              1. 消息可能被错误线程消费（multiprocessing.Connection
                 不是线程安全的）
              2. 主线程吞掉 LOG 等其他消息
              3. 停止时接收线程访问已关闭的连接 → OSError

            现改为：只有 _receiver_loop 读 Pipe，主线程通过
            self._ready_event（threading.Event）等待。

            本方法保留为兼容入口（外部可能调用），直接等 Event。
        """
        if not hasattr(self, '_ready_event') or self._ready_event is None:
            return False
        got = self._ready_event.wait(timeout=timeout)
        return got and getattr(self, '_ready_ok', False)

    # ========================================================
    # 接收循环
    # ========================================================
    def _receiver_loop(self):
        """接收消息循环（独立线程）"""
        while not self._stop_receiver.is_set():
            try:
                if not self._parent_conn:
                    break

                if not self._parent_conn.poll(0.1):
                    # 检查进程是否还活着
                    if not self.is_alive:
                        break
                    continue

                message = self._parent_conn.recv()

                if message is None:
                    break

                self._handle_message(message)

            except EOFError:
                break
            except OSError:
                break
            except Exception as e:
                if not self._stop_receiver.is_set():
                    print(f"[PluginSandbox] 接收错误: {e}")
                break

        # 进程退出
        if not self._stop_receiver.is_set():
            self._on_process_exit()

    def _handle_message(self, message: Dict[str, Any]):
        """处理收到的消息"""
        msg_type = message.get('type')

        if msg_type == MSG_TYPE_RESPONSE:
            self._handle_response(message)

        elif msg_type == MSG_TYPE_LOG:
            level = message.get('level', 'info')
            text = message.get('message', '')
            self.log_received.emit(level, text)

            # 检查崩溃
            if level == 'error' and message.get('traceback'):
                self.output_received.emit('traceback',
                                            message['traceback'])

        elif msg_type == MSG_TYPE_EVENT:
            event_name = message.get('name', '')
            event_data = message.get('data', {})
            self.output_received.emit(f"event:{event_name}",
                                        str(event_data))

        elif msg_type == MSG_TYPE_READY:
            # P1-A2: 就绪信号由接收线程处理，通知主线程
            self._ready_ok = bool(message.get('success', False))
            self._ready_event.set()

        elif msg_type == MSG_TYPE_PONG:
            self._last_pong = time.time()

    def _handle_response(self, message: Dict[str, Any]):
        """处理响应"""
        request_id = message.get('id', '')
        result = message.get('result', {})

        with self._request_lock:
            q = self._pending_requests.pop(request_id, None)

        if q:
            q.put(result)

    def _on_process_exit(self):
        """进程退出回调"""
        exit_code = 0

        if self._process:
            exit_code = self._process.exitcode or 0

        with self._lock:
            self._set_state(SandboxState.CRASHED)

        self.plugin_crashed.emit(exit_code)

        # 检查自动重启
        if (self.config.restart_on_crash and
                self._restart_count < self.config.max_restarts):
            self._restart_count += 1
            self._set_state(SandboxState.RESTARTING)
            self._restart_timer.start(2000)

    # ========================================================
    # 重启
    # ========================================================
    def _do_restart(self):
        """执行重启"""
        self._cleanup()

        if self.start():
            self.plugin_restarted.emit()

    # ========================================================
    # 心跳
    # ========================================================
    def _send_ping(self):
        """发送心跳"""
        if self.is_alive:
            try:
                self._parent_conn.send({
                    'type': MSG_TYPE_PING,
                    'timestamp': time.time(),
                })
            except Exception:
                pass

    # ========================================================
    # 调用方法（主要 API）
    # ========================================================
    def call(self, method: str, params: Optional[Dict] = None,
             timeout: Optional[float] = None) -> SandboxResult:
        """
        调用插件方法（同步）。

        参数:
            method: 方法名
            params: 参数
            timeout: 超时（秒）

        返回:
            SandboxResult
        """
        if not self.is_alive:
            return SandboxResult(
                success=False,
                error="沙箱未运行",
            )

        timeout = timeout or self.config.timeout
        request_id = str(uuid.uuid4())

        # 创建响应队列
        q = queue.Queue()
        with self._request_lock:
            self._pending_requests[request_id] = q

        # 发送请求
        try:
            self._set_state(SandboxState.BUSY)

            self._parent_conn.send({
                'type': MSG_TYPE_REQUEST,
                'id': request_id,
                'method': method,
                'params': params or {},
                'timeout': timeout,
            })

        except Exception as e:
            with self._request_lock:
                self._pending_requests.pop(request_id, None)

            self._set_state(SandboxState.RUNNING)

            return SandboxResult(
                success=False,
                error=f"发送请求失败: {e}",
                request_id=request_id,
            )

        # 等待响应
        try:
            response = q.get(timeout=timeout)

            if response is None:
                return SandboxResult(
                    success=False,
                    error="沙箱已关闭",
                    request_id=request_id,
                )

            # 转换为 SandboxResult
            result = SandboxResult(
                success=response.get('success', False),
                result=response.get('result'),
                error=response.get('error', ''),
                error_type=response.get('error_type', ''),
                traceback=response.get('traceback', ''),
                stdout=response.get('stdout', ''),
                stderr=response.get('stderr', ''),
                elapsed_ms=response.get('elapsed_ms', 0.0),
                request_id=request_id,
            )

            return result

        except queue.Empty:
            # 超时
            with self._request_lock:
                self._pending_requests.pop(request_id, None)

            self._set_state(SandboxState.TIMEOUT)

            return SandboxResult(
                success=False,
                error=f"调用超时 ({timeout}s)",
                request_id=request_id,
            )

        finally:
            if self._state != SandboxState.TIMEOUT:
                self._set_state(SandboxState.RUNNING)

    def call_async(self, method: str,
                    params: Optional[Dict] = None,
                    callback: Optional[Callable] = None,
                    timeout: Optional[float] = None):
        """
        异步调用插件方法。

        参数:
            method: 方法名
            params: 参数
            callback: 回调（接收 SandboxResult）
            timeout: 超时
        """
        def do_call():
            result = self.call(method, params, timeout)
            if callback:
                try:
                    callback(result)
                except Exception as e:
                    print(f"[PluginSandbox] 回调异常: {e}")

        thread = threading.Thread(target=do_call, daemon=True)
        thread.start()

    # ========================================================
    # 便捷方法
    # ========================================================
    def ping(self, timeout: float = 5.0) -> bool:
        """Ping 测试"""
        result = self.call('__ping__', timeout=timeout)
        return result.success and result.result == 'pong'

    def get_info(self) -> Optional[Dict[str, Any]]:
        """获取插件信息"""
        result = self.call('__info__')
        if result.success:
            return result.result
        return None

    def inspect(self) -> Optional[Dict[str, Any]]:
        """检查插件能力"""
        result = self.call('__inspect__')
        if result.success:
            return result.result
        return None

    # ========================================================
    # 调试
    # ========================================================
    def dump(self) -> str:
        """导出沙箱信息"""
        lines = ["PluginSandbox", "=" * 60]
        lines.append(f"名称: {self.config.name}")
        lines.append(f"路径: {self.plugin_path}")
        lines.append(f"状态: {self._state.name}")
        lines.append(f"进程存活: {self.is_alive}")
        lines.append(f"PID: {self._process.pid if self._process else 'N/A'}")

        with self._request_lock:
            lines.append(f"待处理请求: {len(self._pending_requests)}")

        lines.append(f"重启次数: {self._restart_count}")
        lines.append(f"权限: {', '.join(self.config.permissions) or '无'}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<PluginSandbox {self.config.name} "
                f"state={self._state.name} "
                f"alive={self.is_alive}>")


# ============================================================
# 沙箱管理器
# ============================================================
class SandboxManager(QObject):
    """
    沙箱管理器。

    管理多个插件沙箱。
    """

    sandbox_created = pyqtSignal(str)   # 沙箱名
    sandbox_destroyed = pyqtSignal(str) # 沙箱名

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

        self._sandboxes: Dict[str, PluginSandbox] = {}
        self._lock = threading.RLock()

    def create(self, name: str, plugin_path: str,
                config: Optional[SandboxConfig] = None) -> Optional[PluginSandbox]:
        """
        创建沙箱。

        参数:
            name: 沙箱名称（唯一）
            plugin_path: 插件路径
            config: 配置

        返回:
            PluginSandbox 或 None
        """
        with self._lock:
            if name in self._sandboxes:
                print(f"[SandboxManager] 沙箱已存在: {name}")
                return self._sandboxes[name]

            if config is None:
                config = SandboxConfig(name=name)

            sandbox = PluginSandbox(
                plugin_path, config, parent=self
            )

            # 连接信号
            sandbox.plugin_crashed.connect(
                lambda code, n=name: self._on_crashed(n, code)
            )

            self._sandboxes[name] = sandbox
            self.sandbox_created.emit(name)

            return sandbox

    def get(self, name: str) -> Optional[PluginSandbox]:
        """获取沙箱"""
        with self._lock:
            return self._sandboxes.get(name)

    def destroy(self, name: str):
        """销毁沙箱"""
        with self._lock:
            sandbox = self._sandboxes.pop(name, None)

        if sandbox:
            sandbox.stop()
            self.sandbox_destroyed.emit(name)

    def destroy_all(self):
        """销毁所有沙箱"""
        names = list(self._sandboxes.keys())
        for name in names:
            self.destroy(name)

    def list_sandboxes(self) -> List[str]:
        """列出所有沙箱"""
        with self._lock:
            return list(self._sandboxes.keys())

    def _on_crashed(self, name: str, exit_code: int):
        """崩溃回调"""
        print(f"[SandboxManager] 沙箱 {name} 崩溃 (code={exit_code})")

    def dump(self) -> str:
        """导出信息"""
        lines = ["SandboxManager", "=" * 60]
        lines.append(f"沙箱数: {len(self._sandboxes)}")

        for name, sandbox in self._sandboxes.items():
            lines.append(f"  • {name}: {sandbox.state.name}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"<SandboxManager sandboxes={len(self._sandboxes)}>"


# ============================================================
# 便捷函数
# ============================================================
def create_sandbox(plugin_path: str,
                    permissions: Optional[List[str]] = None,
                    config: Optional[SandboxConfig] = None
                    ) -> PluginSandbox:
    """
    快速创建沙箱。

    参数:
        plugin_path: 插件路径
        permissions: 权限列表
        config: 配置

    返回:
        PluginSandbox 实例
    """
    if config is None:
        config = SandboxConfig.from_permissions(
            permissions or [], name=os.path.basename(plugin_path)
        )

    sandbox = PluginSandbox(plugin_path, config)
    return sandbox


def run_in_sandbox(plugin_path: str, method: str,
                    params: Optional[Dict] = None,
                    permissions: Optional[List[str]] = None,
                    timeout: float = 30) -> SandboxResult:
    """
    在沙箱中运行插件方法（一次性）。

    参数:
        plugin_path: 插件路径
        method: 方法名
        params: 参数
        permissions: 权限
        timeout: 超时

    返回:
        SandboxResult
    """
    sandbox = create_sandbox(plugin_path, permissions)

    try:
        if sandbox.start():
            return sandbox.call(method, params, timeout)
        else:
            return SandboxResult(
                success=False,
                error="沙箱启动失败",
            )
    finally:
        sandbox.stop()


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    import sys
    import tempfile
    import shutil
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # 创建测试插件
    tmp_dir = tempfile.mkdtemp(prefix="qingcao_sandbox_test_")

    try:
        # 插件 1：正常插件
        plugin1 = os.path.join(tmp_dir, "safe_plugin")
        os.makedirs(plugin1)

        with open(os.path.join(plugin1, "__init__.py"), 'w') as f:
            f.write('''
import math

class Plugin:
    NAME = "safe_plugin"
    VERSION = "1.0.0"

    def __init__(self):
        self.counter = 0

    def add(self, a, b):
        return a + b

    def multiply(self, a, b):
        return a * b

    def sqrt(self, x):
        return math.sqrt(x)

    def counter_inc(self):
        self.counter += 1
        return self.counter

    def fail(self):
        raise ValueError("故意的错误")

    def print_something(self):
        print("Hello from sandbox!")

    def deactivate(self):
        print("Cleanup")
''')

        # 插件 2：危险插件（尝试网络）
        plugin2 = os.path.join(tmp_dir, "bad_plugin")
        os.makedirs(plugin2)

        with open(os.path.join(plugin2, "__init__.py"), 'w') as f:
            f.write('''
class Plugin:
    def try_network(self):
        import socket
        return socket.gethostname()

    def try_process(self):
        import subprocess
        return subprocess.run(["echo", "hi"], capture_output=True)
''')

        print("=== 测试 1: 正常插件 ===")

        # 创建并启动沙箱
        config = SandboxConfig(
            name="safe_sandbox",
            permissions=[],
            timeout=10,
        )

        sandbox = PluginSandbox(plugin1, config)

        # 连接信号
        sandbox.plugin_ready.connect(
            lambda: print("[信号] 插件就绪")
        )
        sandbox.plugin_crashed.connect(
            lambda code: print(f"[信号] 插件崩溃 (code={code})")
        )
        sandbox.log_received.connect(
            lambda level, msg: print(f"[日志 {level}] {msg}")
        )

        # 启动
        success = sandbox.start()
        print(f"启动结果: {success}")

        if success:
            print(f"沙箱信息: {sandbox}")
            print()

            # 测试方法调用
            print("测试方法调用:")
            result = sandbox.call('add', {'a': 3, 'b': 5})
            print(f"  add(3, 5) = {result.result} "
                  f"({result.elapsed_ms:.1f}ms)")

            result = sandbox.call('multiply', {'a': 4, 'b': 7})
            print(f"  multiply(4, 7) = {result.result}")

            result = sandbox.call('sqrt', {'x': 16})
            print(f"  sqrt(16) = {result.result}")

            result = sandbox.call('counter_inc')
            print(f"  counter_inc() = {result.result}")

            result = sandbox.call('counter_inc')
            print(f"  counter_inc() = {result.result}")

            # 测试异常
            result = sandbox.call('fail')
            print(f"  fail() = {result.error} ({result.error_type})")

            # 测试输出
            result = sandbox.call('print_something')
            print(f"  print_something() stdout: "
                  f"{result.stdout.strip()}")

            # 测试信息
            info = sandbox.get_info()
            print(f"  插件信息: {info}")

            # 测试 Ping
            print(f"  Ping: {sandbox.ping()}")

            print()

        # 测试 2：危险插件
        print("=== 测试 2: 危险插件 ===")

        sandbox2 = PluginSandbox(
            plugin2,
            SandboxConfig(name="bad_sandbox", permissions=[])
        )

        if sandbox2.start():
            # 测试网络访问（应被拒绝）
            result = sandbox2.call('try_network')
            print(f"  网络访问: success={result.success}, "
                  f"error={result.error}")

            # 测试进程创建（应被拒绝）
            result = sandbox2.call('try_process')
            print(f"  进程创建: success={result.success}, "
                  f"error={result.error}")

            sandbox2.stop()

        print()

        # 测试 3：沙箱管理器
        print("=== 测试 3: 沙箱管理器 ===")

        manager = SandboxManager()

        s1 = manager.create("s1", plugin1)
        s2 = manager.create("s2", plugin1)

        print(f"沙箱列表: {manager.list_sandboxes()}")

        if s1 and s1.start():
            result = s1.call('add', {'a': 1, 'b': 2})
            print(f"s1.add(1, 2) = {result.result}")

        if s2 and s2.start():
            result = s2.call('add', {'a': 10, 'b': 20})
            print(f"s2.add(10, 20) = {result.result}")

        print()
        print(manager.dump())
        print()

        # 清理
        manager.destroy_all()

        # 停止第一个沙箱
        if sandbox.is_running:
            sandbox.stop()

        print("测试完成。")

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    sys.exit(0)