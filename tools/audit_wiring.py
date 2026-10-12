#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""接线审计：找出"定义/存在但没有任何生产调用方"的代码

背景
----
本项目曾出现多次**同类缺陷**：模块写得完整、文档也写了，
但**从未被接线**，因此实际功能为零。已发现的例子：

  * `infrastructure/plugin_sandbox.py` + `sandbox_runtime.py`（3390 行）
    —— 无生产调用方，且实测无法启动（已删除）
  * `infrastructure/sound_manager.py`（1600+ 行）—— 曾零调用
  * 插件权限确认对话框 —— 启动路径用裸 loader，确认框永不弹出
  * 热重载 —— 只 print("可能需要重启编辑器")
  * `locale/*.mo` —— 全仓没有编译产物，4 种语言从未生效

这类缺陷**单测覆盖不到**（测试只测被调用的函数），是最容易漏掉的一类。

本工具用 AST + 全仓引用计数找出候选，输出按文件聚合。

判定规则：
  1. 收集所有顶层 `def` / `class` 名（生产代码）
  2. 统计每个名字在**全仓生产代码**中作为名字出现的次数
  3. 只出现 1 次（即只有定义处）= 无调用方 → 候选
  4. 排除：魔术方法、测试钩子、Qt 生命周期、装饰器注册的名字等

注意：这是**启发式**筛查，不是证明。候选需人工确认为真缺陷才可动手。

用法::

    python tools/audit_wiring.py                  # 汇总
    python tools/audit_wiring.py --files          # 按文件分组列出
    python tools/audit_wiring.py --module core.lsp_client
    python tools/audit_wiring.py --json out.json
