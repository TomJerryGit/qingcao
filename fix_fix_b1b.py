#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修复 fix_b1b.py 的两处问题：
  1. END_PATTERN 放宽正则
  2. Step 1 失败后中止
"""
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "fix_b1b.py"


def main():
    if not TARGET.exists():
        print(f"[FAIL] 未找到 {TARGET}")
        return 1

    # 备份
    bak = Path(str(TARGET) + ".bak")
    if not bak.exists():
        shutil.copy2(TARGET, bak)
        print(f"[OK]   已备份: {bak.name}")

    content = TARGET.read_text(encoding='utf-8')

    # ---- 修改 1: END_PATTERN ----
    old_pattern = r"END_PATTERN = re.compile(r'^class EventHistory\(', re.MULTILINE)"
    new_pattern = (
        r"# \b 匹配单词边界，既能匹配 'class EventHistory:' 也能匹配\n"
        r"# 'class EventHistory(...)'，同时避免匹配到 EventHistoryFoo\n"
        r"END_PATTERN = re.compile(r'^class EventHistory\b', re.MULTILINE)"
    )

    if old_pattern not in content:
        if "r'^class EventHistory\\b'" in content:
            print("[SKIP] END_PATTERN 已是新版本")
        else:
            print("[FAIL] 未找到 END_PATTERN 旧代码")
            return 1
    else:
        content = content.replace(old_pattern, new_pattern, 1)
        print("[OK]   END_PATTERN 已修改")

    # ---- 修改 2: Step 1 失败中止 ----
    old_flow = (
        'if args.dry_run:\n'
        '        print()\n'
        '        print_info("[DRY-RUN] 完成，未修改任何文件")\n'
        '        print_info("去掉 --dry-run 即可应用")\n'
        '        return 0\n'
        '\n'
        '    print_header("Step 2: 加身份等价测试")'
    )
    new_flow = (
        'if args.dry_run:\n'
        '        print()\n'
        '        print_info("[DRY-RUN] 完成，未修改任何文件")\n'
        '        print_info("去掉 --dry-run 即可应用")\n'
        '        return 0\n'
        '\n'
        '    # 新增：Step 1 失败则中止\n'
        '    if r1 == \'failed\':\n'
        '        print()\n'
        '        print_fail("Step 1 失败，跳过 Step 2")\n'
        '        return 1\n'
        '\n'
        '    print_header("Step 2: 加身份等价测试")'
    )

    if old_flow not in content:
        print("[WARN] 未找到 Step 1/2 之间的代码块（可能已修改过）")
    else:
        content = content.replace(old_flow, new_flow, 1)
        print("[OK]   Step 1 失败中止逻辑已添加")

    # 语法验证
    try:
        compile(content, str(TARGET), 'exec')
    except SyntaxError as e:
        print(f"[FAIL] 语法错误: line {e.lineno}: {e.msg}")
        return 1

    TARGET.write_text(content, encoding='utf-8', newline='\n')
    print()
    print("[OK]   修复完成")
    print()
    print("下一步:")
    print("  python fix_b1b.py --dry-run    # 预演")
    print("  python fix_b1b.py              # 应用")
    print("  python tests/run_all.py        # 验证")
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())