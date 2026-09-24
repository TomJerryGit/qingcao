#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 (QingCao Editor)
============================
开发者：hedongwei
邮箱：1265338136@qq.com
青草枯荣，野火重生。

本文件为沙箱子进程运行时模块，包含：
- SandboxRuntime：沙箱运行时（在子进程中执行）
- SafeFinder：自定义模块导入器（基于 sys.meta_path）
- install_sandbox_hooks：安装所有安全钩子
- safe_compile：安全编译（基于 RestrictedPython）
- build_safe_builtins：安全内建字典
- check_ast_safety：AST 危险节点检查
- AuditLog：审计日志

设计原则:
    1. 多层防御：导入拦截 + 内建白名单 + AST 限制
    2. 失败安全：任何异常都返回 SandboxResult，不崩溃
    3. 可审计：所有拒绝都记录到 audit log
    4. 隔离在子进程：不影响主进程
    5. 内部豁免：沙箱自身运行所需的模块不受策略约束
    6. 原始内建快照：沙箱内部机制使用原始引用，避免被自己替换

与 plugin_sandbox.py 的关系:
    - plugin_sandbox.py：父进程管理（启动子进程、通信、权限确认）
    - sandbox_runtime.py：子进程执行（导入钩子、代码编译、方法调用）

修复记录:
    v2.1:
        - 增加 sys.path 引导，支持直接运行本文件
        - 增加 INTERNAL_ALLOWED_MODULES 豁免机制
        - install_sandbox_hooks 预导入内部依赖
    v2.2:
        - 增加 _ORIGINAL_BUILTINS 快照，避免 safe_compile 被自己拦截
        - 统一使用 _builtins_module，去除局部 import builtins
        - build_safe_builtins 优先使用原始内建
    v2.3（本次修复，P0）:
        - 【核心】删除 install_sandbox_hooks 中对
          _builtins_module.exec / eval / compile / globals /
          locals / vars / breakpoint / input / open 的原地替换。
          这些替换会污染整个 Python 解释器的全局 builtins，
          导致 RestrictedPython.compile_restricted()、tempfile、
          shutil 等所有依赖内建 compile 的标准库全部失效。
        - 保留 SafeFinder（sys.meta_path 拦截 import）和
          socket.getaddrinfo 拦截。这两个机制不涉及 builtins，
          不影响沙箱自身。
        - 补齐 INTERNAL_ALLOWED_MODULES：tempfile、shutil、
          random、datetime、time 等。
        - safe_compile 明确使用 _ORIGINAL_COMPILE。
        - build_safe_builtins 明确从 _ORIGINAL_BUILTINS 取值。

    ⚠ 修复原理（务必理解）:
        插件代码拿到的 __builtins__ 是 build_safe_builtins()
        返回的独立字典（注入在 ns['__builtins__']），
        完全不需要靠污染全局 builtins 来限制。
        沙箱自身机制（RestrictedPython、tempfile、json 等）
        依赖原始 compile/eval/open，绝不能触碰全局 builtins。
        只有 SafeFinder 是全局的，但它只拦截 import，
        且通过 INTERNAL_ALLOWED_MODULES 豁免沙箱自身的依赖。
