#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快捷键冲突诊断
============================================================
扫描项目中所有 QKeySequence / setShortcut 定义，
找出重复的快捷键。

用法：
    python tools/diagnose_shortcut.py
    python tools/diagnose_shortcut.py Ctrl+Shift+D
"""

import os
import re
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    '__pycache__', '.git', '.github', '.venv', 'venv',
    'env', '.env', 'build', 'dist', 'node_modules',
    'backup', 'data', 'logs', '_archive',
    '1.0 QingCaoEditor_Others', '_archived_tools',
}


# 匹配各种快捷键定义方式
PATTERNS = [
    # QKeySequence("Ctrl+Shift+D")
    re.compile(r'QKeySequence\(\s*["\']([^"\']+)["\']'),
    # setShortcut("Ctrl+Shift+D")
    re.compile(r'setShortcut\(\s*["\']([^"\']+)["\']'),
    # "Ctrl+Shift+D",  在 create_action / _add_action 调用里
    # 用更宽松的方式：匹配字符串字面量里含 Ctrl/Alt/Shift/F 的组合
    re.compile(r'["\'](Ctrl\+[A-Za-z0-9\+\-\=\[\]\/\\\;\,\.\`]+)["\']'),
    re.compile(r'["\'](Alt\+[A-Za-z0-9\+]+)["\']'),
    re.compile(r'["\'](Shift\+[A-Za-z0-9\+]+)["\']'),
]


def find_py_files():
    result = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith('.py') and '.bak' not in fn:
                result.append(Path(dirpath) / fn)
    return result


def normalize(seq: str) -> str:
    """标准化快捷键字符串（大小写、排序）"""
    parts = [p.strip() for p in re.split(r'\+', seq)]
    mods = sorted(
        [p.capitalize() for p in parts[:-1]],
    )
    key = parts[-1].upper() if parts else ''
    return '+'.join(mods + [key])


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None

    print()
    print("=" * 60)
    print("快捷键冲突诊断")
    print("=" * 60)
    print(f"  项目根目录: {ROOT}")
    if target:
        print(f"  目标快捷键: {target}")

    py_files = find_py_files()
    print(f"  发现 {len(py_files)} 个 .py 文件")
    print()

    # 收集：shortcut -> [(文件, 行号, 上下文)]
    shortcuts = defaultdict(list)

    for f in py_files:
        try:
            with open(f, encoding='utf-8', errors='replace') as fh:
                lines = fh.readlines()
        except Exception:
            continue

        for lineno, line in enumerate(lines, 1):
            # 跳过注释
            stripped = line.strip()
            if stripped.startswith('#'):
                continue

            for pattern in PATTERNS:
                for m in pattern.finditer(line):
                    seq = m.group(1)
                    # 跳过明显不是快捷键的（比如 "Ctrl" 单独出现）
                    if seq in ('Ctrl', 'Alt', 'Shift', 'Meta'):
                        continue

                    norm = normalize(seq)
                    shortcuts[norm].append({
                        'file': f,
                        'line': lineno,
                        'raw': seq,
                        'context': line.strip()[:80],
                    })

    # 找出冲突
    conflicts = {
        seq: refs for seq, refs in shortcuts.items()
        if len(refs) > 1
    }

    if not conflicts:
        print("[OK] 未发现快捷键冲突")
        return 0

    print(f"[WARN] 发现 {len(conflicts)} 个冲突快捷键")
    print()

    # 按冲突数量排序
    sorted_conflicts = sorted(
        conflicts.items(),
        key=lambda x: -len(x[1])
    )

    for seq, refs in sorted_conflicts:
        if target and normalize(target) != seq:
            continue

        print("=" * 60)
        print(f"  {seq}  (共 {len(refs)} 处定义)")
        print("=" * 60)
        for ref in refs:
            rel = ref['file'].relative_to(ROOT)
            print(f"  {rel}:{ref['line']}")
            print(f"      {ref['context']}")
        print()

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        print(f"\n脚本异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)