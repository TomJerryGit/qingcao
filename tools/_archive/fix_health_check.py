#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修复 health_check.py 中 .gitignore 检查的误报
============================================================
问题：
    `*.py[cod]` 已被 .gitignore 使用，但 health_check 检查
    的是字面量 `*.pyc`，导致误报"缺少 *.pyc"。

方案：
    将 should_ignore 从「字符串列表」改为「(显示名, 关键词列表)」，
    任一关键词命中即视为已忽略。

用法：
    python tools/fix_health_check.py --dry-run
    python tools/fix_health_check.py
============================================================
"""

import sys
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "tools" / "health_check.py"


def print_header(t):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


def print_ok(m):
    print("  [OK]   " + m)


def print_skip(m):
    print("  [SKIP] " + m)


def print_fail(m):
    print("  [FAIL] " + m)


def validate_syntax(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            src = f.read()
        compile(src, str(path), 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


# ============================================================
# 旧函数（锚点）
# ============================================================
OLD_BLOCK = "\n".join([
    "def check_gitignore():",
    '    print_header("检查 8: .gitignore 内容")',
    "",
    '    gi_path = ROOT / ".gitignore"',
    "    if not gi_path.exists():",
    '        print_warn(".gitignore 不存在")',
    "        return 0",
    "",
    "    try:",
    "        content = gi_path.read_text(encoding='utf-8')",
    "    except Exception as e:",
    '        print_fail(f"读取失败: {e}")',
    "        return 0",
    "",
    "    # 应该被忽略的",
    "    should_ignore = [",
    "        '__pycache__',",
    "        '*.pyc',",
    "        '.pytest_cache',",
    "        'build/',",
    "        'dist/',",
    "        'venv/',",
    "        '.venv/',",
    "        'session.json',",
    "        'crash.log',",
    "        'logs/',",
    "        'backup/',",
    "        'data/',",
    "    ]",
    "",
    "    missing = [item for item in should_ignore if item not in content]",
    "",
    "    if not missing:",
    '        print_ok(f".gitignore 包含所有 {len(should_ignore)} 项关键条目")',
    "        return 0",
    "",
    '    print_warn(f".gitignore 缺少 {len(missing)} 项:")',
    "    for m in missing:",
    '        print(f"      - {m}")',
    "",
    "    print()",
    '    print_info("建议追加到 .gitignore:")',
    "    for m in missing:",
    '        print(f"      {m}")',
    "",
    "    return len(missing)",
])


# ============================================================
# 新函数（支持多关键词匹配）
# ============================================================
NEW_BLOCK = "\n".join([
    "def check_gitignore():",
    '    print_header("检查 8: .gitignore 内容")',
    "",
    '    gi_path = ROOT / ".gitignore"',
    "    if not gi_path.exists():",
    '        print_warn(".gitignore 不存在")',
    "        return 0",
    "",
    "    try:",
    "        content = gi_path.read_text(encoding='utf-8')",
    "    except Exception as e:",
    '        print_fail(f"读取失败: {e}")',
    "        return 0",
    "",
    "    # (显示名, 检测关键词列表)",
    "    # 任一关键词命中即视为已忽略。",
    "    # 例如 *.pyc 的检测同时接受:",
    "    #   *.pyc        （明确写 *.pyc）",
    "    #   *.py[cod]    （Python 标准写法，覆盖 pyc/pyo/pyd）",
    "    #   *.py[co]     （等价写法）",
    "    should_ignore = [",
    '        ("__pycache__",    ["__pycache__"]),',
    '        ("*.pyc",          ["*.pyc", "*.py[cod]", "*.py[co]"]),',
    '        (".pytest_cache",  [".pytest_cache"]),',
    '        ("build/",         ["build/"]),',
    '        ("dist/",          ["dist/"]),',
    '        ("venv/",          ["venv/", "venv\\n", "venv\\r"]),',
    '        (".venv/",         [".venv/"]),',
    '        ("session.json",   ["session.json"]),',
    '        ("crash.log",      ["crash.log"]),',
    '        ("logs/",          ["logs/"]),',
    '        ("backup/",        ["backup/"]),',
    '        ("data/",          ["data/"]),',
    "    ]",
    "",
    "    missing = []",
    "    for display, keywords in should_ignore:",
    "        if not any(kw in content for kw in keywords):",
    "            missing.append(display)",
    "",
    "    if not missing:",
    '        print_ok(f".gitignore 包含所有 {len(should_ignore)} 项关键条目")',
    "        return 0",
    "",
    '    print_warn(f".gitignore 缺少 {len(missing)} 项:")',
    "    for m in missing:",
    '        print(f"      - {m}")',
    "",
    "    print()",
    '    print_info("建议追加到 .gitignore:")',
    "    for m in missing:",
    '        print(f"      {m}")',
    "",
    "    return len(missing)",
])


# ============================================================
# 主流程
# ============================================================
def main():
    dry_run = '--dry-run' in sys.argv
    no_backup = '--no-backup' in sys.argv

    print_header("修复 health_check.py 误报")
    print(f"  目标文件: {TARGET}")
    print(f"  模式:     {'DRY-RUN' if dry_run else '实际修复'}")

    if not TARGET.exists():
        print_fail(f"文件不存在: {TARGET}")
        return 1

    # 读取
    try:
        content = TARGET.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 1

    # 幂等检测
    if "任一关键词命中即视为已忽略" in content:
        print_skip("已修复，跳过")
        return 0

    # 锚点检测
    if OLD_BLOCK not in content:
        print_fail("未找到旧版 check_gitignore 函数")
        print()
        print("  可能原因：")
        print("    1. health_check.py 已被修改")
        print("    2. 版本不一致")
        print()
        print("  请打开 tools/health_check.py，找到 check_gitignore 函数，")
        print("  手动替换为下面新版内容：")
        print()
        for line in NEW_BLOCK.split('\n'):
            print("  " + line)
        return 1

    if dry_run:
        print_ok("[DRY-RUN] 会替换 check_gitignore 函数")
        print()
        print("  新版本支持多关键词匹配:")
        print("    *.pyc 会同时检测: *.pyc / *.py[cod] / *.py[co]")
        return 0

    # 备份
    if not no_backup:
        backup = TARGET.with_suffix(".py.bak.health")
        try:
            shutil.copy2(TARGET, backup)
            print_ok(f"已备份: {backup.name}")
        except Exception as e:
            print_fail(f"备份失败: {e}")
            return 1

    # 替换
    new_content = content.replace(OLD_BLOCK, NEW_BLOCK, 1)

    try:
        TARGET.write_text(new_content, encoding='utf-8')
    except Exception as e:
        print_fail(f"写入失败: {e}")
        return 1

    # 语法检查
    ok, err = validate_syntax(TARGET)
    if not ok:
        print_fail(f"语法检查失败: {err}")
        if not no_backup:
            backup = TARGET.with_suffix(".py.bak.health")
            if backup.exists():
                shutil.copy2(backup, TARGET)
                print_fail("已从备份还原")
        return 1

    print_ok("已替换 check_gitignore 函数")
    print_ok("语法验证通过")

    print()
    print("=" * 60)
    print("验证:")
    print("=" * 60)
    print()
    print("  python tools\\qingcao.py health")
    print()

    return 0


if __name__ == '__main__':
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