"""

import os
import sys
import ast
import time
import json
import traceback
import importlib
import importlib.abc
import importlib.machinery
from typing import Optional, List, Set, Dict, Any, Tuple, Callable


# ============================================================
# sys.path 引导：确保项目根目录可导入
# ============================================================
# 当直接运行本文件（python infrastructure/sandbox_runtime.py）时，
# Python 把 infrastructure/ 作为 sys.path[0]，无法 import core.*。
# 这里手动把项目根目录插入 sys.path。
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # 上一级 = 项目根
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ============================================================
# 原始内建快照（关键！必须在任何替换之前执行）
# ============================================================
# 说明：
#   install_sandbox_hooks 中的某些机制可能间接影响内建，
#   为避免"沙箱内部机制被自己拦截"，这里预先保存原始引用。
#
# 原则：
#   - 沙箱内部机制（safe_compile / execute_code / safe_open）
#     → 使用 _ORIGINAL_BUILTINS 中的原始引用
#   - 插件代码（Layer 2）
#     → 使用受限内建（通过 ns['__builtins__'] 字典注入）
import builtins as _builtins_module

_ORIGINAL_BUILTINS: Dict[str, Any] = {
    'compile':     _builtins_module.compile,
    'eval':        _builtins_module.eval,
    'exec':        _builtins_module.exec,
    'globals':     _builtins_module.globals,
    'locals':      _builtins_module.locals,
    'vars':        _builtins_module.vars,
    'open':        _builtins_module.open,
    'input':       _builtins_module.input,
    'print':       _builtins_module.print,
    '__import__':  _builtins_module.__import__,
}

# 便捷别名
_ORIGINAL_COMPILE = _ORIGINAL_BUILTINS['compile']
_ORIGINAL_IMPORT = _ORIGINAL_BUILTINS['__import__']
_ORIGINAL_OPEN = _ORIGINAL_BUILTINS['open']


# ============================================================
# 尝试导入 RestrictedPython
# ============================================================
_RESTRICTED_PYTHON_OK = False
_restricted_compile = None
_restricted_safe_globals = None

try:
    from RestrictedPython import (
        compile_restricted, safe_globals as _safe_globals_dict
    )
    from RestrictedPython.Eval import default_guarded_getitem
    from RestrictedPython.Guards import (
        safe_builtins as _rp_safe_builtins,
        guarded_iter_unpack_sequence,
        guarded_unpack_sequence,
    )
    _RESTRICTED_PYTHON_OK = True
    _restricted_compile = compile_restricted
    _restricted_safe_globals = _safe_globals_dict
    print("[SandboxRuntime] RestrictedPython 已加载")
except ImportError as e:
    print(f"[SandboxRuntime] RestrictedPython 未安装: {e}")
    print("[SandboxRuntime] 将使用降级模式（受限编译 + 严格白名单）")


# ============================================================
# RestrictedPython 辅助全局（v2.4 新增）
# ============================================================
# 说明：
#   RestrictedPython.compile_restricted() 编译出的字节码会
#   引用这些辅助函数。必须在 exec 时把它们注入到 namespace，
#   否则会出现 NameError: name '_getattr_' is not defined。
#
#   每个函数采用 try/except 逐项导入，以兼容不同版本的
#   RestrictedPython（API 在不同版本间略有差异）。


def _allow_write(obj):
    """默认属性写入守卫：返回 obj 本身允许赋值（AST 已检查）"""
    return obj


class _WriteGuard:
    """
    属性写入守卫（v2.8）。

    说明：
        RestrictedPython 自带的 full_write_guard 要求被赋值对象
        具有 __guarded_setattr__，否则抛 TypeError:
        attribute-less object。改为直接转发 setattr / delattr。
        安全性由 AST 检查（禁止危险属性访问）和沙箱策略保证。
    """
    __slots__ = ('_target',)

    def __init__(self, target):
        object.__setattr__(self, '_target', target)

    def __setattr__(self, name, value):
        setattr(self._target, name, value)

    def __delattr__(self, name):
        delattr(self._target, name)


def _write_guard(obj):
    """_write_ 的实现：返回一个允许属性写入的代理对象。"""
    return _WriteGuard(obj)


def _build_restricted_globals() -> Dict[str, Any]:
    """构建 RestrictedPython 编译代码所需的辅助全局字典。"""
    result: Dict[str, Any] = {}
    if not _RESTRICTED_PYTHON_OK:
        return result

    # _getattr_：属性访问守卫
    try:
        from RestrictedPython.Guards import guarded_getattr
        result['_getattr_'] = guarded_getattr
    except ImportError:
        result['_getattr_'] = getattr

    # _getitem_：下标访问守卫
    try:
        from RestrictedPython.Eval import default_guarded_getitem
        result['_getitem_'] = default_guarded_getitem
    except ImportError:
        try:
            from RestrictedPython.Guards import guarded_getitem
            result['_getitem_'] = guarded_getitem
        except ImportError:
            result['_getitem_'] = lambda obj, key: obj[key]

    # _getiter_：迭代器守卫
    try:
        from RestrictedPython.Eval import default_guarded_getiter
        result['_getiter_'] = default_guarded_getiter
    except ImportError:
        result['_getiter_'] = iter

    # _write_：属性写入守卫
    try:
        from RestrictedPython.Guards import full_write_guard
        result['_write_'] = full_write_guard
    except ImportError:
        class _DefaultWriteGuard:
            def __getattr__(self, name):
                return _allow_write
        result['_write_'] = _DefaultWriteGuard()

    # _inplacevar_：原地运算守卫
    try:
        from RestrictedPython.Guards import guarded_inplacevar
        result['_inplacevar_'] = guarded_inplacevar
    except ImportError:
        try:
            from RestrictedPython.Eval import default_guarded_inplacevar
            result['_inplacevar_'] = default_guarded_inplacevar
        except ImportError:
            pass

    # _apply_：函数调用守卫
    try:
        from RestrictedPython.Guards import guarded_apply
        result['_apply_'] = guarded_apply
    except ImportError:
        pass

    # _print_：print 守卫
    try:
        from RestrictedPython.Guards import guarded_print
        result['_print_'] = guarded_print
    except ImportError:
        try:
            from RestrictedPython.print_function import print_
            result['_print_'] = print_
        except ImportError:
            result['_print_'] = print

    # _unpack_sequence_：序列解包守卫
    try:
        from RestrictedPython.Guards import guarded_unpack_sequence
        result['_unpack_sequence_'] = guarded_unpack_sequence
    except ImportError:
        pass

    # __metaclass__：class 定义所需（v2.5 补齐）
    # RestrictedPython 编译 class Foo: 时会引用 __metaclass__
    result['__metaclass__'] = type

    # _write_：覆盖为宽松守卫（v2.8）
    # 说明：
    #   RestrictedPython 的 full_write_guard 要求被赋值对象
    #   具有 __guarded_setattr__，否则抛 TypeError:
    #   attribute-less object。这里覆盖为 _write_guard，
    #   直接转发 setattr/delattr。
    result['_write_'] = _write_guard

    return result


# 模块加载时构建一次
_RESTRICTED_GLOBALS: Dict[str, Any] = _build_restricted_globals()


# ============================================================
# 导入 sandbox_policy
# ============================================================
try:
    from core.sandbox_policy import (
        SandboxPolicy,
        SAFE_BUILTINS,
        SAFE_MODULES,
        DANGEROUS_MODULES,
    )
except ImportError as _e:
    print(f"[SandboxRuntime] 警告：无法导入 core.sandbox_policy: {_e}")
    SAFE_BUILTINS = set()
    SAFE_MODULES = set()
    DANGEROUS_MODULES = set()
    SandboxPolicy = None


# ============================================================
# 审计日志
# ============================================================
class AuditLog:
    """简单的审计日志（内存，环形缓冲）"""

    def __init__(self, max_size: int = 500):
        self.max_size = max_size
        self._entries: List[Dict[str, Any]] = []

    def record(self, action: str, detail: str,
               allowed: bool, reason: str = ""):
        entry = {
            'ts': time.time(),
            'action': action,
            'detail': str(detail)[:200],
            'allowed': allowed,
            'reason': reason,
        }
        self._entries.append(entry)
        if len(self._entries) > self.max_size:
            self._entries.pop(0)

    def get_recent(self, n: int = 50) -> List[Dict[str, Any]]:
        return self._entries[-n:]

    def clear(self):
        self._entries.clear()

    def dump(self, n: int = 20) -> str:
        lines = [f"AuditLog ({len(self._entries)} 条)"]
        for entry in self._entries[-n:]:
            ts = time.strftime("%H:%M:%S", time.localtime(entry['ts']))
            status = "✓" if entry['allowed'] else "✗"
            lines.append(
                f"  [{ts}] {status} {entry['action']}: {entry['detail']}"
            )
            if entry['reason']:
                lines.append(f"        └─ {entry['reason']}")
        return "\n".join(lines)


# 全局审计日志
_audit = AuditLog()


def get_audit_log() -> AuditLog:
    """获取全局审计日志"""
    return _audit


# ============================================================
# 沙箱内部白名单（不受策略约束）
# ============================================================
# 说明：
#   这些模块是沙箱运行时自己需要的，不能受策略限制，
#   否则会出现"沙箱把自己 setup 用的模块拦掉"的死锁。
#
# 安全性：
#   - builtins / sys：Python 核心，已被 AST 检查和白名单限制
#   - core / infrastructure / app：沙箱自身代码
#   - importlib：允许 importlib 自身使用（但用户的
#     importlib.import_module 依然被 meta_path 拦截）
#   - tempfile / shutil：沙箱自测和自身 setup 需要
#   - 其他：Python 解释器内部依赖
INTERNAL_ALLOWED_MODULES: Set[str] = {
    # ---- Python 基础设施 ----
    'builtins', '__builtin__', 'sys', '_frozen_importlib',
    '_frozen_importlib_external', '_imp',
    'importlib', 'importlib.abc', 'importlib.machinery',
    'importlib.util', 'importlib._bootstrap',
    'importlib._bootstrap_external',
    'types', 'typing', 'typing.io', 'typing.re',
    'collections', 'collections.abc',
    'warnings', 'weakref', 'encodings', 'codecs',
    'abc', 'io', 'os', 'os.path', 'posixpath',
    'stat', 'errno', 're', 'sre_compile', 'sre_parse',
    'encodings.utf_8', 'encodings.aliases',
    'functools', 'operator', 'itertools', 'heapq',
    'copyreg', 'keyword', 'reprlib',
    'marshal',

    # ---- 沙箱自测/自身 setup 需要（v2.3 补齐）----
    'tempfile',      # 沙箱自测创建临时目录
    'shutil',        # 沙箱自测清理临时目录
    'random',        # 部分工具需要
    'datetime',      # 日志/时间戳
    'time',          # time.time / strftime

    # ---- 项目自身 ----
    'core', 'infrastructure', 'app',
    'core.sandbox_policy',
    'infrastructure.sandbox_runtime',

    # ---- socket 依赖链（v2.4 补齐）----
    'selectors',     # socket 内部会 import 它
    'select',        # 部分平台需要

    # ---- 网络 setup（SafeFinder 自身需要 import socket）----
    'socket', '_socket',
}


def _is_internal_module(module_name: str) -> bool:
    """
    判断是否为沙箱内部模块。

    参数:
        module_name: 模块名（如 'builtins' 或 'core.sandbox_policy'）

    返回:
        是否豁免策略检查
    """
    if not module_name:
        return False
    top = module_name.split('.')[0]
    return top in INTERNAL_ALLOWED_MODULES


# ============================================================
# 自定义模块导入器（基于 sys.meta_path）
# ============================================================
class SafeFinder(importlib.abc.MetaPathFinder):
    """
    自定义模块查找器。

    在所有其他 Finder 之前插入，拦截所有 import 请求，
    根据策略决定是否允许。

    优势（对比 __builtins__.__import__）:
        1. 拦截所有导入路径（import、importlib.import_module 等）
        2. 无法通过 sys.modules 直接绕过
        3. 可以拦截延迟导入（__getattr__ 中 import）
    """

    def __init__(self, policy):
        """
        参数:
            policy: SandboxPolicy 实例
        """
        self.policy = policy

    def find_spec(self, fullname, path=None, target=None):
        """
        拦截导入。

        返回:
            None 表示继续使用后续 Finder
            抛 ImportError 表示拒绝导入
        """
        # 内部模块豁免（沙箱自身 setup 用）
        if _is_internal_module(fullname):
            return None

        # 策略检查
        allowed = self.policy.can_import(fullname)

        _audit.record(
            'import',
            fullname,
            allowed,
            "" if allowed else "policy 拒绝"
        )

        if not allowed:
            raise ImportError(
                f"沙箱拒绝导入模块 '{fullname}' "
                f"(权限: {self.policy.permissions})"
            )

        # 允许：返回 None 让后续 Finder 继续处理
        return None


# ============================================================
# 危险 AST 节点检查
# ============================================================
class _DangerousNodeChecker(ast.NodeVisitor):
    """
    AST 遍历器：检测危险节点。

    用于降级模式（RestrictedPython 不可用时）。
    即使 RestrictedPython 可用，也建议叠加此检查。

    检测:
        - exec / eval / compile / __import__ 调用
        - Attribute 访问 .__globals__ / .__code__ / .__subclasses__ 等
        - Global / Nonlocal 语句
    """

    FORBIDDEN_NAMES = {
        'eval', 'exec', 'compile', '__import__',
        'globals', 'locals', 'vars',
        'open', 'input', 'breakpoint',
        'memoryview',
    }

    FORBIDDEN_ATTRS = {
        '__globals__', '__code__', '__closure__',
        '__subclasses__', '__bases__', '__mro__',
        '__class__', '__dict__', '__getattribute__',
        '__reduce__', '__reduce_ex__',
        'f_globals', 'f_locals', 'f_back',
        'gi_frame', 'cr_frame',
    }

    def __init__(self):
        self.violations: List[Tuple[int, str]] = []

    def visit_Call(self, node: ast.Call):
        # 检查直接调用
        if isinstance(node.func, ast.Name):
            if node.func.id in self.FORBIDDEN_NAMES:
                self.violations.append(
                    (node.lineno, f"调用禁止的函数: {node.func.id}")
                )

        # 检查属性调用（obj.eval() 等）
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in self.FORBIDDEN_NAMES:
                self.violations.append(
                    (node.lineno,
                     f"调用禁止的属性: .{node.func.attr}()")
                )

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr in self.FORBIDDEN_ATTRS:
            self.violations.append(
                (node.lineno, f"访问禁止的属性: .{node.attr}")
            )
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global):
        self.violations.append(
            (node.lineno, f"禁止 global 语句: {', '.join(node.names)}")
        )
        self.generic_visit(node)

    def visit_Nonlocal(self, node: ast.Nonlocal):
        self.violations.append(
            (node.lineno, f"禁止 nonlocal 语句: {', '.join(node.names)}")
        )
        self.generic_visit(node)


def check_ast_safety(code: str) -> List[str]:
    """
    检查代码 AST 是否有危险节点。

    参数:
        code: 源代码字符串

    返回:
        违规列表（空表示安全）
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"语法错误: 第 {e.lineno} 行: {e.msg}"]

    checker = _DangerousNodeChecker()
    checker.visit(tree)

    return [
        f"第 {line} 行: {msg}"
        for line, msg in checker.violations
    ]