"""
import argparse
import ast
import io
import json
import os
import re
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP_DIRS = {
    '__pycache__', '.git', 'build', 'dist', 'site', '_archive',
    '.pytest_cache', 'venv', '.venv', 'node_modules',
}

# 这些名字天然"只出现一次"或由框架回调，不参与判定
IGNORE_NAMES = {
    'main', 'setup', 'teardown', 'run', 'start', 'stop', 'close',
    'show', 'hide', 'paintEvent', 'closeEvent', 'resizeEvent',
    'keyPressEvent', 'mousePressEvent', 'wheelEvent', 'dragEnterEvent',
    'dropEvent', 'showEvent', 'hideEvent', 'changeEvent', 'focusInEvent',
    'focusOutEvent', 'contextMenuEvent', 'keyReleaseEvent', 'enterEvent',
    'leaveEvent', 'moveEvent', 'timerEvent', 'eventFilter',
}

# 这些前缀是 Qt/框架生命周期或私有辅助，允许无外部调用
IGNORE_PREFIXES = ('_on_', 'on_', 'test_', '_test', 'visit_', 'handle_')

# 由装饰器/元类注册、或通过字符串查找的名字，允许无直接调用
REGISTER_DECORATORS = (
    'register', 'command', 'action', 'slot', 'property', 'staticmethod',
    'classmethod', 'abstractmethod', 'singleton', 'lru_cache',
)

PROD_TOP = ('app', 'core', 'ui', 'infrastructure', 'plugins')


def iter_py(include_tests=False):
    for base in PROD_TOP:
        if not os.path.isdir(os.path.join(ROOT, base)):
            continue
        for root, dirs, files in os.walk(os.path.join(ROOT, base)):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if f.endswith('.py'):
                    yield os.path.join(root, f)
    if include_tests:
        tdir = os.path.join(ROOT, 'tests')
        if os.path.isdir(tdir):
            for root, dirs, files in os.walk(tdir):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for f in files:
                    if f.endswith('.py'):
                        yield os.path.join(root, f)


def rel(p):
    return os.path.relpath(p, ROOT).replace('\\', '/')


def read(p):
    try:
        return io.open(p, encoding='utf-8', errors='replace').read()
    except OSError:
        return ''


def collect_definitions(paths):
    """返回 [(name, kind, file, lineno)]"""
    out = []
    for p in paths:
        src = read(p)
        if not src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append((node.name, 'func', rel(p), node.lineno))
            elif isinstance(node, ast.ClassDef):
                out.append((node.name, 'class', rel(p), node.lineno))
    return out


def count_name_occurrences(paths):
    """统计每个标识符在全仓出现的次数（词法级，够用且不误报太多）"""
    counts = {}
    token_re = re.compile(r'[A-Za-z_]\w*')
    for p in paths:
        src = read(p)
        for m in token_re.finditer(src):
            n = m.group(0)
            counts[n] = counts.get(n, 0) + 1
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description='接线审计')
    parser.add_argument('--files', action='store_true', help='按文件分组输出')
    parser.add_argument('--module', help='只审计某个模块前缀，如 core.lsp_client')
    parser.add_argument('--json', help='输出 JSON 到指定路径')
    parser.add_argument('--include-tests', action='store_true',
                        help='把 tests/ 也计入引用来源（更宽松）')
    args = parser.parse_args(argv)

    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    paths = list(iter_py())
    defs = collect_definitions(paths)
    # 引用来源：生产代码（可选含测试）
    ref_paths = list(iter_py(include_tests=args.include_tests))
    counts = count_name_occurrences(ref_paths)

    candidates = []
    for name, kind, f, line in defs:
        if name in IGNORE_NAMES or name.startswith('__'):
            continue
        if name.startswith(IGNORE_PREFIXES):
            continue
        if args.module and not f.replace('/', '.').startswith(args.module):
            continue
        if counts.get(name, 0) <= 1:
            candidates.append({'name': name, 'kind': kind,
                               'file': f, 'line': line})

    by_file = {}
    for c in candidates:
        by_file.setdefault(c['file'], []).append(c)

    print('=' * 72)
    print('接线审计（启发式）：定义存在但全仓无其它引用')
    print('=' * 72)
    print('  扫描生产代码文件 : %d' % len(paths))
    print('  提取定义         : %d 个（函数/类）' % len(defs))
    print('  候选（无调用方） : %d 个，分布在 %d 个文件'
          % (len(candidates), len(by_file)))
    print()

    # 只统计"公共 API"（不以 _ 开头）——这些更可能是真缺陷
    public = [c for c in candidates if not c['name'].startswith('_')]
    print('  其中**公共名字**（不以 _ 开头，更可能是真缺陷）: %d 个' % len(public))
    print()

    if args.files:
        ranked = sorted(by_file.items(), key=lambda kv: -len(kv[1]))
        for f, items in ranked[:40]:
            pub = [i for i in items if not i['name'].startswith('_')]
            if not pub:
                continue
            print('  %s  （%d 个候选，%d 个公共）' % (f, len(items), len(pub)))
            for i in pub[:12]:
                print('      L%-5d [%s] %s' % (i['line'], i['kind'], i['name']))
            if len(pub) > 12:
                print('      ... 其余 %d 个' % (len(pub) - 12))
            print()
    else:
        print('  候选最多的 15 个文件（仅列公共名字）：')
        ranked = sorted(by_file.items(), key=lambda kv: -len(kv[1]))
        for f, items in ranked[:15]:
            pub = [i for i in items if not i['name'].startswith('_')]
            if pub:
                print('    %-52s %3d 个公共候选' % (f, len(pub)))

    if args.json:
        with io.open(args.json, 'w', encoding='utf-8') as fh:
            json.dump({'candidates': candidates,
                       'summary': {'files': len(paths),
                                   'defs': len(defs),
                                   'candidates': len(candidates)}},
                      fh, ensure_ascii=False, indent=1)
        print()
        print('  已写出: %s' % args.json)

    print()
    print('提示：候选不等于缺陷。请人工确认是否为：')
    print('  * 从未接线的功能模块（真缺陷）')
    print('  * 供插件/外部调用的公共 API（保留）')
    print('  * 框架回调 / 由字符串反射调用（保留）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
