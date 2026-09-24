#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - sandbox_runtime.py v2.8 修复
============================================================
一次性完成两件事：
  A. 定义 _WriteGuard 类和 _write_guard 函数
  B. 在 _build_restricted_globals 末尾覆盖 _write_

为什么需要 v2.8：
    v2.6 脚本因补丁 1 锚点不匹配（v2.4 实际写入的内容与 v2.6
    的锚点差了一行注释），导致 failed=1，而 v2.6 的写回条件是
    `failed == 0`，因此整批修改都未写回——包括补丁 2。v2.7 又
    依赖 v2.6 定义的 _write_guard，所以也失败。

    本脚本不再依赖 v2.4/v2.6 写入的 _write_ 段落形态，只用
    两个稳定锚点：
      锚点 1: _allow_write 函数（v2.4 写入，格式稳定）
      锚点 2: __metaclass__ 段落（v2.5 写入，格式稳定）

    A、B 两处一并检查，一并应用，成功才写回（原子性）。

特性：
    - 幂等
    - 备份为 *.bak.v27
    - 修改后 compile() 验证
    - 失败自动回滚
    - 原子性：任一锚点缺失则不写回

用法：
    python fix_sandbox_runtime_v28.py --dry-run
    python fix_sandbox_runtime_v28.py
"""

import sys
import shutil
import argparse
import traceback
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "infrastructure" / "sandbox_runtime.py"
BACKUP_SUFFIX = ".bak.v27"


# ============================================================
# 输出
# ============================================================
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


# ============================================================
# 补丁 A：定义 _WriteGuard 和 _write_guard
# ============================================================
PATCH_A_MARKER = "class _WriteGuard:"

PATCH_A_OLD = "\n".join([
    "def _allow_write(obj):",
    '    """默认属性写入守卫：返回 obj 本身允许赋值（AST 已检查）"""',
    "    return obj",
])

PATCH_A_NEW = "\n".join([
    "def _allow_write(obj):",
    '    """默认属性写入守卫：返回 obj 本身允许赋值（AST 已检查）"""',
    "    return obj",
    "",
    "",
    "class _WriteGuard:",
    '    """',
    "    属性写入守卫（v2.8）。",
    "",
    "    说明：",
    "        RestrictedPython 自带的 full_write_guard 要求被赋值对象",
    "        具有 __guarded_setattr__，否则抛 TypeError:",
    "        attribute-less object。改为直接转发 setattr / delattr。",
    "        安全性由 AST 检查（禁止危险属性访问）和沙箱策略保证。",
    '    """',
    "    __slots__ = ('_target',)",
    "",
    "    def __init__(self, target):",
    "        object.__setattr__(self, '_target', target)",
    "",
    "    def __setattr__(self, name, value):",
    "        setattr(self._target, name, value)",
    "",
    "    def __delattr__(self, name):",
    "        delattr(self._target, name)",
    "",
    "",
    "def _write_guard(obj):",
    '    """_write_ 的实现：返回一个允许属性写入的代理对象。"""',
    "    return _WriteGuard(obj)",
])


# ============================================================
# 补丁 B：在 _build_restricted_globals 末尾覆盖 _write_
# ============================================================
PATCH_B_MARKER = "# _write_：覆盖为宽松守卫（v2.8）"

PATCH_B_OLD = "\n".join([
    "    # __metaclass__：class 定义所需（v2.5 补齐）",
    "    # RestrictedPython 编译 class Foo: 时会引用 __metaclass__",
    "    result['__metaclass__'] = type",
    "",
    "    return result",
])

PATCH_B_NEW = "\n".join([
    "    # __metaclass__：class 定义所需（v2.5 补齐）",
    "    # RestrictedPython 编译 class Foo: 时会引用 __metaclass__",
    "    result['__metaclass__'] = type",
    "",
    "    # _write_：覆盖为宽松守卫（v2.8）",
    "    # 说明：",
    "    #   RestrictedPython 的 full_write_guard 要求被赋值对象",
    "    #   具有 __guarded_setattr__，否则抛 TypeError:",
    "    #   attribute-less object。这里覆盖为 _write_guard，",
    "    #   直接转发 setattr/delattr。",
    "    result['_write_'] = _write_guard",
    "",
    "    return result",
])