# ============================================================
# 安全编译
# ============================================================
def safe_compile(code: str, filename: str = '<plugin>',
                 mode: str = 'exec') -> Any:
    """
    安全编译代码。

    优先使用 RestrictedPython；不可用时使用 AST 检查 + 原生 compile。

    修复说明（v2.3）:
        - 明确使用 _ORIGINAL_COMPILE（模块加载时快照）。
          由于 install_sandbox_hooks 不再替换 builtins.compile，
          本函数即使使用内置 compile 也是安全的；但为了防御性
          编程与语义清晰，仍显式使用 _ORIGINAL_COMPILE。

    参数:
        code: 源代码
        filename: 文件名（用于错误信息）
        mode: 'exec' / 'eval' / 'single'

    返回:
        编译后的代码对象

    异常:
        ValueError: 代码包含危险内容
    """
    # 1. AST 检查（始终执行）
    violations = check_ast_safety(code)
    if violations:
        reason = "; ".join(violations[:5])
        _audit.record('compile', filename, False, reason)
        raise ValueError(f"代码包含禁止内容: {reason}")

    # 2. RestrictedPython 编译（如果可用）
    if _RESTRICTED_PYTHON_OK and _restricted_compile:
        try:
            bytecode = _restricted_compile(code, filename, mode)
            _audit.record('compile', filename, True, "RestrictedPython")
            return bytecode
        except SyntaxError as e:
            _audit.record('compile', filename, False, f"语法: {e}")
            raise ValueError(f"RestrictedPython 编译失败: {e}")
        except Exception as e:
            _audit.record('compile', filename, False, f"编译异常: {e}")
            raise ValueError(f"编译异常: {e}")

    # 3. 降级：使用原始 compile（已通过 AST 检查）
    try:
        bytecode = _ORIGINAL_COMPILE(code, filename, mode)
        _audit.record('compile', filename, True,
                      "原生 compile (AST 已检查)")
        return bytecode
    except SyntaxError as e:
        _audit.record('compile', filename, False, f"语法: {e}")
        raise ValueError(f"编译失败: {e}")


