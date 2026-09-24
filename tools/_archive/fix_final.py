#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - 最终清理（补丁 6e + atexit）
============================================================
处理 v2 补丁集遗漏的 2 项：
    1. 补丁 6e: deferred_init 结束的 print
    2. atexit 打印改为 logger

用法:
    python fix_final.py --dry-run
    python fix_final.py
"""

import sys
import shutil
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.final"


def print_header(t):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


def print_ok(m):
    print(f"  [OK]   {m}")


def print_skip(m):
    print(f"  [SKIP] {m}")


def print_fail(m):
    print(f"  [FAIL] {m}")


def print_info(m):
    print(f"  [INFO] {m}")


# ============================================================
# 修复定义
# ============================================================
FIX_6E_OLD = """            logger.info("延迟初始化完成")
            print(">>> [MAIN] deferred_init 全部完成", flush=True)"""

FIX_6E_NEW = """            logger.info("延迟初始化完成")"""


FIX_ATEXIT_OLD = '''@atexit.register
def _on_exit():
    """进程退出时输出标记"""
    try:
        sys.stderr.write("\\n[MAIN] 进程退出 (atexit 触发)\\n")
        sys.stderr.flush()
    except Exception:
        pass'''


FIX_ATEXIT_NEW = '''@atexit.register
def _on_exit():
    """进程退出时输出日志标记"""
    try:
        import logging
        logging.getLogger("QingCao").info("进程退出 (atexit)")
    except Exception:
        pass'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("青草编辑器 最终清理")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际修复'}")

    main_py = ROOT / "main.py"
    if not main_py.exists():
        print_fail("main.py 不存在")
        return 1

    content = main_py.read_text(encoding='utf-8')
    original = content
    applied = 0
    skipped = 0

    # ---- 修复 6e ----
    print()
    print("【补丁 6e: deferred_init 结束 print】")
    if FIX_6E_OLD not in content:
        print_skip("已修复或锚点不匹配")
        skipped += 1
    else:
        if args.dry_run:
            print_info("[DRY-RUN] 将移除此行:")
            print_info('  print(">>> [MAIN] deferred_init 全部完成", flush=True)')
        else:
            content = content.replace(FIX_6E_OLD, FIX_6E_NEW, 1)
            print_ok("已移除 deferred_init 结束的 print")
        applied += 1

    # ---- 修复 atexit ----
    print()
    print("【补丁 atexit: 进程退出打印】")
    if FIX_ATEXIT_OLD not in content:
        print_skip("已修复或锚点不匹配")
        skipped += 1
    else:
        if args.dry_run:
            print_info("[DRY-RUN] 将把 atexit 的 stderr.write 改为 logger")
        else:
            content = content.replace(FIX_ATEXIT_OLD, FIX_ATEXIT_NEW, 1)
            print_ok("atexit 打印已改为 logger")
        applied += 1

    # ---- 写回 ----
    if not args.dry_run and content != original:
        # 语法验证
        try:
            compile(content, str(main_py), 'exec')
        except SyntaxError as e:
            print_fail(f"语法错误: line {e.lineno}: {e.msg}")
            return 1

        # 备份
        if not args.no_backup:
            backup = Path(str(main_py) + BACKUP_SUFFIX)
            if not backup.exists():
                shutil.copy2(main_py, backup)
                print_info(f"已备份: {backup.name}")

        main_py.write_text(content, encoding='utf-8', newline='\n')
        print()
        print_ok("main.py 已更新")

    # ---- 汇总 ----
    print()
    print("=" * 60)
    print(f"  已应用: {applied}")
    print(f"  已跳过: {skipped}")
    print("=" * 60)

    if args.dry_run:
        print()
        print("⚠ DRY-RUN 模式，未修改文件")
        print("  运行 `python fix_final.py` 应用")

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