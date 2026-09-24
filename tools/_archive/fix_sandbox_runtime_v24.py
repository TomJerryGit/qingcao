#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - sandbox_runtime.py v2.4 修复
============================================================
自动应用 4 处修复（对应 v2.3 -> v2.4 升级）：

  A. INTERNAL_ALLOWED_MODULES 补齐 selectors / select
     （socket 依赖链）

  B. 新增 _RESTRICTED_GLOBALS 及 _build_restricted_globals()
     （RestrictedPython 编译后代码所需的辅助函数）

  C. build_safe_builtins 补齐 __build_class__ / type / object 等
     （class Foo: 语句与反射所需）

  D. SandboxRuntime.create_namespace 注入 _RESTRICTED_GLOBALS

特性：
  - 幂等：已修复的项自动跳过
  - 备份：首次修改前备份为 *.bak.v23
  - 验证：修改后 compile() 检查语法
  - 回滚：语法失败自动还原
  - 可单点应用：--only A,B

用法：
    python fix_sandbox_runtime_v24.py --dry-run   # 预演
    python fix_sandbox_runtime_v24.py             # 应用
    python fix_sandbox_runtime_v24.py --no-backup # 不备份
    python fix_sandbox_runtime_v24.py --only B    # 只应用 B
"""

import os
import sys
import shutil
import argparse
import traceback
from pathlib import Path
from typing import List, Optional, Callable, Tuple

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "infrastructure" / "sandbox_runtime.py"
BACKUP_SUFFIX = ".bak.v23"


# ============================================================
# 输出辅助
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
# Patch 类
# ============================================================
class Patch:
    """单个补丁"""

    def __init__(self, pid: str, name: str, marker: str,
                 apply_func: Callable[[str], Tuple[str, bool]]):
        self.pid = pid
        self.name = name
        self.marker = marker
        self.apply_func = apply_func

    def is_applied(self, content: str) -> bool:
        return bool(self.marker) and self.marker in content

    def apply(self, content: str) -> Tuple[str, bool]:
        return self.apply_func(content)


def replace_edit(pid: str, name: str,
                 old: str, new: str, marker: str) -> Patch:
    """构造一个精确替换补丁"""

    def apply_func(content: str) -> Tuple[str, bool]:
        count = content.count(old)
        if count == 0:
            raise ValueError(f"锚点未找到（补丁 {pid}: {name}）")
        if count > 1:
            raise ValueError(
                f"锚点重复出现 {count} 次（补丁 {pid}: {name}）"
            )
        return content.replace(old, new, 1), True

    return Patch(pid, name, marker, apply_func)


# ============================================================
# 补丁定义
# ============================================================
def build_patches() -> List[Patch]:
    patches: List[Patch] = []

    # --------------------------------------------------------
    # 补丁 A: INTERNAL_ALLOWED_MODULES 补齐 selectors / select
    # --------------------------------------------------------
    patch_a_old = "\n".join([
        "    # ---- 网络 setup（SafeFinder 自身需要 import socket）----",
        "    'socket', '_socket',",
        "}",
    ])

    patch_a_new = "\n".join([
        "    # ---- socket 依赖链（v2.4 补齐）----",
        "    'selectors',     # socket 内部会 import 它",
        "    'select',        # 部分平台需要",
        "",
        "    # ---- 网络 setup（SafeFinder 自身需要 import socket）----",
        "    'socket', '_socket',",
        "}",
    ])

    patches.append(replace_edit(
        pid="A",
        name="INTERNAL_ALLOWED_MODULES 补齐 selectors / select",
        old=patch_a_old,
        new=patch_a_new,
        marker="# ---- socket 依赖链（v2.4 补齐）----",
    ))

    # --------------------------------------------------------
    # 补丁 B: 新增 _RESTRICTED_GLOBALS
    # --------------------------------------------------------
    patch_b_old = "\n".join([
        '    print("[SandboxRuntime] 将使用降级模式（受限编译 + 严格白名单）")',
        "",
        "",
        "# ============================================================",
        "# 导入 sandbox_policy",
        "# ============================================================",
    ])

    patch_b_new = "\n".join([
        '    print("[SandboxRuntime] 将使用降级模式（受限编译 + 严格白名单）")',
        "",
        "",
        "# ============================================================",
        "# RestrictedPython 辅助全局（v2.4 新增）",
        "# ============================================================",
        "# 说明：",
        "#   RestrictedPython.compile_restricted() 编译出的字节码会",
        "#   引用这些辅助函数。必须在 exec 时把它们注入到 namespace，",
        "#   否则会出现 NameError: name '_getattr_' is not defined。",
        "#",
        "#   每个函数采用 try/except 逐项导入，以兼容不同版本的",
        "#   RestrictedPython（API 在不同版本间略有差异）。",
        "",
        "",
        "def _allow_write(obj):",
        '    """默认属性写入守卫：返回 obj 本身允许赋值（AST 已检查）"""',
        "    return obj",
        "",
        "",
        "def _build_restricted_globals() -> Dict[str, Any]:",
        '    """构建 RestrictedPython 编译代码所需的辅助全局字典。"""',
        "    result: Dict[str, Any] = {}",
        "    if not _RESTRICTED_PYTHON_OK:",
        "        return result",
        "",
        "    # _getattr_：属性访问守卫",
        "    try:",
        "        from RestrictedPython.Guards import guarded_getattr",
        "        result['_getattr_'] = guarded_getattr",
        "    except ImportError:",
        "        result['_getattr_'] = getattr",
        "",
        "    # _getitem_：下标访问守卫",
        "    try:",
        "        from RestrictedPython.Eval import default_guarded_getitem",
        "        result['_getitem_'] = default_guarded_getitem",
        "    except ImportError:",
        "        try:",
        "            from RestrictedPython.Guards import guarded_getitem",
        "            result['_getitem_'] = guarded_getitem",
        "        except ImportError:",
        "            result['_getitem_'] = lambda obj, key: obj[key]",
        "",
        "    # _getiter_：迭代器守卫",
        "    try:",
        "        from RestrictedPython.Eval import default_guarded_getiter",
        "        result['_getiter_'] = default_guarded_getiter",
        "    except ImportError:",
        "        result['_getiter_'] = iter",
        "",
        "    # _write_：属性写入守卫",
        "    try:",
        "        from RestrictedPython.Guards import full_write_guard",
        "        result['_write_'] = full_write_guard",
        "    except ImportError:",
        "        class _DefaultWriteGuard:",
        "            def __getattr__(self, name):",
        "                return _allow_write",
        "        result['_write_'] = _DefaultWriteGuard()",
        "",
        "    # _inplacevar_：原地运算守卫",
        "    try:",
        "        from RestrictedPython.Guards import guarded_inplacevar",
        "        result['_inplacevar_'] = guarded_inplacevar",
        "    except ImportError:",
        "        try:",
        "            from RestrictedPython.Eval import default_guarded_inplacevar",
        "            result['_inplacevar_'] = default_guarded_inplacevar",
        "        except ImportError:",
        "            pass",
        "",
        "    # _apply_：函数调用守卫",
        "    try:",
        "        from RestrictedPython.Guards import guarded_apply",
        "        result['_apply_'] = guarded_apply",
        "    except ImportError:",
        "        pass",
        "",
        "    # _print_：print 守卫",
        "    try:",
        "        from RestrictedPython.Guards import guarded_print",
        "        result['_print_'] = guarded_print",
        "    except ImportError:",
        "        try:",
        "            from RestrictedPython.print_function import print_",
        "            result['_print_'] = print_",
        "        except ImportError:",
        "            result['_print_'] = print",
        "",
        "    # _unpack_sequence_：序列解包守卫",
        "    try:",
        "        from RestrictedPython.Guards import guarded_unpack_sequence",
        "        result['_unpack_sequence_'] = guarded_unpack_sequence",
        "    except ImportError:",
        "        pass",
        "",
        "    return result",
        "",
        "",
        "# 模块加载时构建一次",
        "_RESTRICTED_GLOBALS: Dict[str, Any] = _build_restricted_globals()",
        "",
        "",
        "# ============================================================",
        "# 导入 sandbox_policy",
        "# ============================================================",
    ])

    patches.append(replace_edit(
        pid="B",
        name="新增 _RESTRICTED_GLOBALS 与 _build_restricted_globals()",
        old=patch_b_old,
        new=patch_b_new,
        marker="_RESTRICTED_GLOBALS: Dict[str, Any] = _build_restricted_globals()",
    ))

    # --------------------------------------------------------
    # 补丁 C: build_safe_builtins 补齐 __build_class__ 等
    # --------------------------------------------------------
    patch_c_old = "\n".join([
        "    # 特殊处理：__import__ 使用受限版本",
        "    result['__import__'] = make_safe_import(policy)",
    ])

    patch_c_new = "\n".join([
        "    # ---- 类构造所需（v2.4 补齐）----",
        "    # class Foo: 语句在字节码层面需要 __build_class__",
        "    if hasattr(_builtins_module, '__build_class__'):",
        "        result['__build_class__'] = _builtins_module.__build_class__",
        "",
        "    # 类和对象基础设施（确保存在，即使白名单遗漏）",
        "    for name in ('object', 'type', 'super',",
        "                 'property', 'staticmethod', 'classmethod'):",
        "        if name not in result and hasattr(_builtins_module, name):",
        "            result[name] = getattr(_builtins_module, name)",
        "",
        "    # 反射（白名单可能遗漏）",
        "    for name in ('isinstance', 'issubclass',",
        "                 'getattr', 'hasattr', 'setattr',",
        "                 'callable', 'repr', 'id', 'hash'):",
        "        if name not in result and hasattr(_builtins_module, name):",
        "            result[name] = getattr(_builtins_module, name)",
        "",
        "    # 特殊处理：__import__ 使用受限版本",
        "    result['__import__'] = make_safe_import(policy)",
    ])

    patches.append(replace_edit(
        pid="C",
        name="build_safe_builtins 补齐 __build_class__ 等",
        old=patch_c_old,
        new=patch_c_new,
        marker="result['__build_class__'] = _builtins_module.__build_class__",
    ))

    # --------------------------------------------------------
    # 补丁 D: create_namespace 注入 _RESTRICTED_GLOBALS
    # --------------------------------------------------------
    patch_d_old = "\n".join([
        "    def create_namespace(self,",
        "                          initial: Optional[Dict] = None) -> Dict:",
        '        """',
        "        创建安全的命名空间。",
        "",
        "        参数:",
        "            initial: 初始值",
        "",
        "        返回:",
        "            命名空间字典（可直接用于 exec）",
        '        """',
        "        ns: Dict[str, Any] = {",
        "            '__builtins__': build_safe_builtins(self.policy),",
        "            '__name__': '__sandbox_plugin__',",
        "            '__doc__': None,",
        "            '__package__': None,",
        "            '__loader__': None,",
        "            '__spec__': None,",
        "        }",
        "",
        "        if initial:",
        "            ns.update(initial)",
        "",
        "        return ns",
    ])

    patch_d_new = "\n".join([
        "    def create_namespace(self,",
        "                          initial: Optional[Dict] = None) -> Dict:",
        '        """',
        "        创建安全的命名空间。",
        "",
        "        修复说明（v2.4）:",
        "            - 在 __builtins__ 之外，额外注入 RestrictedPython",
        "              编译后代码所需的辅助函数（_getattr_ / _getiter_ /",
        "              _getitem_ / _write_ / _inplacevar_ 等）。",
        "              缺少这些会导致任何稍复杂的语句（import、for、",
        "              列表推导、class 定义）抛 NameError。",
        "",
        "        参数:",
        "            initial: 初始值",
        "",
        "        返回:",
        "            命名空间字典（可直接用于 exec）",
        '        """',
        "        ns: Dict[str, Any] = {",
        "            '__builtins__': build_safe_builtins(self.policy),",
        "            '__name__': '__sandbox_plugin__',",
        "            '__doc__': None,",
        "            '__package__': None,",
        "            '__loader__': None,",
        "            '__spec__': None,",
        "        }",
        "",
        "        # v2.4: 注入 RestrictedPython 辅助函数",
        "        if _RESTRICTED_GLOBALS:",
        "            ns.update(_RESTRICTED_GLOBALS)",
        "",
        "        if initial:",
        "            ns.update(initial)",
        "",
        "        return ns",
    ])

    patches.append(replace_edit(
        pid="D",
        name="create_namespace 注入 _RESTRICTED_GLOBALS",
        old=patch_d_old,
        new=patch_d_new,
        marker="# v2.4: 注入 RestrictedPython 辅助函数",
    ))

    return patches