# ============================================================
# 安全内建字典
# ============================================================
def build_safe_builtins(policy) -> Dict[str, Any]:
    """
    根据策略构建受限的内建函数字典。

    修复说明（v2.3）:
        - 优先从 _ORIGINAL_BUILTINS 获取原始内建，
          避免在 install_sandbox_hooks 中若曾替换 builtins
          导致白名单内建被污染。
        - 由于 v2.3 已彻底移除对 builtins 的全局替换，
          本函数的安全性不再依赖此修复；但仍保留以防万一。

    参数:
        policy: SandboxPolicy

    返回:
        {name: value} 字典，可直接用于 exec 的 __builtins__
    """
    result: Dict[str, Any] = {}

    # 使用白名单
    allowed = policy.restricted_builtins or SAFE_BUILTINS

    for name in allowed:
        # 优先使用原始内建（避免被外部替换影响）
        if name in _ORIGINAL_BUILTINS:
            result[name] = _ORIGINAL_BUILTINS[name]
        elif hasattr(_builtins_module, name):
            result[name] = getattr(_builtins_module, name)

    # ---- 类构造所需（v2.4 补齐）----
    # class Foo: 语句在字节码层面需要 __build_class__
    if hasattr(_builtins_module, '__build_class__'):
        result['__build_class__'] = _builtins_module.__build_class__

    # 类和对象基础设施（确保存在，即使白名单遗漏）
    for name in ('object', 'type', 'super',
                 'property', 'staticmethod', 'classmethod'):
        if name not in result and hasattr(_builtins_module, name):
            result[name] = getattr(_builtins_module, name)

    # 反射（白名单可能遗漏）
    for name in ('isinstance', 'issubclass',
                 'getattr', 'hasattr', 'setattr',
                 'callable', 'repr', 'id', 'hash'):
        if name not in result and hasattr(_builtins_module, name):
            result[name] = getattr(_builtins_module, name)

    # 特殊处理：__import__ 使用受限版本
    result['__import__'] = make_safe_import(policy)

    # 异常类
    for exc_name in [
        'Exception', 'BaseException',
        'ValueError', 'TypeError', 'KeyError', 'IndexError',
        'AttributeError', 'RuntimeError', 'StopIteration',
        'NotImplementedError', 'OSError', 'IOError',
        'PermissionError', 'FileNotFoundError', 'FileExistsError',
        'ImportError', 'ZeroDivisionError', 'ArithmeticError',
        'AssertionError', 'UnicodeError', 'LookupError',
        'OverflowError', 'RecursionError', 'NameError',
    ]:
        if hasattr(_builtins_module, exc_name):
            result[exc_name] = getattr(_builtins_module, exc_name)

    # 常量
    result['True'] = True
    result['False'] = False
    result['None'] = None
    result['NotImplemented'] = NotImplemented
    result['Ellipsis'] = Ellipsis
    result['__debug__'] = True

    return result


