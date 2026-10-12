#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
升级 health_check.py —— 智能跳过注释/兼容分支
============================================================
旧逻辑：只要字符串里出现 .prov / .enc 就报
新逻辑：
    - 跳过注释行（以 # 开头）
    - 跳过 hasattr / getattr 兼容检查
    - 只报『直接访问』和『赋值』

用法：
    python tools/patch_health_check.py --dry-run
    python tools/patch_health_check.py
"""

import sys
import re
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


# 新的 check_deprecated_api 函数（智能识别）
NEW_FUNC = "\n".join([
    'def check_deprecated_api(py_files):',
    '    print_header("检查 5: Deprecated API 使用")',
    '',
    '    # 智能识别：跳过注释和 hasattr/getattr 兼容检查',
    '    pattern_prov = re.compile(r\'\\.\\bprov\\b\')',
    '    pattern_enc = re.compile(r\'\\.\\benc\\b(?!oding)\')',
    '',
    '    findings = []',
    '',
    '    for f in py_files:',
    '        try:',
    "            with open(f, 'r', encoding='utf-8', errors='replace') as fh:",
    '                lines = fh.readlines()',
    '        except Exception:',
    '            continue',
    '',
    '        for i, line in enumerate(lines, 1):',
    '            if not (pattern_prov.search(line) or pattern_enc.search(line)):',
    '                continue',
    '',
    '            stripped = line.strip()',
    '',
    '            # 跳过注释',
    "            if stripped.startswith('#'):",
    '                continue',
    '',
    '            # 跳过 hasattr / getattr 兼容检查',
    "            if 'hasattr(' in line or 'getattr(' in line:",
    '                continue',
    '',
    '            # 判断类别',
    '            if pattern_prov.search(line):',
    '                desc = "proxy.prov / editor.prov"',
    '            else:',
    '                desc = "document.enc"',
    '',
    '            findings.append((f, i, desc))',
    '',
    '    if not findings:',
    '        print_ok("未发现直接访问 deprecated API")',
    '        return 0',
    '',
    '    print_warn(f"发现 {len(findings)} 处直接访问:")',
    '    for f, i, desc in findings[:15]:',
    '        rel = f.relative_to(ROOT) if hasattr(f, "relative_to") else str(f)',
    '        print(f"      {rel}:{i}")',
    '        print(f"          → {desc}")',
    '',
    '    if len(findings) > 15:',
    '        print(f"      ... 及其他 {len(findings) - 15} 处")',
    '',
    '    print()',
    '    print_info("提示: .prov / .enc 已有别名，不会崩")',
    '',
    '    return len(findings)',
    '',
])


def main():
    dry_run = '--dry-run' in sys.argv
    no_backup = '--no-backup' in sys.argv

    print_header("升级 health_check.py")
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

    # 幂等检测
    if '智能识别：跳过注释' in content:
        print_skip("已升级")
        return 0

    # 用正则找出旧的 check_deprecated_api 函数
    # 匹配: def check_deprecated_api(...) 到下一个 def 或文件末尾
    pattern = re.compile(
        r'^def check_deprecated_api\([^)]*\):.*?(?=^def |\Z)',
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if not match:
        print_fail("未找到 check_deprecated_api 函数")
        return 1

    if dry_run:
        print_ok("[DRY-RUN] 会替换 check_deprecated_api 函数")
        print()
        print("  新版本特点:")
        print("    - 跳过注释行（# 开头）")
        print("    - 跳过 hasattr / getattr 兼容检查")
        print("    - 只报『直接访问』")
        return 0

    # 备份
    if not no_backup:
        backup = TARGET.with_suffix(".py.bak.patch")
        try:
            shutil.copy2(TARGET, backup)
            print_ok(f"已备份: {backup.name}")
        except Exception as e:
            print_fail(f"备份失败: {e}")
            return 1

    # 替换
    new_content = content[:match.start()] + NEW_FUNC + content[match.end():]

    try:
        TARGET.write_text(new_content, encoding='utf-8')
        print_ok("已替换 check_deprecated_api")
    except Exception as e:
        print_fail(f"写入失败: {e}")
        return 1

    # 语法验证
    ok, err = validate_syntax(TARGET)
    if not ok:
        print_fail(f"语法错误: {err}")
        if not no_backup:
            shutil.copy2(backup, TARGET)
            print_fail("已从备份还原")
        return 1

    print_ok("语法验证通过")
    print()
    print("  下一步: python tools\\qingcao.py health")
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