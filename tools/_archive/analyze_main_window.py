#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分析 ui/main_window.py 的结构
============================================================
用 ast 解析 MainWindow 类的所有方法，按功能前缀分类，
为拆分提供数据支撑。

用法：
    python tools/analyze_main_window.py
"""

import ast
import sys
from pathlib import Path
from collections import Counter


ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "ui" / "main_window.py"


def print_header(t):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


def main():
    print_header("分析 ui/main_window.py")

    if not TARGET.exists():
        print(f"[FAIL] 文件不存在: {TARGET}")
        return 1

    try:
        src = TARGET.read_text(encoding='utf-8')
    except Exception as e:
        print(f"[FAIL] 读取失败: {e}")
        return 1

    # 统计行数
    lines = src.split('\n')
    total_lines = len(lines)
    print(f"  总行数: {total_lines}")
    print(f"  文件大小: {TARGET.stat().st_size} 字节")

    # 解析 AST
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        print(f"[FAIL] 语法错误: 行 {e.lineno}: {e.msg}")
        return 1

    # 找 MainWindow 类
    main_window_cls = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            main_window_cls = node
            break

    if main_window_cls is None:
        print("[FAIL] 未找到 MainWindow 类")
        return 1

    # 收集方法
    methods = []
    for node in main_window_cls.body:
        if isinstance(node, ast.FunctionDef):
            # 计算行数
            end = getattr(node, 'end_lineno', node.lineno)
            length = end - node.lineno + 1
            methods.append({
                'name': node.name,
                'line': node.lineno,
                'end': end,
                'length': length,
            })

    print(f"  方法总数: {len(methods)}")
    print()

    # 按前缀分类
    prefix_groups = {
        '__init__':       ['__init__'],
        '_build_*':       [],   # 构建类
        '_create_*':      [],   # 工厂类
        '_add_*':         [],   # 添加类
        '_on_*':          [],   # 回调类
        '_toggle_*':      [],   # 切换类
        '_show_*':        [],   # 显示类
        '_new_* / _open_* / _save_* / _close_*': [],  # 文件操作
        '_update_* / _refresh_*': [],  # 状态更新
        '_sync_*':        [],   # 同步类
        '其他':            [],
    }

    for m in methods:
        n = m['name']
        if n == '__init__':
            prefix_groups['__init__'].append(m)
        elif n.startswith('_build_'):
            prefix_groups['_build_*'].append(m)
        elif n.startswith('_create_'):
            prefix_groups['_create_*'].append(m)
        elif n.startswith('_add_'):
            prefix_groups['_add_*'].append(m)
        elif n.startswith('_on_'):
            prefix_groups['_on_*'].append(m)
        elif n.startswith('_toggle_'):
            prefix_groups['_toggle_*'].append(m)
        elif n.startswith('_show_'):
            prefix_groups['_show_*'].append(m)
        elif any(n.startswith(p) for p in
                 ('_new_', '_open_', '_save_', '_close_', '_reload_',
                  '_restore_closed')):
            prefix_groups['_new_* / _open_* / _save_* / _close_*'].append(m)
        elif any(n.startswith(p) for p in ('_update_', '_refresh_')):
            prefix_groups['_update_* / _refresh_*'].append(m)
        elif n.startswith('_sync_'):
            prefix_groups['_sync_*'].append(m)
        else:
            prefix_groups['其他'].append(m)

    # 输出
    print("=" * 60)
    print("  方法分类")
    print("=" * 60)

    for group, items in prefix_groups.items():
        if not items:
            continue
        total = sum(m['length'] for m in items)
        print()
        print(f"  【{group}】共 {len(items)} 个方法，约 {total} 行")
        items.sort(key=lambda x: -x['length'])
        for m in items[:15]:
            print(f"      L{m['line']:>5d}-{m['end']:<5d} ({m['length']:>3d} 行)  {m['name']}")
        if len(items) > 15:
            print(f"      ... 及其他 {len(items) - 15} 个")

    # 拆分建议
    print()
    print("=" * 60)
    print("  拆分建议（按新文件）")
    print("=" * 60)

    suggestions = [
        ("ui/main_window/status_bar_mixin.py",
         "状态栏构建 + 状态更新",
         ['_build_status_bar', '_update_status_for_editor',
          '_refresh_status', '_update_memory', '_update_git_branch']),
        ("ui/main_window/file_ops_mixin.py",
         "文件新建/打开/保存/关闭",
         ['_new_file', '_open_file', '_open_folder',
          '_save_file', '_save_file_as', '_save_all',
          '_close_current_tab', '_close_all_tabs',
          '_open_startup_files']),
        ("ui/main_window/edit_ops_mixin.py",
         "编辑操作（撤销/重做/复制/粘贴等）",
         ['_undo', '_redo', '_cut', '_copy', '_paste',
          '_select_all', '_duplicate_line', '_move_line_up',
          '_move_line_down', '_toggle_comment']),
        ("ui/main_window/menu_mixin.py",
         "菜单构建",
         ['_build_menus', '_build_panel_menu', '_add_action']),
        ("ui/main_window/dock_mixin.py",
         "面板切换",
         ['_toggle_outline', '_toggle_directory',
          '_toggle_minimap', '_toggle_console', '_toggle_global_search']),
        ("ui/main_window/help_mixin.py",
         "帮助菜单",
         ['_show_shortcuts', '_show_daily_tip', '_about',
          '_show_online_docs', '_show_github']),
    ]

    for path, desc, names in suggestions:
        found = [m for m in methods if m['name'] in names]
        if not found:
            print(f"  [SKIP] {path}（未找到匹配方法）")
            continue
        total = sum(m['length'] for m in found)
        print()
        print(f"  → {path}")
        print(f"     说明: {desc}")
        print(f"     包含: {len(found)} 个方法，约 {total} 行")
        for m in found:
            print(f"       - {m['name']} ({m['length']} 行)")

    print()
    print("=" * 60)
    print("  说明")
    print("=" * 60)
    print()
    print("  - 上表是「建议」不是「必须」，可按实际情况调整")
    print("  - 拆分时需要 mixin 通过 self 访问 MainWindow 的属性")
    print("  - 拆分后必须回归测试全部功能")

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