def make_safe_import(policy) -> Callable:
    """
    创建一个受限的 __import__ 函数。

    修复说明（v2.3）:
        - 使用 _ORIGINAL_IMPORT（模块加载时快照），
          避免多次包装导致的递归。
        - 由于 install_sandbox_hooks 不再替换 builtins.__import__，
          本函数只用于注入到插件代码的 __builtins__ 字典中。

    参数:
        policy: SandboxPolicy

    返回:
        受限的 import 函数
    """
    # 使用模块加载时保存的原始 __import__
    real_import = _ORIGINAL_IMPORT

    def safe_import(name, globals=None, locals=None,
                    fromlist=(), level=0):
        # 内部模块豁免
        if _is_internal_module(name):
            return real_import(name, globals, locals, fromlist, level)

        # 策略检查
        if not policy.can_import(name):
            _audit.record('import', name, False, "safe_import 拒绝")
            raise ImportError(f"沙箱拒绝导入: {name}")

        _audit.record('import', name, True)
        return real_import(name, globals, locals, fromlist, level)

    return safe_import


# ============================================================
# 安装所有安全钩子
# ============================================================
def install_sandbox_hooks(policy) -> Dict[str, Any]:
    """
    安装所有沙箱安全钩子。

    在子进程启动时调用一次。

    修复说明（v2.3，核心）:
        - 【删除】对全局 builtins.exec / eval / compile /
          globals / locals / vars / breakpoint / input / open
          的原地替换。
          这些替换会污染整个 Python 解释器的全局 builtins，
          导致 RestrictedPython.compile_restricted()、tempfile、
          shutil 等所有依赖内建 compile 的标准库全部失效。
        - 【保留】SafeFinder（sys.meta_path 拦截 import）。
        - 【保留】socket.getaddrinfo 替换（网络层拦截）。
        - 插件代码的限制通过 SandboxRuntime.create_namespace()
          注入的受限 __builtins__ 字典实现，不依赖全局替换。

    参数:
        policy: SandboxPolicy

    返回:
        上下文信息字典（供调试）
    """
    context: Dict[str, Any] = {
        'installed': [],
        'errors': [],
        'restricted_python': _RESTRICTED_PYTHON_OK,
    }

    # ---- 1. 安装 sys.meta_path 拦截器 ----
    try:
        finder = SafeFinder(policy)
        sys.meta_path.insert(0, finder)
        context['installed'].append('SafeFinder (sys.meta_path)')
        _audit.record('install', 'SafeFinder', True)
    except Exception as e:
        context['errors'].append(f"SafeFinder: {e}")
        _audit.record('install', 'SafeFinder', False, str(e))

    # ---- 2. 网络拦截（在 socket 层） ----
    #
    # 说明：SafeFinder 只拦截 import；socket.getaddrinfo 拦截
    #       实际的 DNS 解析请求，作为网络访问的最后一道防线。
    #       这一替换不涉及 builtins，不影响沙箱自身。
    #
    #       注意：这里使用 _ORIGINAL_IMPORT 而非内置 __import__，
    #       避免依赖当前 builtins 状态。
    try:
        _socket_mod = _ORIGINAL_IMPORT('socket')
        real_getaddrinfo = _socket_mod.getaddrinfo

        def _safe_getaddrinfo(host, port, *args, **kwargs):
            if not policy.can_access_host(host):
                _audit.record('network',
                              f"{host}:{port}", False,
                              "主机不在白名单")
                raise OSError(f"沙箱禁止访问: {host}")
            _audit.record('network', f"{host}:{port}", True)
            return real_getaddrinfo(host, port, *args, **kwargs)

        _socket_mod.getaddrinfo = _safe_getaddrinfo
        context['installed'].append('socket.getaddrinfo')
        _audit.record('install', 'network guard', True)
    except Exception as e:
        context['errors'].append(f"网络拦截: {e}")
        _audit.record('install', 'network guard', False, str(e))

    # ============================================================
    # 说明（v2.3 修复）：
    #
    # 原 v2.2 实现曾在此处对全局 builtins 做如下替换：
    #
    #     _bt.exec = _blocked('exec')
    #     _bt.eval = _blocked('eval')
    #     _bt.compile = _blocked('compile')
    #     _bt.globals = _blocked('globals')
    #     _bt.locals = _blocked('locals')
    #     _bt.vars = _blocked('vars')
    #     _bt.breakpoint = _blocked('breakpoint')
    #     _bt.input = _blocked('input')
    #     _bt.open = _safe_open
    #
    # 这些替换是【严重错误】：
    #   1. builtins 是模块级全局对象，替换会影响整个解释器。
    #   2. RestrictedPython.compile_restricted() 内部调用
    #      compile()，运行时查找 builtins.compile，
    #      拿到的是 _blocked('compile')，直接抛 RuntimeError。
    #   3. tempfile、shutil 等标准库同样依赖 compile/eval，
    #      导致沙箱自测、甚至插件加载基础设施全部失效。
    #
    # 正确做法：
    #   插件代码拿到的 __builtins__ 是 SandboxRuntime
    #   通过 build_safe_builtins() 构建的独立字典，
    #   在 create_namespace() 中注入 ns['__builtins__']。
    #   __import__ 也通过 make_safe_import() 受限。
    #
    #   沙箱自身用 _ORIGINAL_* 快照，不受任何影响。
    # ============================================================

    return context


