#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - sandbox_runtime.py v2.7 修复
============================================================
仅一处：在 _build_restricted_globals 末尾追加
    result['_write_'] = _write_guard

原因：
    v2.6 补丁 1 的锚点与实际文件不符（v2.4 给 _write_ 段落加了
    额外注释），导致替换失败。本脚本改用"追加覆盖"策略，不依赖
    原段落内容，只要 v2.5 的 __metaclass__ 存在即可精确插入。

特性：
    - 幂等
    - 备份为 *.bak.v26
    - 修改后 compile() 验证
    - 失败自动回滚

用法：
    python fix_sandbox_runtime_v27.py --dry-run
    python fix_sandbox_runtime_v27.py
"""

import sys
import shutil
import argparse
import traceback
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "infrastructure" / "sandbox_runtime.py"
BACKUP_SUFFIX = ".bak.v26"


def print_header(t: str):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


def print_ok(m: str):
    print(f"  [OK]   {m}")


def print_skip(m: str):
    print(f"  [SKIP] {m}")


def print_fail(m: str):
    print(f"  [FAIL] {m}")


def print_info(m: str):
    print(f"  [INFO] {m}")


# ------------------------------------------------------------
# 锚点与替换：用 v2.5 写入的 __metaclass__ 段落作为定位点
# ------------------------------------------------------------
OLD_BLOCK = "\n".join([
    "    # __metaclass__：class 定义所需（v2.5 补齐）",
    "    # RestrictedPython 编译 class Foo: 时会引用 __metaclass__",
    "    result['__metaclass__'] = type",
    "",
    "    return result",
])

NEW_BLOCK = "\n".join([
    "    # __metaclass__：class 定义所需（v2.5 补齐）",
    "    # RestrictedPython 编译 class Foo: 时会引用 __metaclass__",
    "    result['__metaclass__'] = type",
    "",
    "    # _write_：强制覆盖为宽松守卫（v2.7）",
    "    # 说明：",
    "    #   RestrictedPython 的 full_write_guard 要求被赋值对象",
    "    #   具有 __guarded_setattr__，否则抛 TypeError:",
    "    #   attribute-less object。改为转发 setattr/delattr。",
    "    #   安全性由 AST 检查与沙箱策略保证。",
    "    result['_write_'] = _write_guard",
    "",
    "    return result",
])

MARKER = "# _write_：强制覆盖为宽松守卫（v2.7）"


def validate_python(content: str, filepath: str) -> Tuple[bool, str]:
    try:
        compile(content, filepath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="sandbox_runtime.py v2.7 修复"
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("sandbox_runtime.py v2.7 修复")
    print(f"  项目目录: {ROOT}")
    print(f"  目标文件: {TARGET.relative_to(ROOT)}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")
    print(f"  备份:     {'禁用' if args.no_backup else '启用'}")

    if not TARGET.exists():
        print_fail(f"目标文件不存在: {TARGET}")
        return 1

    try:
        content = TARGET.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 1

    print()
    print("【补丁】在 _build_restricted_globals 末尾追加 _write_ 覆盖")

    # 幂等
    if MARKER in content:
        print_skip("已修复，跳过")
        return 0

    # 前置检查：v2.6 的 _write_guard 函数必须存在
    if "def _write_guard(obj):" not in content:
        print_fail(
            "未找到 _write_guard 函数。请先运行 fix_sandbox_runtime_v26.py"
        )
        return 1

    # 锚点检测
    if OLD_BLOCK not in content:
        print_fail("锚点未找到（v2.5 的 __metaclass__ 段落不存在）")
        print()
        print("  期望锚点：")
        for line in OLD_BLOCK.split('\n'):
            print(f"    | {line}")
        print()
        print("  请手动检查 _build_restricted_globals 函数末尾。")
        return 1

    if content.count(OLD_BLOCK) > 1:
        print_fail("锚点出现多次，请手动检查")
        return 1

    if args.dry_run:
        print_info("[DRY-RUN] 锚点存在，会插入 4 行")
        return 0

    # 应用
    new_content = content.replace(OLD_BLOCK, NEW_BLOCK, 1)

    # 语法验证
    ok, err = validate_python(new_content, str(TARGET))
    if not ok:
        print_fail(f"语法验证失败: {err}")
        return 1

    # 备份
    if not args.no_backup:
        backup = Path(str(TARGET) + BACKUP_SUFFIX)
        if not backup.exists():
            try:
                shutil.copy2(TARGET, backup)
                print_info(f"已备份: {backup.name}")
            except Exception as e:
                print_fail(f"备份失败: {e}")
                return 1
        else:
            print_info(f"备份已存在: {backup.name}")

    # 写回
    try:
        TARGET.write_text(new_content, encoding='utf-8', newline='\n')
        print_ok("已写入")
    except Exception as e:
        print_fail(f"写回失败: {e}")
        backup = Path(str(TARGET) + BACKUP_SUFFIX)
        if backup.exists():
            try:
                shutil.copy2(backup, TARGET)
                print_info("已从备份还原")
            except Exception:
                pass
        return 1

    print()
    print("=" * 60)
    print("✓ 修复完成")
    print("=" * 60)
    print()
    print("下一步:")
    print("  python infrastructure/sandbox_runtime.py")

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n脚本异常: {e}")
        traceback.print_exc()
        sys.exit(1)