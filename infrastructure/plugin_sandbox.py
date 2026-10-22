# -*- coding: utf-8 -*-
"""插件安全沙箱（P2 第一阶段：静态能力审计 + 权限声明校验）

为什么不直接做"进程级沙箱"：
* 插件 API 是进程内 QObject/信号模型，迁移到子进程需要整套 RPC 代理，
  工作量大且破坏现有兼容性；
* 真正有威胁的是**插件声明了低权限却偷偷联网/起进程/删文件**，
  这类问题可以用 AST 静态审计提前发现（商店上架/CI 准入控制）。

本模块提供：
* `Finding`：一条审计发现（规则代码/严重度/行号/所需权限）；
* `audit_source(source, filename)`：AST 扫描危险 import 与调用；
* `audit_plugin(plugin_dir)`：读取 manifest 权限，比对审计结果；
* 权限映射：network / process / filesystem / danger（禁入清单）。

用法（CI/上架前）：
    python -m tools.audit_plugins                 # 审计全部内置插件
    python -m tools.audit_plugins path/to/plugin  # 审计指定插件目录
"""
import ast
import json
import os
from dataclasses import dataclass, field
from typing import List


# 危险模块 → 所需权限
MODULE_PERMISSIONS = {
    "socket": "network",
    "ssl": "network",
    "http": "network",
    "urllib": "network",
    "requests": "network",
    "ftplib": "network",
    "smtplib": "network",
    "telnetlib": "network",
    "subprocess": "process",
    "multiprocessing": "process",
    "ctypes": "process",
    "pty": "process",
}

# 危险函数（模块名, 函数名）→ 所需权限
CALL_PERMISSIONS = {
    ("os", "system"): "process",
    ("os", "popen"): "process",
    ("os", "execv"): "process",
    ("os", "execl"): "process",
    ("os", "spawnv"): "process",
    ("os", "spawnl"): "process",
    ("os", "remove"): "filesystem",
    ("os", "unlink"): "filesystem",
    ("os", "rmdir"): "filesystem",
    ("os", "removedirs"): "filesystem",
    ("shutil", "rmtree"): "filesystem",
    ("os", "rename"): "filesystem",
}

# 内建危险函数名 → danger（无法通过权限声明合法化，需人工评审）
DANGER_BUILTINS = {"eval", "exec", "compile", "__import__"}

# 文件写入模式
_WRITE_MODES = set("wax+")


@dataclass
class Finding:
    code: str
    severity: str          # info / warning / high
    message: str
    line: int = 0
    permission: str = ""   # network / process / filesystem / danger

    def to_dict(self):
        return {
            "code": self.code, "severity": self.severity,
            "message": self.message, "line": self.line,
            "permission": self.permission,
        }


@dataclass
class AuditResult:
    plugin_dir: str = ""
    findings: List[Finding] = field(default_factory=list)
    declared_permissions: List[str] = field(default_factory=list)
    missing_permissions: List[str] = field(default_factory=list)
    verdict: str = "pass"   # pass / warn / review / reject

    @property
    def high(self) -> List[Finding]:
        return [f for f in self.findings if f.severity == "high"]

    def to_dict(self):
        return {
            "plugin_dir": self.plugin_dir,
            "findings": [f.to_dict() for f in self.findings],
            "declared_permissions": self.declared_permissions,
            "missing_permissions": self.missing_permissions,
            "verdict": self.verdict,
        }


def _iter_py_files(plugin_dir: str):
    for root, _dirs, files in os.walk(plugin_dir):
        if os.path.basename(root).startswith("."):
            continue
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(root, name)


def audit_source(source: str, filename: str = "<plugin>") -> List[Finding]:
    """AST 扫描源码中的危险 import / 调用 / eval 等"""
    findings = []
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        return [Finding("SBX000", "high", "语法错误无法审计: %s" % e,
                        getattr(e, "lineno", 0), "danger")]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                perm = MODULE_PERMISSIONS.get(top)
                if perm:
                    findings.append(Finding(
                        "SBX101", "warning",
                        "导入可能越权模块: %s（需要 %s 权限）"
                        % (alias.name, perm),
                        node.lineno, perm))
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            perm = MODULE_PERMISSIONS.get(top)
            if perm:
                findings.append(Finding(
                    "SBX101", "warning",
                    "导入可能越权模块: %s（需要 %s 权限）"
                    % (node.module, perm), node.lineno, perm))
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and isinstance(
                    fn.value, ast.Name):
                key = (fn.value.id, fn.attr)
                perm = CALL_PERMISSIONS.get(key)
                if perm:
                    findings.append(Finding(
                        "SBX102", "high",
                        "调用危险函数 %s.%s（需要 %s 权限）"
                        % (key[0], key[1], perm),
                        node.lineno, perm))
                if (key[0] == "open" or key == ("builtins", "open")):
                    pass
            elif isinstance(fn, ast.Name):
                if fn.id in DANGER_BUILTINS:
                    findings.append(Finding(
                        "SBX103", "high",
                        "使用 %s() 动态执行代码" % fn.id,
                        node.lineno, "danger"))
                if fn.id == "open":
                    modes = [a for a in node.args if isinstance(a, ast.Constant)
                             and isinstance(a.value, str)]
                    for kw in node.keywords:
                        if kw.arg == "mode" and isinstance(
                                kw.value, ast.Constant):
                            modes.append(kw.value)
                    write = False
                    for m in modes:
                        val = getattr(m, "value", "")
                        if isinstance(val, str) and _WRITE_MODES & set(val):
                            write = True
                    if write:
                        findings.append(Finding(
                            "SBX104", "warning",
                            "以写模式打开文件（需要 filesystem 权限）",
                            node.lineno, "filesystem"))
    return findings


def audit_plugin(plugin_dir: str) -> AuditResult:
    """审计单个插件目录：扫描源码 + 校验 manifest 权限声明"""
    result = AuditResult(plugin_dir=os.path.abspath(plugin_dir))
    manifest_path = os.path.join(plugin_dir, "plugin.json")
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        result.declared_permissions = [
            str(p) for p in (manifest.get("permissions") or [])]
    except (OSError, ValueError) as e:
        result.findings.append(Finding(
            "SBX001", "high", "manifest 无法读取: %s" % e, 0, "danger"))

    for path in _iter_py_files(plugin_dir):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                src = f.read()
        except OSError:
            continue
        findings = audit_source(src, filename=path)
        rel = os.path.relpath(path, plugin_dir)
        for fd in findings:
            fd.message = "%s: %s" % (rel, fd.message)
        result.findings.extend(findings)

    needed = {f.permission for f in result.findings
              if f.permission and f.permission != "danger"}
    declared = set(result.declared_permissions)
    result.missing_permissions = sorted(needed - declared)

    if any(f.permission == "danger" for f in result.findings):
        # eval/exec/compile 等无法通过权限声明合法化，需人工评审
        # （例如 python_debugger 就是合法用途），因此不自动 reject。
        result.verdict = "review"
    elif result.missing_permissions:
        result.verdict = "review"
    elif result.findings:
        result.verdict = "warn"
    return result


def audit_plugins_root(plugins_dir: str) -> List[AuditResult]:
    """审计插件根目录下所有子目录插件"""
    results = []
    if not os.path.isdir(plugins_dir):
        return results
    for name in sorted(os.listdir(plugins_dir)):
        path = os.path.join(plugins_dir, name)
        if os.path.isdir(path) and os.path.exists(
                os.path.join(path, "plugin.json")):
            results.append(audit_plugin(path))
    return results