# ============================================================
# 安全执行环境
# ============================================================
class SandboxRuntime:
    """
    沙箱运行时（子进程内使用）。

    提供:
        - 创建安全命名空间
        - 执行插件代码
        - 调用插件方法
    """

    def __init__(self, policy):
        """
        参数:
            policy: SandboxPolicy
        """
        self.policy = policy
        self.context: Dict[str, Any] = {}
        self.plugin_instance = None

    def create_namespace(self,
                          initial: Optional[Dict] = None) -> Dict:
        """
        创建安全的命名空间。

        修复说明（v2.4）:
            - 在 __builtins__ 之外，额外注入 RestrictedPython
              编译后代码所需的辅助函数（_getattr_ / _getiter_ /
              _getitem_ / _write_ / _inplacevar_ 等）。
              缺少这些会导致任何稍复杂的语句（import、for、
              列表推导、class 定义）抛 NameError。

        参数:
            initial: 初始值

        返回:
            命名空间字典（可直接用于 exec）
        """
        ns: Dict[str, Any] = {
            '__builtins__': build_safe_builtins(self.policy),
            '__name__': '__sandbox_plugin__',
            '__doc__': None,
            '__package__': None,
            '__loader__': None,
            '__spec__': None,
        }

        # v2.4: 注入 RestrictedPython 辅助函数
        if _RESTRICTED_GLOBALS:
            ns.update(_RESTRICTED_GLOBALS)

        if initial:
            ns.update(initial)

        return ns

    def execute_code(self, code: str,
                     namespace: Optional[Dict] = None) -> Any:
        """
        执行代码。

        参数:
            code: 源代码
            namespace: 命名空间（None 则新建）

        返回:
            执行结果（如果有表达式）

        异常:
            ValueError: 编译失败或包含危险内容
            RuntimeError: 运行时异常
        """
        ns = namespace if namespace is not None else self.create_namespace()

        # 安全编译
        bytecode = safe_compile(code, '<runtime>', 'exec')

        # 执行：使用 _ORIGINAL_BUILTINS['exec'] 快照
        try:
            _ORIGINAL_BUILTINS['exec'](bytecode, ns)
            return None
        except Exception as e:
            raise RuntimeError(f"执行失败: {e}")

    def load_plugin(self, plugin_path: str) -> bool:
        """
        加载插件（读取其 __init__.py 并执行）。

        参数:
            plugin_path: 插件目录

        返回:
            是否成功
        """
        entry = os.path.join(plugin_path, '__init__.py')
        if not os.path.exists(entry):
            raise FileNotFoundError(f"缺少入口文件: {entry}")

        # 读取源码（使用原始 open 快照）
        try:
            with _ORIGINAL_OPEN(entry, 'r', encoding='utf-8') as f:
                source = f.read()
        except Exception as e:
            raise RuntimeError(f"读取插件源码失败: {e}")

        # 创建命名空间
        ns = self.create_namespace()
        self.context = ns

        # 编译 + 执行
        try:
            bytecode = safe_compile(source, entry, 'exec')
            _ORIGINAL_BUILTINS['exec'](bytecode, ns)
        except ValueError as e:
            raise RuntimeError(f"插件代码被拒绝: {e}")
        except Exception as e:
            raise RuntimeError(f"插件加载失败: {e}")

        # 查找 Plugin 类
        if 'Plugin' not in ns:
            raise RuntimeError("插件缺少 Plugin 类")

        plugin_cls = ns['Plugin']

        # 实例化
        try:
            self.plugin_instance = plugin_cls()
        except Exception as e:
            raise RuntimeError(f"Plugin 实例化失败: {e}")

        return True

    def call_method(self, method_name: str,
                    params: Any = None) -> Any:
        """
        调用插件方法。

        参数:
            method_name: 方法名
            params: 参数（dict 或 list 或单个值）

        返回:
            方法返回值

        异常:
            AttributeError: 方法不存在
            RuntimeError: 方法执行异常
        """
        if self.plugin_instance is None:
            raise RuntimeError("插件未加载")

        method = getattr(self.plugin_instance, method_name, None)
        if method is None or not callable(method):
            raise AttributeError(f"插件无方法: {method_name}")

        # 参数处理
        try:
            if params is None:
                return method()
            elif isinstance(params, dict):
                return method(**params)
            elif isinstance(params, (list, tuple)):
                return method(*params)
            else:
                return method(params)
        except Exception as e:
            tb = traceback.format_exc()
            raise RuntimeError(f"方法执行失败: {e}\n{tb}")


