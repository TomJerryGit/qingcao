#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - sandbox_runtime.py v2.6 修复
============================================================
修复：RestrictedPython.full_write_guard 拒绝插件类的属性写入。

现象：
    TypeError: attribute-less object (assign or del)
    （发生在插件 self.counter = 0 时）

原因：
    full_write_guard 要求被赋值对象有 __guarded_setattr__ 方法，
    否则拒绝属性赋值。对一般插件过于严格。

修复：
    1. 新增 _WriteGuard 类与 _write_guard() 函数，直接转发
       setattr / delattr。
    2. _build_restricted_globals 中的 _write_ 改用 _write_guard，
       不再使用 full_write_guard。

安全性：
    - AST 检查禁止 .__class__ / .__bases__ / .__globals__ 等
      危险属性访问
    - 沙箱策略限制模块导入和内建
    - 属性写入本身不需要额外的守卫

特性：
    - 幂等
    - 备份为 *.bak.v25
    - 修改后 compile() 验证
    - 失败自动回滚

用法：
    python fix_sandbox_runtime_v26.py --dry-run
    python fix_sandbox_runtime_v26.py
"""

import sys
import shutil
import argparse
import traceback
from pathlib import Path
from typing import Tuple, List, Callable

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "infrastructure" / "sandbox_runtime.py"
BACKUP_SUFFIX = ".bak.v25"


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
# Patch 定义
# ============================================================
class Patch:
    def __init__(self, pid: str, name: str, marker: str,
                 old: str, new: str):
        self.pid = pid
        self.name = name
        self.marker = marker
        self.old = old
        self.new = new

    def is_applied(self, content: str) -> bool:
        return self.marker in content

    def apply(self, content: str) -> Tuple[str, bool]:
        count = content.count(self.old)
        if count == 0:
            raise ValueError(
                f"锚点未找到（补丁 {self.pid}: {self.name}）"
            )
        if count > 1:
            raise ValueError(
                f"锚点重复 {count} 次（补丁 {self.pid}: {self.name}）"
            )
        return content.replace(self.old, self.new, 1), True


def build_patches() -> List[Patch]:
    patches = []

    # --------------------------------------------------------
    # 补丁 1: 替换 _write_ 构建逻辑
    # --------------------------------------------------------
    old_1 = "\n".join([
        "    # _write_：属性写入守卫",
        "    try:",
        "        from RestrictedPython.Guards import full_write_guard",
        "        result['_write_'] = full_write_guard",
        "    except ImportError:",
        "        # 降级：允许设置属性（策略由 AST 检查保护）",
        "        class _DefaultWriteGuard:",
        "            def __getattr__(self, name):",
        "                return _allow_write",
        "        result['_write_'] = _DefaultWriteGuard()",
    ])

    new_1 = "\n".join([
        "    # _write_：属性写入守卫（v2.6：改用宽松实现）",
        "    # 说明：",
        "    #   RestrictedPython 的 full_write_guard 要求被赋值对象",
        "    #   具有 __guarded_setattr__ 方法，否则拒绝，导致插件的",
        "    #   self.counter = 0 抛 \"attribute-less object\"。",
        "    #   我们改为自定义的宽松守卫：直接转发 setattr/delattr。",
        "    #   安全性由 AST 检查（禁止危险属性访问）和沙箱策略保证。",
        "    result['_write_'] = _write_guard",
    ])

    patches.append(Patch(
        pid="1",
        name="_build_restricted_globals 使用自定义 _write_guard",
        marker="result['_write_'] = _write_guard",
        old=old_1,
        new=new_1,
    ))

    # --------------------------------------------------------
    # 补丁 2: 添加 _WriteGuard 类与 _write_guard 函数
    # --------------------------------------------------------
    old_2 = "\n".join([
        "def _allow_write(obj):",
        '    """默认属性写入守卫：返回 obj 本身允许赋值（AST 已检查）"""',
        "    return obj",
    ])

    new_2 = "\n".join([
        "def _allow_write(obj):",
        '    """默认属性写入守卫：返回 obj 本身允许赋值（AST 已检查）"""',
        "    return obj",
        "",
        "",
        "class _WriteGuard:",
        '    """',
        "    属性写入守卫（v2.6）。",
        "",
        "    说明：",
        "        RestrictedPython 自带的 full_write_guard 要求被赋值",
        "        对象具有 __guarded_setattr__ 方法，否则拒绝赋值，",
        "        导致插件中常见的 self.counter = 0 抛 TypeError:",
        "        attribute-less object。",
        "",
        "        本类改为直接转发 setattr / delattr。安全性由：",
        "          1. AST 检查（禁止 .__class__ / .__bases__ 等危险",
        "             属性访问）",
        "          2. 沙箱策略（导入 / 内建受限）",
        "        共同保证。",
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

    patches.append(Patch(
        pid="2",
        name="新增 _WriteGuard 与 _write_guard",
        marker="class _WriteGuard:",
        old=old_2,
        new=new_2,
    ))

    return patches


# ============================================================
# 验证与应用
# ============================================================
def validate_python(content: str, filepath: str) -> Tuple[bool, str]:
    try:
        compile(content, filepath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def apply_all(patches: List[Patch],
              content: str,
              dry_run: bool) -> Tuple[str, int, int, int]:
    applied = 0
    skipped = 0
    failed = 0
    result = content

    for patch in patches:
        print()
        print(f"【{patch.pid}】{patch.name}")

        if patch.is_applied(result):
            print_skip("已修复，跳过")
            skipped += 1
            continue

        if dry_run:
            try:
                patch.apply(result)
                print_info("[DRY-RUN] 锚点存在，会修改")
                applied += 1
            except ValueError as e:
                print_fail(f"[DRY-RUN] {e}")
                failed += 1
            continue

        try:
            new_content, _ = patch.apply(result)
            ok, err = validate_python(new_content, str(TARGET))
            if not ok:
                print_fail(f"语法验证失败: {err}")
                failed += 1
                continue
            result = new_content
            print_ok("已应用")
            applied += 1
        except ValueError as e:
            print_fail(str(e))
            failed += 1
        except Exception as e:
            print_fail(f"异常: {e}")
            traceback.print_exc()
            failed += 1

    return result, applied, skipped, failed


# ============================================================
# 主入口
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser(
        description="sandbox_runtime.py v2.6 修复"
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("sandbox_runtime.py v2.6 修复")
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

    patches = build_patches()

    new_content, applied, skipped, failed = apply_all(
        patches, content, args.dry_run
    )

    # 写回
    if not args.dry_run and applied > 0 and failed == 0:
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
                print_info(f"备份已存在: {backup.name}")

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

    # 汇总
    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    print(f"  已应用: {applied}")
    print(f"  已跳过: {skipped}")
    print(f"  失败:   {failed}")

    if args.dry_run:
        print()
        print("⚠ DRY-RUN 模式，未修改文件")
        print("  运行 `python fix_sandbox_runtime_v26.py` 应用")
    elif failed == 0 and applied > 0:
        print()
        print("=" * 60)
        print("✓ 修复完成")
        print("=" * 60)
        print()
        print("下一步:")
        print("  python infrastructure/sandbox_runtime.py")

    return 0 if failed == 0 else 1


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