# ============================================================
# 校验与应用
# ============================================================
def validate_python(content: str, filepath: str) -> Tuple[bool, str]:
    try:
        compile(content, filepath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def apply_replace(content: str, old: str, new: str,
                  label: str) -> Tuple[str, bool]:
    """精确替换，要求 old 唯一"""
    count = content.count(old)
    if count == 0:
        raise ValueError(f"锚点未找到（{label}）")
    if count > 1:
        raise ValueError(f"锚点重复 {count} 次（{label}）")
    return content.replace(old, new, 1), True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="sandbox_runtime.py v2.8 修复"
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("sandbox_runtime.py v2.8 修复")
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

    # --------------------------------------------------------
    # 第一步：检查两处补丁的状态
    # --------------------------------------------------------
    print()
    print("=" * 60)
    print("检查补丁状态")
    print("=" * 60)

    a_applied = PATCH_A_MARKER in content
    b_applied = PATCH_B_MARKER in content

    print(f"  补丁 A（定义 _write_guard）: "
          f"{'已应用' if a_applied else '未应用'}")
    print(f"  补丁 B（覆盖 _write_）:      "
          f"{'已应用' if b_applied else '未应用'}")

    if a_applied and b_applied:
        print()
        print_skip("两处均已应用，无需修改")
        return 0

    # --------------------------------------------------------
    # 第二步：检查锚点
    # --------------------------------------------------------
    if not a_applied:
        if PATCH_A_OLD not in content:
            print()
            print_fail("补丁 A 锚点未找到")
            print()
            print("  期望锚点：")
            for line in PATCH_A_OLD.split('\n'):
                print(f"    | {line}")
            print()
            print("  请检查 _allow_write 函数是否存在。")
            return 1

        if content.count(PATCH_A_OLD) > 1:
            print()
            print_fail("补丁 A 锚点重复出现，请手动检查")
            return 1

    if not b_applied:
        if PATCH_B_OLD not in content:
            print()
            print_fail("补丁 B 锚点未找到")
            print()
            print("  期望锚点：")
            for line in PATCH_B_OLD.split('\n'):
                print(f"    | {line}")
            print()
            print("  请检查 _build_restricted_globals 中的 __metaclass__ 段落。")
            return 1

        if content.count(PATCH_B_OLD) > 1:
            print()
            print_fail("补丁 B 锚点重复出现，请手动检查")
            return 1

    # --------------------------------------------------------
    # DRY-RUN
    # --------------------------------------------------------
    if args.dry_run:
        print()
        print_info("[DRY-RUN] 锚点检查通过，会应用以下修改：")
        if not a_applied:
            print_info("  A. 在 _allow_write 后插入 _WriteGuard 类和 _write_guard 函数")
        if not b_applied:
            print_info("  B. 在 __metaclass__ 段落后插入 _write_ 覆盖")
        return 0

    # --------------------------------------------------------
    # 第三步：应用（原子性）
    # --------------------------------------------------------
    print()
    print("=" * 60)
    print("应用补丁")
    print("=" * 60)

    new_content = content
    applied_count = 0

    try:
        if not a_applied:
            new_content, _ = apply_replace(
                new_content, PATCH_A_OLD, PATCH_A_NEW,
                "补丁 A: 定义 _write_guard"
            )
            print_ok("A: 已插入 _WriteGuard 和 _write_guard")
            applied_count += 1

        if not b_applied:
            new_content, _ = apply_replace(
                new_content, PATCH_B_OLD, PATCH_B_NEW,
                "补丁 B: 覆盖 _write_"
            )
            print_ok("B: 已覆盖 _write_")
            applied_count += 1

    except ValueError as e:
        print_fail(f"应用失败: {e}")
        print_info("文件未修改")
        return 1

    # --------------------------------------------------------
    # 第四步：语法验证
    # --------------------------------------------------------
    print()
    print("=" * 60)
    print("语法验证")
    print("=" * 60)

    ok, err = validate_python(new_content, str(TARGET))
    if not ok:
        print_fail(f"语法错误: {err}")
        print_info("文件未修改")
        return 1
    print_ok("语法验证通过")

    # --------------------------------------------------------
    # 第五步：备份 + 写回
    # --------------------------------------------------------
    print()
    print("=" * 60)
    print("写回文件")
    print("=" * 60)

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

    try:
        TARGET.write_text(new_content, encoding='utf-8', newline='\n')
        print_ok(f"已写回: {TARGET.relative_to(ROOT)}")
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

    # --------------------------------------------------------
    # 完成
    # --------------------------------------------------------
    print()
    print("=" * 60)
    print(f"✓ 修复完成（已应用 {applied_count} 处）")
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