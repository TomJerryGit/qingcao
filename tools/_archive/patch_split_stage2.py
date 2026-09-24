#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修复 tools/split_stage2.py 的两个 bug
============================================================
1. do_split 中 header + mixin_body 类型错误
2. main 中 import 插入逻辑混乱

用法：
    python tools/patch_split_stage2.py --dry-run
    python tools/patch_split_stage2.py
"""

import sys
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "tools" / "split_stage2.py"


# ============================================================
# Bug 1: do_split 结尾
# ============================================================
OLD_1 = "\n".join([
    "    # 生成 mixin 内容",
    "    mixin_body = []",
    "    for name, info in ordered:",
    "        mixin_body.extend(info['lines'])",
    "",
    "    mixin_content = '\\n'.join(",
    "        header + mixin_body",
    "    ).rstrip() + '\\n'",
])

NEW_1 = "\n".join([
    "    # 生成 mixin 内容",
    "    mixin_body_lines = []",
    "    for name, info in ordered:",
    "        mixin_body_lines.extend(info['lines'])",
    "",
    "    # header 是 str，mixin_body_lines 是 list",
    "    mixin_content = header + '\\n' + '\\n'.join(mixin_body_lines)",
    "    mixin_content = mixin_content.rstrip() + '\\n'",
])


# ============================================================
# Bug 2: main 中 import 插入
# ============================================================
OLD_2 = "\n".join([
    "    # ---- 加 import ----",
    "    imports = [",
    '        "from ui.mixins.file_ops_mixin import FileOpsMixin",',
    '        "from ui.mixins.edit_ops_mixin import EditOpsMixin",',
    "    ]",
    "    pattern2 = re.compile(r'^(class MainWindow\\()', re.MULTILINE)",
    "    for imp in imports:",
    "        if imp in new_source:",
    '            print_skip(f"import 已存在: {imp}")',
    "        else:",
    "            new_source = pattern2.sub(",
    '                f"{imp}\\n\\\\1", new_source, count=1',
    "            )",
    '            print_ok(f"已插入: {imp}")',
])

NEW_2 = "\n".join([
    "    # ---- 加 import ----",
    "    # 先清理可能残留的旧 import（幂等）",
    "    new_source = re.sub(",
    "        r'^from ui\\.mixins\\.file_ops_mixin import FileOpsMixin\\s*\\n',",
    "        '', new_source, flags=re.MULTILINE",
    "    )",
    "    new_source = re.sub(",
    "        r'^from ui\\.mixins\\.edit_ops_mixin import EditOpsMixin\\s*\\n',",
    "        '', new_source, flags=re.MULTILINE",
    "    )",
    "",
    "    # 构造 import 块",
    "    import_block = (",
    '        "from ui.mixins.file_ops_mixin import FileOpsMixin\\n"',
    '        "from ui.mixins.edit_ops_mixin import EditOpsMixin\\n"',
    "    )",
    "",
    "    # 一次性插入到 class MainWindow 之前",
    "    class_pattern = re.compile(",
    "        r'^(class MainWindow\\()', re.MULTILINE",
    "    )",
    "    if import_block.split('\\n')[0] in new_source:",
    '        print_skip("import 已存在")',
    "    else:",
    "        new_source = class_pattern.sub(",
    '            f"{import_block}\\n\\\\1", new_source, count=1',
    "        )",
    '        print_ok("已插入 2 个 import")',
])


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


def main():
    dry_run = '--dry-run' in sys.argv
    no_backup = '--no-backup' in sys.argv

    print_header("修复 tools/split_stage2.py")
    print(f"  目标: {TARGET}")
    print(f"  模式: {'DRY-RUN' if dry_run else '实际修复'}")

    if not TARGET.exists():
        print_fail(f"文件不存在: {TARGET}")
        return 1

    try:
        content = TARGET.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 1

    # ---- 修复 1 ----
    print_header("修复 1: do_split 结尾")
    if NEW_1 in content:
        print_skip("已修复")
    elif OLD_1 in content:
        if dry_run:
            print_ok("[DRY-RUN] 会替换 do_split 结尾")
        else:
            content = content.replace(OLD_1, NEW_1, 1)
            print_ok("已替换 do_split 结尾")
    else:
        print_fail("未找到锚点 (do_split 结尾)")
        print()
        print("  手动检查 tools/split_stage2.py 中:")
        print("    搜索 'mixin_body'")
        print("    应为 'mixin_body = []' 附近")
        return 1

    # ---- 修复 2 ----
    print_header("修复 2: main 中 import 插入")
    if NEW_2 in content:
        print_skip("已修复")
    elif OLD_2 in content:
        if dry_run:
            print_ok("[DRY-RUN] 会替换 import 插入逻辑")
        else:
            content = content.replace(OLD_2, NEW_2, 1)
            print_ok("已替换 import 插入逻辑")
    else:
        print_fail("未找到锚点 (import 插入)")
        print()
        print("  手动检查 tools/split_stage2.py 中:")
        print("    搜索 '# ---- 加 import ----'")
        print("    到 'print_ok(f\"已插入: {imp}\")' 之间")
        return 1

    if dry_run:
        print()
        print("✓ DRY-RUN 完成")
        print("  运行 `python tools\\patch_split_stage2.py` 执行")
        return 0

    # ---- 备份 + 写入 ----
    if not no_backup:
        backup = TARGET.with_suffix(".py.bak.patch")
        try:
            shutil.copy2(TARGET, backup)
            print_ok(f"已备份: {backup.name}")
        except Exception as e:
            print_fail(f"备份失败: {e}")
            return 1

    try:
        TARGET.write_text(content, encoding='utf-8')
        print_ok("已写回")
    except Exception as e:
        print_fail(f"写入失败: {e}")
        return 1

    # ---- 语法验证 ----
    print_header("语法验证")
    ok, err = validate_syntax(TARGET)
    if ok:
        print_ok("tools/split_stage2.py")
    else:
        print_fail(f"语法错误: {err}")
        if not no_backup:
            shutil.copy2(TARGET.with_suffix(".py.bak.patch"), TARGET)
            print_ok("已从备份还原")
        return 1

    print()
    print("=" * 60)
    print("  下一步:")
    print("=" * 60)
    print()
    print("  1. 重新预演: python tools\\split_stage2.py --dry-run")
    print("  2. 实际执行: python tools\\split_stage2.py")
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