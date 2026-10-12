#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - sandbox_runtime.py v2.5 修复
============================================================
仅修一处：RestrictedPython 编译 class 定义时引用 __metaclass__。

现象：
    NameError: name '__metaclass__' is not defined
    （发生在 load_plugin 中 exec class Plugin: 时）

原因：
    RestrictedPython.compile_restricted() 生成 class 定义代码时
    会引用 __metaclass__，需要在 namespace 中提供。

修复：
    在 _build_restricted_globals() 的 return result 前注入：
        result['__metaclass__'] = type

特性：
    - 幂等：已修复则跳过
    - 备份：首次修改前备份为 *.bak.v24
    - 验证：修改后 compile() 检查语法
    - 回滚：语法失败自动还原

用法：
    python fix_sandbox_runtime_v25.py --dry-run
    python fix_sandbox_runtime_v25.py
"""

import os
import sys
import shutil
import argparse
import traceback
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "infrastructure" / "sandbox_runtime.py"
BACKUP_SUFFIX = ".bak.v24"


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
# 锚点与替换
# ------------------------------------------------------------
# 使用 _unpack_sequence_ 尾部作为锚点（v2.4 新增，位置稳定）
OLD_BLOCK = "\n".join([
    "    # _unpack_sequence_：序列解包守卫",
    "    try:",
    "        from RestrictedPython.Guards import guarded_unpack_sequence",
    "        result['_unpack_sequence_'] = guarded_unpack_sequence",
    "    except ImportError:",
    "        pass",
    "",
    "    return result",
])


NEW_BLOCK = "\n".join([
    "    # _unpack_sequence_：序列解包守卫",
    "    try:",
    "        from RestrictedPython.Guards import guarded_unpack_sequence",
    "        result['_unpack_sequence_'] = guarded_unpack_sequence",
    "    except ImportError:",
    "        pass",
    "",
    "    # __metaclass__：class 定义所需（v2.5 补齐）",
    "    # RestrictedPython 编译 class Foo: 时会引用 __metaclass__",
    "    result['__metaclass__'] = type",
    "",
    "    return result",
])


MARKER = "result['__metaclass__'] = type"


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
        description="sandbox_runtime.py v2.5 修复"
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("sandbox_runtime.py v2.5 修复")
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

    # 幂等检测
    print()
    print("【补丁】_build_restricted_globals 注入 __metaclass__")
    if MARKER in content:
        print_skip("已修复，跳过")
        return 0

    # 锚点检测
    if OLD_BLOCK not in content:
        print_fail("锚点未找到")
        print()
        print("  期望锚点（_build_restricted_globals 尾部）：")
        for line in OLD_BLOCK.split('\n'):
            print(f"    | {line}")
        print()
        print("  请检查 v2.4 修复是否已正确应用。")
        return 1

    if content.count(OLD_BLOCK) > 1:
        print_fail("锚点出现多次，请手动检查")
        return 1

    if args.dry_run:
        print_info("[DRY-RUN] 锚点存在，会插入一行：")
        print_info("    result['__metaclass__'] = type")
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
            print_info(f"备份已存在: {backup.name}（保留旧备份）")

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
    print("  1. 语法验证:")
    print("     python -c \"import ast; ast.parse("
          "open('infrastructure/sandbox_runtime.py', "
          "encoding='utf-8').read()); print('OK')\"")
    print("  2. 运行自测:")
    print("     python infrastructure/sandbox_runtime.py")

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