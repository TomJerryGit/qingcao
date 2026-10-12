# -*- coding: utf-8 -*-
"""
自动诊断并修复 plugins/ai_assistant/__init__.py 的缩进/隐藏字符问题。
"""
import os
import re

TARGET = "plugins/ai_assistant/__init__.py"


def diagnose(filepath):
    """诊断文件，返回问题列表"""
    issues = []
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    lines = content.split('\n')

    # 1. 检查隐藏字符
    for i, line in enumerate(lines, 1):
        if '\u3000' in line:
            issues.append((i, 'fullwidth_space', line))
        if '\xa0' in line:
            issues.append((i, 'nbsp', line))
        if '\t' in line:
            issues.append((i, 'tab', line))

    # 2. 检查第 283 行附近
    if len(lines) >= 283:
        line_283 = lines[282]  # 0-indexed
        stripped = line_283.lstrip()
        indent = len(line_283) - len(stripped)
        if not stripped.startswith('#'):
            issues.append((283, 'not_comment', line_283))
        elif indent != 4:
            issues.append((283, 'wrong_indent', line_283))

    return issues, lines


def fix(filepath):
    """修复文件"""
    print(f"正在诊断: {filepath}")

    if not os.path.exists(filepath):
        print(f"[FAIL] 文件不存在: {filepath}")
        return False

    issues, lines = diagnose(filepath)

    if not issues:
        print("[OK] 未发现隐藏字符/缩进问题")
        # 尝试编译验证
        try:
            compile('\n'.join(lines), filepath, 'exec')
            print("[OK] 语法编译通过")
            return True
        except SyntaxError as e:
            print(f"[FAIL] 语法错误: line {e.lineno}: {e.msg}")
            print(f"   内容: {lines[e.lineno - 1] if e.lineno else '?'}")
            return False

    print(f"发现 {len(issues)} 个问题:")
    for lineno, kind, line in issues[:20]:
        print(f"  line {lineno}: {kind}")
        print(f"    {repr(line[:80])}")
    if len(issues) > 20:
        print(f"  ... 及其他 {len(issues) - 20} 个")

    # 备份
    backup = filepath + '.bak'
    try:
        with open(backup, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print(f"[OK] 已备份: {backup}")
    except Exception as e:
        print(f"[FAIL] 备份失败: {e}")
        return False

    # 修复：替换隐藏字符为普通字符
    print("\n正在修复...")
    content = '\n'.join(lines)
    content = content.replace('\u3000', ' ')  # 全角空格 -> 半角
    content = content.replace('\xa0', ' ')     # 不换行空格 -> 普通空格

    # 写回
    with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)

    # 再次验证
    print("\n验证修复结果...")
    try:
        new_content = open(filepath, 'r', encoding='utf-8').read()
        compile(new_content, filepath, 'exec')
        print("[OK] 修复成功！语法编译通过")
        return True
    except SyntaxError as e:
        print(f"[FAIL] 仍有语法错误: line {e.lineno}: {e.msg}")

        # 打印错误行附近 5 行
        new_lines = open(filepath, 'r', encoding='utf-8').read().split('\n')
        start = max(0, (e.lineno or 1) - 3)
        end = min(len(new_lines), (e.lineno or 1) + 3)
        print("\n错误附近的内容:")
        for i in range(start, end):
            marker = ">>>" if i + 1 == e.lineno else "   "
            print(f"{marker} {i + 1:4d}: {repr(new_lines[i])}")

        print(f"\n[提示] 已备份原文件到: {backup}")
        print(f"       你可以对比 {backup} 和 {filepath} 手动修复")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("AI 插件文件诊断与修复")
    print("=" * 60)
    print()

    success = fix(TARGET)

    print()
    print("=" * 60)
    if success:
        print("[OK] 修复完成，请重新启动编辑器")
    else:
        print("[FAIL] 修复失败，请把上面的输出贴给我")
    print("=" * 60)