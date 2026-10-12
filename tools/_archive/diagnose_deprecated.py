#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
精确诊断 deprecated API 使用
============================================================
逐个显示每处 .prov / .enc 的实际代码 + 分类：
    - 注释          纯文档，无影响
    - 兼容分支      hasattr/getattr 检查，故意保留
    - 直接访问      x.prov.yyy / x.enc.yyy
    - 赋值          x.prov = yyy（已被 setter 兼容）

用法：
    python tools/diagnose_deprecated.py
    python tools/diagnose_deprecated.py --only-direct
"""

import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    '__pycache__', '.git', '.github', '.venv', 'venv',
    'env', '.env', 'build', 'dist', 'node_modules',
    'backup', 'data', 'logs', '_archive', 'tools',
    '1.0 QingCaoEditor_Others', '_archived_tools',
}


def print_header(t):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


# 匹配模式
PAT_PROV = re.compile(r'\.\bprov\b')
PAT_ENC = re.compile(r'\.\benc\b(?!oding)')


def classify(line: str) -> str:
    """给一行代码分类"""
    stripped = line.strip()

    # 注释
    if stripped.startswith('#'):
        return "注释"

    # hasattr / getattr 兼容检查
    if 'hasattr(' in line or 'getattr(' in line:
        return "兼容分支"

    # 赋值（= xxx 在右侧，或 x.prov = ...）
    if re.search(r'\.\b(prov|enc)\s*=', line):
        return "赋值"

    # 直接访问
    if PAT_PROV.search(line) or PAT_ENC.search(line):
        return "直接访问"

    return "未知"


def main():
    only_direct = '--only-direct' in sys.argv

    print_header("精确诊断 deprecated API")
    print(f"  项目根目录: {ROOT}")
    if only_direct:
        print(f"  模式: 只显示『直接访问』")
    print()

    # 收集
    results = {
        "注释": [],
        "兼容分支": [],
        "赋值": [],
        "直接访问": [],
        "未知": [],
    }

    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for fn in filenames:
            if not fn.endswith('.py'):
                continue
            if '.bak' in fn:
                continue

            fpath = Path(dirpath) / fn
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()
            except Exception:
                continue

            for lineno, line in enumerate(lines, 1):
                if not (PAT_PROV.search(line) or PAT_ENC.search(line)):
                    continue

                cat = classify(line)
                results[cat].append({
                    'file': fpath.relative_to(ROOT),
                    'line': lineno,
                    'code': line.rstrip()[:100],
                })

    # 输出
    for cat in ["注释", "兼容分支", "赋值", "直接访问", "未知"]:
        items = results[cat]
        if not items:
            continue
        if only_direct and cat != "直接访问":
            continue

        print_header(f"{cat} ({len(items)} 处)")
        for item in items:
            print(f"  {item['file']}:{item['line']}")
            print(f"      {item['code']}")
        print()

    # 汇总
    print_header("汇总")
    total = sum(len(v) for v in results.values())
    print(f"  总计: {total} 处")
    for cat in ["注释", "兼容分支", "赋值", "直接访问", "未知"]:
        cnt = len(results[cat])
        if cnt > 0:
            print(f"    {cat}: {cnt}")

    print()
    print("  建议:")
    if results["直接访问"]:
        print(f"    - {len(results['直接访问'])} 处『直接访问』可考虑迁移到新 API")
    else:
        print("    - 无『直接访问』，无需改代码")
    print("    - 升级 health_check 让它识别注释/兼容分支")
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