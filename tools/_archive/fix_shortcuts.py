#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修复 _build_shortcuts 中与菜单 QAction 重复的快捷键
============================================================
问题:
    同一切能通过 QAction（_build_menus）和 QShortcut（_build_shortcuts）
    绑定了两次，Qt 报 "Ambiguous shortcut overload"。

方案:
    _build_shortcuts 只保留菜单里没有的快捷键:
        - Ctrl+Space    (自动补全)
        - Ctrl+Tab      (下一标签)
        - Ctrl+Shift+Tab(上一标签)

用法:
    python tools/fix_shortcuts.py --dry-run
    python tools/fix_shortcuts.py
"""

import sys
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "ui" / "main_window.py"


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


# 旧块（含所有 22 个快捷键）
OLD_BLOCK = "\n".join([
    '        shortcuts = [',
    '            ("Ctrl+Shift+P", self._show_command_palette),',
    '            ("Ctrl+P", self._show_file_palette),',
    '            # P2-4: 符号跳转改为 Ctrl+Alt+R',
    '            ("Ctrl+Alt+R", self._show_symbol_palette),',
    '            ("Ctrl+G", self._goto_line_dialog),',
    '            ("Ctrl+Shift+T", self._restore_closed_tab),',
    '            ("Ctrl+Shift+D", self._duplicate_line),',
    '            ("Ctrl+Shift+Up", self._move_line_up),',
    '            ("Ctrl+Shift+Down", self._move_line_down),',
    '            ("Ctrl+D", self._select_next_occurrence),',
    '            ("Ctrl+/", self._toggle_comment),',
    '            ("Ctrl+`", self._toggle_console),',
    '            ("Ctrl+Space", self._auto_complete),',
    '            ("F5", self._insert_datetime),',
    '            ("F11", self.toggle_distraction_free),',
    '            ("Shift+F11", self.toggle_fullscreen),',
    '            ("Ctrl+Tab", self._next_tab),',
    '            ("Ctrl+Shift+Tab", self._prev_tab),',
    '            ("Ctrl+W", self._close_current_tab),',
    '            ("Ctrl+Alt+S", self._save_all),',
    '            ("Ctrl+L", self._goto_line_dialog),',
    '            ("Ctrl+Shift+F", self._show_global_search),',
    '            ("Ctrl+Shift+E", self._eval_expression),',
    '        ]',
])


# 新块（仅保留菜单里没有的快捷键）
NEW_BLOCK = "\n".join([
    '        # 注意：以下快捷键中，与菜单 QAction 重复的已移除，',
    '        #       避免 Qt 报 "Ambiguous shortcut overload"。',
    '        #       QAction 的快捷键在 _build_menus 中定义。',
    '        #',
    '        # 这里只保留菜单里没有的快捷键。',
    '        shortcuts = [',
    '            ("Ctrl+Space", self._auto_complete),',
    '            ("Ctrl+Tab", self._next_tab),',
    '            ("Ctrl+Shift+Tab", self._prev_tab),',
    '        ]',
])


def main():
    dry_run = '--dry-run' in sys.argv
    no_backup = '--no-backup' in sys.argv

    print_header("修复 _build_shortcuts 快捷键冲突")
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
    if '("Ctrl+Space", self._auto_complete),' in content and \
       '("Ctrl+Shift+P", self._show_command_palette),' not in content:
        print_skip("已修复")
        return 0

    # 锚点检测
    if OLD_BLOCK not in content:
        print_fail("未找到 _build_shortcuts 的快捷键列表")
        print()
        print("  可能是以下情况之一：")
        print("    1. 快捷键列表已经过修改")
        print("    2. _build_shortcuts 结构与我预期不一致")
        print()
        print("  请手动搜索 'shortcuts = [' 并确认内容")
        return 1

    if dry_run:
        print_ok("[DRY-RUN] 会替换 _build_shortcuts 列表")
        print()
        print("  保留:")
        print("    Ctrl+Space      自动补全")
        print("    Ctrl+Tab        下一标签")
        print("    Ctrl+Shift+Tab  上一标签")
        print()
        print("  移除（与菜单 QAction 重复）:")
        print("    Ctrl+Shift+P, Ctrl+P, Ctrl+Alt+R, Ctrl+G,")
        print("    Ctrl+Shift+T, Ctrl+Shift+D, Ctrl+Shift+Up,")
        print("    Ctrl+Shift+Down, Ctrl+D, Ctrl+/, Ctrl+`,")
        print("    F5, F11, Shift+F11, Ctrl+W, Ctrl+Alt+S,")
        print("    Ctrl+L, Ctrl+Shift+F, Ctrl+Shift+E")
        return 0

    # 备份
    backup = TARGET.with_suffix(".py.bak.shortcuts")
    if not no_backup:
        try:
            shutil.copy2(TARGET, backup)
            print_ok(f"已备份: {backup.name}")
        except Exception as e:
            print_fail(f"备份失败: {e}")
            return 1

    # 替换
    new_content = content.replace(OLD_BLOCK, NEW_BLOCK, 1)

    try:
        TARGET.write_text(new_content, encoding='utf-8')
        print_ok("已替换 _build_shortcuts 列表")
    except Exception as e:
        print_fail(f"写入失败: {e}")
        return 1

    # 语法验证
    ok, err = validate_syntax(TARGET)
    if not ok:
        print_fail(f"语法检查失败: {err}")
        if not no_backup:
            shutil.copy2(backup, TARGET)
            print_fail("已从备份还原")
        return 1

    print_ok("语法验证通过")

    print()
    print("=" * 60)
    print("  下一步:")
    print("=" * 60)
    print()
    print("  python main.py")
    print()
    print("  应该不再出现:")
    print("    QAction::event: Ambiguous shortcut overload: Ctrl+Shift+D")
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