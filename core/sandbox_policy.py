#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯草，野火重生。

本文件为沙箱安全策略配置模块，包含：
- SandboxPolicy：沙箱安全策略（白名单/黑名单/资源限制）
- 权限到资源限制的映射
- 内建函数白名单
- 危险模块黑名单
- 常用安全模块白名单
- 策略预设（strict / standard / permissive）

设计原则:
    1. 默认拒绝，显式允许（白名单机制）
    2. 权限声明驱动策略（permissions → policy）
    3. 策略不可被插件修改
    4. 策略可序列化（用于日志/审计）

用法:
    from core.sandbox_policy import SandboxPolicy

    # 方式 1：从权限推导
    policy = SandboxPolicy.from_permissions(['filesystem', 'network'])

    # 方式 2：使用预设
    policy = SandboxPolicy.strict()
    policy = SandboxPolicy.standard()

    # 方式 3：手动配置
    policy = SandboxPolicy(
        allowed_modules={'math', 'json'},
        blocked_modules={'ctypes', 'socket'},
        max_memory_mb=256,
        max_cpu_time=30,
    )
"""

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set


# ============================================================
# 常量：权限定义
# ============================================================
PERMISSION_FILESYSTEM = "filesystem"
PERMISSION_NETWORK = "network"
PERMISSION_PROCESS = "process"
PERMISSION_CLIPBOARD = "clipboard"
PERMISSION_DIALOG = "dialog"
PERMISSION_EDITOR_WRITE = "editor_write"
PERMISSION_EDITOR_READ = "editor_read"
PERMISSION_TERMINAL = "terminal"
PERMISSION_LSP = "lsp"
PERMISSION_DEBUGGER = "debugger"
PERMISSION_SETTINGS = "settings"
PERMISSION_THEMES = "themes"
PERMISSION_PLUGINS = "plugins"

ALL_PERMISSIONS = {
    PERMISSION_FILESYSTEM,
    PERMISSION_NETWORK,
    PERMISSION_PROCESS,
    PERMISSION_CLIPBOARD,
    PERMISSION_DIALOG,
    PERMISSION_EDITOR_WRITE,
    PERMISSION_EDITOR_READ,
    PERMISSION_TERMINAL,
    PERMISSION_LSP,
    PERMISSION_DEBUGGER,
    PERMISSION_SETTINGS,
    PERMISSION_THEMES,
    PERMISSION_PLUGINS,
}


# ============================================================
# 常量：内建函数白名单
# ============================================================
# 只允许这些内建函数（默认拒绝）
SAFE_BUILTINS: Set[str] = {
    # 类型转换
    'bool', 'int', 'float', 'str', 'bytes', 'bytearray',
    'list', 'tuple', 'dict', 'set', 'frozenset',
    'complex', 'memoryview', 'object',

    # 数学
    'abs', 'divmod', 'max', 'min', 'pow', 'round', 'sum',

    # 序列操作
    'all', 'any', 'enumerate', 'filter', 'iter', 'len',
    'map', 'next', 'range', 'reversed', 'slice', 'sorted', 'zip',

    # 类型检查
    'callable', 'isinstance', 'issubclass', 'type', 'repr',

    # 属性操作（受限）
    'getattr', 'hasattr', 'setattr', 'delattr', 'dir', 'vars',

    # 编码
    'ascii', 'bin', 'chr', 'hex', 'oct', 'ord',

    # 格式化（受限）
    'format',

    # 其他
    'hash', 'id', 'hash',
    'print',  # 允许 print（输出被捕获）
    'id',
    'object',
    'super',
    'property',
    'staticmethod',
    'classmethod',

    # 异常
    'Exception', 'BaseException',
    'ValueError', 'TypeError', 'KeyError', 'IndexError',
    'AttributeError', 'RuntimeError', 'StopIteration',
    'ZeroDivisionError', 'ArithmeticError', 'AssertionError',
    'NotImplementedError', 'NameError', 'ImportError',
    'OSError', 'IOError', 'FileNotFoundError',
    'PermissionError', 'FileExistsError',
    'LookupError', 'OverflowError', 'RecursionError',
    'UnicodeError', 'UnicodeDecodeError', 'UnicodeEncodeError',
    'Warning', 'UserWarning', 'DeprecationWarning',

    # 常量
    'True', 'False', 'None',
    'NotImplemented', 'Ellipsis',
    '__debug__',
    '__name__', '__doc__', '__package__', '__loader__',
    '__spec__', '__file__', '__builtins__',
}


# ============================================================
# 常量：危险模块黑名单
# ============================================================
# 这些模块被明确禁止导入（即使有权限也不允许）
#
# P3-3: 移除由权限门控的冗余模块
#   - 原实现把 socket / ssl / http / urllib / requests /
#     aiohttp / httpx / websocket / ftplib / smtplib /
#     telnetlib / xmlrpc 等"网络模块"放在这里。
#     但 can_import() 里这些模块由 allow_network 权限控制，
#     且权限分支检查在 DANGEROUS_MODULES 之前，导致
#     这里的条目冗余。
#   - 同理 shutil / glob / tempfile / os.path 由 filesystem
#     权限控制；subprocess / multiprocessing 由 process 权限
#     控制。它们都不应该出现在这里。
#   - 保留的只有"绝对禁止"：沙箱逃逸 / 反序列化漏洞 /
#     动态执行 / 平台内部等，无论什么权限都不允许。
DANGEROUS_MODULES: Set[str] = {
    # ---- 沙箱逃逸 ----
    'ctypes', 'cffi', '_ctypes',
    'gc',           # 可遍历对象图
    'atexit',       # 解释器退出时执行任意代码
    'sys',          # sys.modules 可访问被限制的模块

    # ---- 反序列化漏洞 ----
    'pickle', 'cPickle', 'dill',
    'marshal', 'shelve', 'dbm',

    # ---- 动态导入/执行 ----
    'importlib', 'imp',
    'code', 'codeop',

    # ---- 平台内部 ----
    'nt', 'posix', 'msvcrt', 'winreg', '_winapi',

    # ---- 调试/剖析（可读取栈帧）----
    'faulthandler', 'pdb', 'cProfile',

    # ---- 线程/信号（无权限门控）----
    'threading', 'concurrent',
    'pty', 'signal',

    # 说明:
    #   socket / ssl / http / urllib / requests / aiohttp /
    #   httpx / websocket / ftplib / smtplib / telnetlib /
    #   xmlrpc / paramiko → 由 network 权限控制
    #   shutil / glob / tempfile / os.path → 由 filesystem 权限
    #   subprocess / multiprocessing → 由 process 权限
    #   这些模块不在这里，避免与权限分支语义冲突。
}


# ============================================================
# 常量：标准安全模块白名单
# ============================================================
# 这些模块总是允许导入（不依赖权限）
SAFE_MODULES: Set[str] = {
    # 数学
    'math', 'cmath', 'statistics', 'random', 'secrets',
    'decimal', 'fractions', 'numbers',

    # 集合
    'collections', 'itertools', 'functools', 'operator',
    'heapq', 'bisect', 'array',

    # 字符串
    'string', 're', 'textwrap', 'unicodedata', 'difflib',
    'fnmatch',

    # 数据格式
    'json', 'csv', 'base64', 'binascii', 'struct',

    # 时间
    'datetime', 'time', 'calendar', 'zoneinfo',

    # 类型
    'types', 'typing', 'dataclasses', 'enum',
    'abc', 'contextlib', 'copy', 'pprint',
    'weakref',

    # 计算
    'hashlib', 'hmac', 'uuid',

    # 异常
    'traceback',  # 谨慎，但不构成威胁
    'logging',

    # 迭代器/生成器
    'asyncio',  # 用于插件自身异步（不涉及网络）
}


# ============================================================
# 策略数据类
# ============================================================
@dataclass
class SandboxPolicy:
    """
    沙箱安全策略。

    描述一个插件沙箱的所有安全规则。策略一旦创建就不可变
    （修改请创建新实例）。

    字段:
        permissions: 插件声明的权限列表
        allowed_modules: 允许导入的模块白名单（除 SAFE_MODULES 外额外允许）
        blocked_modules: 额外禁止的模块（黑名单）
        allowed_paths: 文件系统白名单路径
        allow_filesystem: 是否允许文件系统访问
        allow_network: 是否允许网络访问
        allow_process: 是否允许子进程
        max_memory_mb: 最大内存占用（MB，0 表示不限制）
        max_cpu_time: 最大 CPU 时间（秒，0 表示不限制）
        max_wall_time: 最大墙钟时间（秒）
        timeout: 单次请求超时（秒）
        restricted_builtins: 内建函数白名单
    """

    # 权限
    permissions: List[str] = field(default_factory=list)

    # 模块访问
    allowed_modules: Set[str] = field(default_factory=set)
    blocked_modules: Set[str] = field(default_factory=set)

    # 文件系统
    allow_filesystem: bool = False
    allowed_paths: List[str] = field(default_factory=list)

    # 网络
    allow_network: bool = False
    allowed_hosts: List[str] = field(default_factory=list)

    # 进程
    allow_process: bool = False

    # 资源限制
    max_memory_mb: int = 512
    max_cpu_time: float = 60.0
    max_wall_time: float = 120.0
    timeout: float = 30.0

    # 内建白名单（可覆盖）
    restricted_builtins: Set[str] = field(
        default_factory=lambda: set(SAFE_BUILTINS)
    )

    # --------------------------------------------------------
    # 工厂方法
    # --------------------------------------------------------
    @classmethod
    def strict(cls) -> 'SandboxPolicy':
        """最严格策略：无权限，资源限制最紧"""
        return cls(
            permissions=[],
            allow_filesystem=False,
            allow_network=False,
            allow_process=False,
            max_memory_mb=128,
            max_cpu_time=15.0,
            max_wall_time=30.0,
            timeout=10.0,
        )

    @classmethod
    def standard(cls) -> 'SandboxPolicy':
        """标准策略：适合大多数插件"""
        return cls(
            permissions=[],
            allow_filesystem=False,
            allow_network=False,
            allow_process=False,
            max_memory_mb=512,
            max_cpu_time=60.0,
            max_wall_time=120.0,
            timeout=30.0,
        )

    @classmethod
    def permissive(cls) -> 'SandboxPolicy':
        """宽松策略：仅用于已信任的插件"""
        return cls(
            permissions=list(ALL_PERMISSIONS),
            allow_filesystem=True,
            allow_network=True,
            allow_process=True,
            max_memory_mb=2048,
            max_cpu_time=300.0,
            max_wall_time=600.0,
            timeout=60.0,
        )

    @classmethod
    def from_permissions(cls, permissions: List[str],
                          **overrides) -> 'SandboxPolicy':
        """
        根据权限声明创建策略。

        参数:
            permissions: 权限列表（如 ['filesystem', 'network']）
            **overrides: 覆盖默认配置

        返回:
            SandboxPolicy
        """
        perms = list(permissions or [])

        policy = cls(
            permissions=perms,
            allow_filesystem=PERMISSION_FILESYSTEM in perms,
            allow_network=PERMISSION_NETWORK in perms,
            allow_process=PERMISSION_PROCESS in perms,
        )

        # 应用 overrides
        for key, value in overrides.items():
            if hasattr(policy, key):
                setattr(policy, key, value)

        return policy

    # --------------------------------------------------------
    # 校验方法
    # --------------------------------------------------------
    def can_import(self, module_name: str) -> bool:
        """
        判断是否允许导入指定模块。

        参数:
            module_name: 模块名（顶层，如 'socket'）

        返回:
            是否允许
        """
        top = module_name.split('.')[0]

        # 1. 用户显式禁止
        if module_name in self.blocked_modules or top in self.blocked_modules:
            return False

        # 2. 用户显式允许
        if module_name in self.allowed_modules or top in self.allowed_modules:
            return True

        # 3. 通用安全模块
        if top in SAFE_MODULES:
            return True

        # 4. 网络模块需要 network 权限
        if top in ('socket', 'ssl', 'http', 'urllib', 'requests',
                   'aiohttp', 'httpx', 'websocket', 'ftplib',
                   'smtplib', 'telnetlib', 'xmlrpc'):
            return self.allow_network

        # 5. 文件模块需要 filesystem 权限
        if top in ('shutil', 'glob', 'tempfile', 'pathlib'):
            return self.allow_filesystem

        # 6. 进程模块需要 process 权限
        if top in ('subprocess', 'multiprocessing'):
            return self.allow_process

        # 7. 危险模块一律禁止
        if top in DANGEROUS_MODULES or module_name in DANGEROUS_MODULES:
            return False

        # 8. 默认拒绝
        return False

    def can_access_path(self, path: str) -> bool:
        """
        判断是否允许访问指定路径。

        参数:
            path: 文件/目录路径

        返回:
            是否允许
        """
        if not self.allow_filesystem:
            return False

        if not self.allowed_paths:
            return False  # 未配置白名单 → 拒绝

        try:
            # 规范化路径（防止符号链接绕过）
            real = os.path.realpath(os.path.abspath(path))

            for allowed in self.allowed_paths:
                allowed_real = os.path.realpath(os.path.abspath(allowed))
                # 使用 os.path.commonpath 严格判断
                try:
                    if os.path.commonpath([real, allowed_real]) == allowed_real:
                        return True
                except ValueError:
                    # 不同驱动器（Windows）→ 不匹配
                    continue
        except Exception:
            pass

        return False

    def can_access_host(self, host: str) -> bool:
        """
        判断是否允许访问指定主机。

        参数:
            host: 主机名或 IP

        返回:
            是否允许
        """
        if not self.allow_network:
            return False

        if not self.allowed_hosts:
            return True  # 未配置白名单 → 允许所有（只要网络权限）

        return host in self.allowed_hosts

    # --------------------------------------------------------
    # 序列化
    # --------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            'permissions': list(self.permissions),
            'allowed_modules': sorted(self.allowed_modules),
            'blocked_modules': sorted(self.blocked_modules),
            'allow_filesystem': self.allow_filesystem,
            'allowed_paths': list(self.allowed_paths),
            'allow_network': self.allow_network,
            'allowed_hosts': list(self.allowed_hosts),
            'allow_process': self.allow_process,
            'max_memory_mb': self.max_memory_mb,
            'max_cpu_time': self.max_cpu_time,
            'max_wall_time': self.max_wall_time,
            'timeout': self.timeout,
        }

    def to_json(self, indent: int = None) -> str:
        """序列化为 JSON"""
        return json.dumps(self.to_dict(), indent=indent,
                          ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'SandboxPolicy':
        """从字典反序列化"""
        policy = cls()
        for key, value in d.items():
            if not hasattr(policy, key):
                continue
            if key in ('allowed_modules', 'blocked_modules',
                       'restricted_builtins'):
                setattr(policy, key, set(value))
            else:
                setattr(policy, key, value)
        return policy

    # --------------------------------------------------------
    # 调试
    # --------------------------------------------------------
    def dump(self) -> str:
        """导出策略摘要"""
        lines = ["SandboxPolicy", "=" * 60]
        lines.append(f"权限: {', '.join(self.permissions) or '无'}")
        lines.append(f"文件系统: {'允许' if self.allow_filesystem else '拒绝'}")
        lines.append(f"  - 白名单: {self.allowed_paths or '未配置'}")
        lines.append(f"网络: {'允许' if self.allow_network else '拒绝'}")
        lines.append(f"  - 主机白名单: {self.allowed_hosts or '全部'}")
        lines.append(f"子进程: {'允许' if self.allow_process else '拒绝'}")
        lines.append(f"内存限制: {self.max_memory_mb} MB")
        lines.append(f"CPU 时间: {self.max_cpu_time} 秒")
        lines.append(f"墙钟时间: {self.max_wall_time} 秒")
        lines.append(f"请求超时: {self.timeout} 秒")
        lines.append(f"内建白名单: {len(self.restricted_builtins)} 个")
        lines.append(f"额外允许模块: {sorted(self.allowed_modules) or '无'}")
        lines.append(f"额外禁止模块: {sorted(self.blocked_modules) or '无'}")
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (f"<SandboxPolicy perms={len(self.permissions)} "
                f"mem={self.max_memory_mb}MB cpu={self.max_cpu_time}s>")


# ============================================================
# 辅助函数
# ============================================================
def is_module_allowed(module_name: str,
                       policy: SandboxPolicy) -> bool:
    """便捷函数：判断模块是否允许"""
    return policy.can_import(module_name)


def build_strict_policy(plugin_name: str = "") -> SandboxPolicy:
    """构建严格策略"""
    policy = SandboxPolicy.strict()
    if plugin_name:
        policy.blocked_modules.add(plugin_name)
    return policy


# ============================================================
# 模块测试
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("SandboxPolicy 测试")
    print("=" * 60)
    print()

    # 1. 严格策略
    print("=== 严格策略 ===")
    strict = SandboxPolicy.strict()
    print(strict.dump())
    print()
    print(f"导入 math: {strict.can_import('math')}")
    print(f"导入 socket: {strict.can_import('socket')}")
    print(f"导入 ctypes: {strict.can_import('ctypes')}")
    print()

    # 2. 有权限的策略
    print("=== 有 network + filesystem 权限 ===")
    policy = SandboxPolicy.from_permissions(
        ['network', 'filesystem'],
        allowed_paths=['/tmp/plugin_data'],
    )
    print(policy.dump())
    print()
    print(f"导入 math: {policy.can_import('math')}")
    print(f"导入 socket: {policy.can_import('socket')}")
    print(f"导入 ctypes: {policy.can_import('ctypes')}")
    print()
    print(f"访问 /tmp/plugin_data/file.txt: "
          f"{policy.can_access_path('/tmp/plugin_data/file.txt')}")
    print(f"访问 /tmp/other/file.txt: "
          f"{policy.can_access_path('/tmp/other/file.txt')}")
    print(f"访问 /etc/passwd: {policy.can_access_path('/etc/passwd')}")
    print()

    # 3. 序列化
    print("=== 序列化 ===")
    json_str = policy.to_json()
    print(f"JSON 长度: {len(json_str)} 字符")
    restored = SandboxPolicy.from_dict(json.loads(json_str))
    print(f"恢复: {restored}")
    print()

    print("测试完成。")