# ============================================================
# 应用逻辑
# ============================================================
def validate_python(content: str, filepath: str) -> Tuple[bool, str]:
    """验证 Python 语法"""
    try:
        compile(content, filepath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def apply_patches(patches: List[Patch],
                  dry_run: bool = False,
                  no_backup: bool = False) -> bool:
    if not TARGET.exists():
        print_fail(f"目标文件不存在: {TARGET}")
        return False

    try:
        original_content = TARGET.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return False

    content = original_content
    file_changed = False
    applied = 0
    skipped = 0
    failed = 0

    for patch in patches:
        print()
        print(f"【{patch.pid}】{patch.name}")

        # 幂等检测
        if patch.is_applied(content):
            print_skip("已修复，跳过")
            skipped += 1
            continue

        if dry_run:
            # dry-run 下也尝试 apply 来检测锚点
            try:
                _, _ = patch.apply(content)
                print_info("[DRY-RUN] 锚点存在，会修改")
                applied += 1
            except ValueError as e:
                print_fail(f"[DRY-RUN] {e}")
                failed += 1
            continue

        try:
            new_content, changed = patch.apply(content)
            if not changed:
                print_skip("无需修改")
                skipped += 1
                continue

            # 语法验证
            ok, err = validate_python(new_content, str(TARGET))
            if not ok:
                print_fail(f"语法验证失败: {err}")
                failed += 1
                continue

            content = new_content
            file_changed = True
            print_ok("已应用")
            applied += 1

        except ValueError as e:
            print_fail(str(e))
            failed += 1
        except Exception as e:
            print_fail(f"异常: {e}")
            traceback.print_exc()
            failed += 1

    # 写回
    if file_changed and not dry_run:
        print()
        print("=" * 60)
        print("写回文件")
        print("=" * 60)

        # 备份
        if not no_backup:
            backup_path = Path(str(TARGET) + BACKUP_SUFFIX)
            if not backup_path.exists():
                try:
                    shutil.copy2(TARGET, backup_path)
                    print_info(f"已备份: {backup_path.name}")
                except Exception as e:
                    print_fail(f"备份失败: {e}")
                    return False
            else:
                print_info(
                    f"备份已存在: {backup_path.name}（保留旧备份，不覆盖）"
                )

        # 写回
        try:
            TARGET.write_text(content, encoding='utf-8', newline='\n')
            print_ok(f"已写回: {TARGET.relative_to(ROOT)}")
        except Exception as e:
            print_fail(f"写回失败: {e}")
            backup_path = Path(str(TARGET) + BACKUP_SUFFIX)
            if backup_path.exists():
                try:
                    shutil.copy2(backup_path, TARGET)
                    print_info("已从备份还原")
                except Exception:
                    pass
            return False

    # 汇总
    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    print(f"  已应用: {applied}")
    print(f"  已跳过: {skipped}")
    print(f"  失败:   {failed}")

    return failed == 0


# ============================================================
# 主入口
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser(
        description="sandbox_runtime.py v2.4 修复脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python fix_sandbox_runtime_v24.py --dry-run   # 预演
  python fix_sandbox_runtime_v24.py             # 应用
  python fix_sandbox_runtime_v24.py --no-backup # 不备份
  python fix_sandbox_runtime_v24.py --only B    # 只应用 B
  python fix_sandbox_runtime_v24.py --only A,B  # 只应用 A,B
        """,
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='预演，不修改文件')
    parser.add_argument('--no-backup', action='store_true',
                        help='不备份原文件')
    parser.add_argument('--only', type=str, default='',
                        help='只应用指定补丁（如 A,B,C,D）')
    args = parser.parse_args()

    print_header("sandbox_runtime.py v2.4 修复")
    print(f"  项目目录: {ROOT}")
    print(f"  目标文件: {TARGET.relative_to(ROOT)}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")
    print(f"  备份:     {'禁用' if args.no_backup else '启用'}")

    if not TARGET.exists():
        print_fail(f"目标文件不存在: {TARGET}")
        return 1

    patches = build_patches()

    # 过滤 --only
    if args.only:
        only_ids = {
            x.strip().upper()
            for x in args.only.split(',') if x.strip()
        }
        patches = [p for p in patches if p.pid in only_ids]

    if not patches:
        print_fail("无待应用补丁")
        return 1

    print(f"  补丁数:   {len(patches)}")
    print()
    print("补丁列表:")
    for p in patches:
        print(f"  [{p.pid}] {p.name}")

    success = apply_patches(patches,
                            dry_run=args.dry_run,
                            no_backup=args.no_backup)

    if args.dry_run:
        print()
        print("⚠ DRY-RUN 模式，未修改文件")
        print("  运行 `python fix_sandbox_runtime_v24.py` 应用")
    elif success:
        print()
        print("=" * 60)
        print("✓ 修复完成")
        print("=" * 60)
        print()
        print("下一步:")
        print("  1. 语法验证:")
        print('     python -c "import ast; ast.parse('
              "open('infrastructure/sandbox_runtime.py', "
              "encoding='utf-8').read()); print('OK')\"")
        print("  2. 运行自测:")
        print("     python infrastructure/sandbox_runtime.py")
        print("  3. 清理备份:")
        print("     del infrastructure\\sandbox_runtime.py.bak.v23")

    return 0 if success else 1


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