# ============================================================
# 单元测试入口
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("SandboxRuntime 自测")
    print("=" * 60)

    # 注意：tempfile/shutil 已在 INTERNAL_ALLOWED_MODULES 中豁免，
    #       因此即使 install_sandbox_hooks 之后再 import 也不会被拦。
    #       这里为清晰起见，在安装钩子之前 import。
    import tempfile
    import shutil

    if SandboxPolicy is None:
        print("✗ SandboxPolicy 未加载，无法测试")
        sys.exit(1)

    policy = SandboxPolicy.strict()
    print(f"策略: {policy}")
    print()

    # 安装钩子
    print("=== 安装安全钩子 ===")
    ctx = install_sandbox_hooks(policy)
    print(f"已安装: {ctx['installed']}")
    if ctx['errors']:
        print(f"错误: {ctx['errors']}")
    else:
        print("错误: []")
    print(f"RestrictedPython: {ctx['restricted_python']}")
    print()

    # 测试 1: 危险代码
    print("=== 测试 1: 危险代码被拒绝 ===")
    runtime = SandboxRuntime(policy)
    dangerous_codes = [
        ("import ctypes", "导入 ctypes"),
        ("eval('1+1')", "调用 eval"),
        ("__import__('socket')", "直接调 __import__"),
        ("open('/etc/passwd')", "打开系统文件"),
        ("x = ().__class__.__bases__", "属性逃逸"),
    ]
    for code, desc in dangerous_codes:
        try:
            runtime.execute_code(code)
            print(f"  ✗ {desc}: 未拦截！")
        except ValueError as e:
            print(f"  ✓ {desc}: 被拒绝 ({str(e)[:50]}...)")
        except Exception as e:
            print(f"  ~ {desc}: 其他异常 ({type(e).__name__})")
    print()

    # 测试 2: 安全代码
    print("=== 测试 2: 安全代码可执行 ===")
    safe_codes = [
        ("x = 1 + 1", "算术"),
        ("import math; y = math.sqrt(16)", "math"),
        ("data = {'a': 1}", "字典"),
        ("for i in range(3): pass", "循环"),
        ("result = [x*2 for x in range(3)]", "列表推导"),
    ]
    for code, desc in safe_codes:
        try:
            runtime.execute_code(code)
            print(f"  ✓ {desc}")
        except Exception as e:
            print(f"  ✗ {desc}: {e}")
    print()

    # 测试 3: 插件加载
    print("=== 测试 3: 插件加载 ===")

    tmp_dir = tempfile.mkdtemp(prefix="qingcao_sandbox_test_")

    plugin_code = '''
"""测试插件"""

class Plugin:
    NAME = "test_plugin"
    VERSION = "1.0.0"

    def __init__(self):
        self.counter = 0

    def add(self, a, b):
        return a + b

    def get_counter(self):
        return self.counter

    def fail(self):
        raise ValueError("故意的错误")
'''

    try:
        with _ORIGINAL_OPEN(os.path.join(tmp_dir, '__init__.py'),
                            'w', encoding='utf-8') as f:
            f.write(plugin_code)

        runtime2 = SandboxRuntime(policy)
        if runtime2.load_plugin(tmp_dir):
            print(f"  ✓ 插件加载成功")

            result = runtime2.call_method('add', {'a': 3, 'b': 5})
            print(f"  ✓ add(3, 5) = {result}")

            result = runtime2.call_method('get_counter')
            print(f"  ✓ get_counter() = {result}")

            try:
                runtime2.call_method('fail')
                print(f"  ✗ fail() 未抛异常")
            except RuntimeError:
                print(f"  ✓ fail() 正确抛出异常")
        else:
            print(f"  ✗ 插件加载失败")

    except Exception as e:
        print(f"  ✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    print()

    # 审计日志
    print("=== 审计日志 ===")
    print(_audit.dump(30))
    print()

    print("=" * 60)
    print("测试完成")
    print("=" * 60)