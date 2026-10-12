#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - 项目健康检查
============================================================
8 项检查:
    1. 核心文件完整性
    2. 空文件 / 可疑文件
    3. 超大文件 (>2000 行)
    4. 缺失的 __init__.py
    5. Deprecated API 使用（智能检测）
    6. TODO / FIXME / HACK 统计
    7. 配置文件完整性
    8. .gitignore 内容

用法:
    python tools/health_check.py
"""

import ast
import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    '__pycache__', '.git', '.github', '.idea', '.vscode',
    'venv', '.venv', 'env', '.env', 'node_modules',
    'build', 'dist', 'backup', 'data', 'logs',
    '1.0 QingCaoEditor_Others', '_archived_tools', '_archive',
    'tools',
}


def print_header(title):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def print_ok(msg):
    print("  [OK]   " + msg)


def print_warn(msg):
    print("  [WARN] " + msg)


def print_fail(msg):
    print("  [FAIL] " + msg)


def print_info(msg):
    print("  [INFO] " + msg)


def print_skip(msg):
    print("  [SKIP] " + msg)


def find_py_files():
    result = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith('.py') and '.bak' not in fn:
                result.append(Path(dirpath) / fn)
    return result


# ============================================================
# 检查 1: 核心文件
# ============================================================
def check_core_files():
    print_header("检查 1: 核心文件完整性")

    required = [
        "main.py",
        "app/actions.py",
        "app/event_bus.py",
        "app/plugins.py",
        "app/preferences.py",
        "app/session.py",
        "app/tabs.py",
        "core/document.py",
        "core/editor.py",
        "core/commands.py",
        "core/content_provider.py",
        "core/search.py",
        "ui/main_window.py",
        "ui/editor_view.py",
        "ui/status_bar_widgets.py",
    ]

    missing = [r for r in required if not (ROOT / r).exists()]

    if not missing:
        print_ok(f"所有 {len(required)} 个核心文件都存在")
        return 0

    print_fail(f"缺失 {len(missing)} 个核心文件:")
    for m in missing:
        print(f"      - {m}")
    return len(missing)


# ============================================================
# 检查 2: 空文件
# ============================================================
def check_empty_files(py_files):
    print_header("检查 2: 空文件 / 可疑文件")

    empty = []
    for f in py_files:
        try:
            if f.stat().st_size == 0:
                empty.append(f)
        except Exception:
            continue

    if empty:
        print_warn(f"发现 {len(empty)} 个空文件:")
        for f in empty[:10]:
            print(f"      {f.relative_to(ROOT)}")
    else:
        print_ok("无空文件")
    return len(empty)


# ============================================================
# 检查 3: 超大文件
# ============================================================
def check_large_files(py_files):
    print_header("检查 3: 超大文件（>2000 行）")

    large = []
    for f in py_files:
        try:
            with open(f, encoding='utf-8', errors='replace') as fh:
                n = sum(1 for _ in fh)
        except Exception:
            continue
        if n > 2000:
            large.append((f, n))

    if not large:
        print_ok("无超大文件")
        return 0

    large.sort(key=lambda x: x[1], reverse=True)
    print_warn(f"发现 {len(large)} 个超大文件:")
    for f, n in large[:10]:
        rel = f.relative_to(ROOT)
        print(f"      {str(rel):55s} {n:5d} 行")
    print()
    print_info("建议拆分这些文件")
    return len(large)


# ============================================================
# 检查 4: __init__.py
# ============================================================
def check_init_files():
    print_header("检查 4: 缺失的 __init__.py")

    packages = ["app", "core", "ui", "infrastructure"]
    missing = []
    for pkg in packages:
        p = ROOT / pkg
        if p.is_dir() and not (p / "__init__.py").exists():
            missing.append(pkg)

    if not missing:
        print_ok("所有一级包都有 __init__.py")
        return 0

    print_warn("以下包缺少 __init__.py:")
    for m in missing:
        print(f"      {m}/")
    return len(missing)


# ============================================================
# 检查 5: Deprecated API（智能检测）
# ============================================================
def check_deprecated_api(py_files):
    print_header("检查 5: Deprecated API 使用")

    findings = []

    for f in py_files:
        try:
            with open(f, encoding='utf-8', errors='replace') as fh:
                source = fh.read()
        except Exception:
            continue

        lines = source.split('\n')

        # AST 找 docstring 行范围
        docstring_lines = set()
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef,
                                     ast.FunctionDef, ast.AsyncFunctionDef)):
                    if (node.body and isinstance(node.body[0], ast.Expr)
                            and isinstance(node.body[0].value, ast.Constant)
                            and isinstance(node.body[0].value.value, str)):
                        d = node.body[0]
                        start = d.lineno
                        end = getattr(d, 'end_lineno', start)
                        for ln in range(start, end + 1):
                            docstring_lines.add(ln)
        except SyntaxError:
            pass

        for i, line in enumerate(lines, 1):
            # 跳过 docstring
            if i in docstring_lines:
                continue

            stripped = line.strip()

            # 跳过注释
            if stripped.startswith('#'):
                continue

            # 跳过 hasattr/getattr 兼容分支
            if 'hasattr(' in line or 'getattr(' in line:
                continue

            # 跳过 EditorWidget 自己的 self.prov
            if ('self.prov' in line and
                    'proxy.prov' not in line and
                    'editor.prov' not in line):
                continue

            # 只报属性链访问
            if re.search(r'\b(proxy|editor)\.prov\.[a-zA-Z_]', line):
                findings.append((f, i, 'proxy.prov.xxx'))
            elif re.search(r'\b(proxy|editor)\.document\.enc\b(?!oding)', line):
                findings.append((f, i, 'document.enc.xxx'))

    if not findings:
        print_ok("未发现真正的 deprecated API 调用")
        print_info("（注释/docstring/兼容分支已自动跳过）")
        return 0

    print_warn(f"发现 {len(findings)} 处直接访问:")
    for f, i, desc in findings:
        try:
            rel = f.relative_to(ROOT)
        except Exception:
            rel = str(f)
        print(f"      {rel}:{i}")
        print(f"          → {desc}")

    print()
    print_info("建议迁移到新 API:")
    print_info("  proxy.prov.xxx  →  proxy.document.provider.xxx")
    print_info("  document.enc    →  document.encoding")
    return len(findings)


# ============================================================
# 检查 6: TODO 统计
# ============================================================
def check_todos(py_files):
    print_header("检查 6: TODO / FIXME / HACK 统计")

    pattern = re.compile(r'\b(TODO|FIXME|HACK|XXX)\b')
    counts = {"TODO": 0, "FIXME": 0, "HACK": 0, "XXX": 0}
    by_file = {}

    for f in py_files:
        try:
            with open(f, encoding='utf-8', errors='replace') as fh:
                content = fh.read()
        except Exception:
            continue

        matches = pattern.findall(content)
        if matches:
            rel = str(f.relative_to(ROOT))
            by_file[rel] = len(matches)
            for m in matches:
                counts[m] = counts.get(m, 0) + 1

    total = sum(counts.values())
    if total == 0:
        print_ok("没有 TODO / FIXME 标记")
        return 0

    print_info(f"共 {total} 处:")
    for k, v in counts.items():
        if v > 0:
            print(f"      {k}: {v}")

    print()
    top = sorted(by_file.items(), key=lambda x: x[1], reverse=True)[:5]
    print_info("Top 5 文件:")
    for f, n in top:
        print(f"      {f}  ({n} 处)")
    return total


# ============================================================
# 检查 7: 配置文件
# ============================================================
def check_configs():
    print_header("检查 7: 配置文件完整性")

    configs = [
        ("requirements.txt", True),
        ("requirements-dev.txt", False),
        (".gitignore", True),
        ("README.md", True),
        ("CHANGELOG.md", False),
        ("LICENSE", True),
    ]

    missing_required = []
    missing_optional = []

    for name, required in configs:
        if not (ROOT / name).exists():
            (missing_required if required else missing_optional).append(name)

    if missing_required:
        print_warn("缺失的关键文件:")
        for name in missing_required:
            print(f"      - {name}")
    else:
        print_ok("关键文件都存在")

    if missing_optional:
        print_info("缺失的可选文件:")
        for name in missing_optional:
            print(f"      - {name}")

    return len(missing_required) + len(missing_optional)


# ============================================================
# 检查 8: .gitignore
# ============================================================
def check_gitignore():
    print_header("检查 8: .gitignore 内容")

    gi_path = ROOT / ".gitignore"
    if not gi_path.exists():
        print_warn(".gitignore 不存在")
        return 0

    try:
        content = gi_path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 0

    should_ignore = [
        ("__pycache__",    ["__pycache__"]),
        ("*.pyc",          ["*.pyc", "*.py[cod]", "*.py[co]"]),
        (".pytest_cache",  [".pytest_cache"]),
        ("build/",         ["build/"]),
        ("dist/",          ["dist/"]),
        ("venv/",          ["venv/", "venv\n", "venv\r"]),
        (".venv/",         [".venv/"]),
        ("session.json",   ["session.json"]),
        ("crash.log",      ["crash.log"]),
        ("logs/",          ["logs/"]),
        ("backup/",        ["backup/"]),
        ("data/",          ["data/"]),
    ]

    missing = []
    for display, keywords in should_ignore:
        if not any(kw in content for kw in keywords):
            missing.append(display)

    if not missing:
        print_ok(f".gitignore 包含所有 {len(should_ignore)} 项关键条目")
        return 0

    print_warn(f".gitignore 缺少 {len(missing)} 项:")
    for m in missing:
        print(f"      - {m}")
    return len(missing)


# ============================================================
# 主流程
# ============================================================
def main():
    print()
    print("#" * 60)
    print("#  青草编辑器 - 项目健康检查")
    print("#" * 60)
    print(f"  项目根目录: {ROOT}")

    py_files = find_py_files()
    print(f"  发现 {len(py_files)} 个 .py 文件")

    issues = 0
    issues += check_core_files()
    issues += check_empty_files(py_files)
    issues += check_large_files(py_files)
    issues += check_init_files()
    issues += check_deprecated_api(py_files)
    issues += check_todos(py_files)
    issues += check_configs()
    issues += check_gitignore()

    print_header("汇总")
    if issues == 0:
        print_ok("项目健康 ✓ 未发现明显问题")
    else:
        print_warn(f"共发现 {issues} 项待处理")
        print()
        print_info("处理建议:")
        print("      - 空文件: 手动决定删除或填充")
        print("      - 超大文件: 考虑拆分")
        print("      - 缺失配置: 按提示创建")

    print()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n脚本异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)