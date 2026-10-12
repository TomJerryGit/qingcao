#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
阶段 1 拆分 ui/main_window.py —— 状态栏
============================================================
将以下方法从 MainWindow 迁移到 StatusBarMixin:

    - _build_status_bar
    - _update_status_for_editor
    - _refresh_status
    - _update_memory
    - _update_git_branch
    - _on_encoding_changed
    - _on_eol_changed
    - _on_git_branch_clicked

生成:
    ui/mixins/__init__.py
    ui/mixins/status_bar_mixin.py

修改:
    ui/main_window.py:
        - 删除上述方法
        - 顶部 import StatusBarMixin
        - class MainWindow(QMainWindow) -> class MainWindow(StatusBarMixin, QMainWindow)

特性:
    - 幂等: 已拆分的自动跳过
    - 备份: *.before_split 由用户预先做，本脚本额外备份为 *.bak.split
    - 验证: 拆分后 compile() 检查两个文件语法
    - 回滚: 语法失败自动还原

用法:
    python tools/split_stage1.py --dry-run
    python tools/split_stage1.py
"""

import os
import sys
import re
import shutil
import argparse
import ast
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MW = ROOT / "ui" / "main_window.py"
MIXIN_DIR = ROOT / "ui" / "mixins"
MIXIN_FILE = MIXIN_DIR / "status_bar_mixin.py"
MIXIN_INIT = MIXIN_DIR / "__init__.py"


# 要拆出去的方法
TARGET_METHODS = [
    "_build_status_bar",
    "_update_status_for_editor",
    "_refresh_status",
    "_update_memory",
    "_update_git_branch",
    "_on_encoding_changed",
    "_on_eol_changed",
    "_on_git_branch_clicked",
]


# ============================================================
# 工具函数
# ============================================================
def print_header(t):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


def print_ok(m):
    print("  [OK]   " + m)


def print_skip(m):
    print("  [SKIP] " + m)


def print_warn(m):
    print("  [WARN] " + m)


def print_fail(m):
    print("  [FAIL] " + m)


def print_info(m):
    print("  [INFO] " + m)


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


def find_method_range(source_lines, node):
    """
    找方法的完整行范围 [start, end)，包含:
    - 前置装饰器
    - 前置分节注释 (如 # ======)
    - 后置空行
    """
    # 起始行（0-indexed）
    start = node.lineno - 1

    # 装饰器
    if node.decorator_list:
        start = min(d.lineno for d in node.decorator_list) - 1

    # 向前扫：把紧邻的分节注释也带走
    i = start - 1
    while i >= 0 and source_lines[i].strip().startswith('#'):
        i -= 1
    if i + 1 < start:
        # i+1 是第一行注释
        first_comment = source_lines[i + 1].strip()
        if (first_comment.startswith('# ===') or
                first_comment.startswith('# ---')):
            start = i + 1

    # 结束行（0-indexed exclusive）
    end = node.end_lineno if hasattr(node, 'end_lineno') else node.lineno

    # 向后吞空行
    while end < len(source_lines) and source_lines[end].strip() == '':
        end += 1

    return start, end


# ============================================================
# 主逻辑
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="阶段 1: 拆分 ui/main_window.py 的状态栏部分"
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("阶段 1 拆分: ui/main_window.py -> StatusBarMixin")
    print(f"  源文件:   {MW}")
    print(f"  Mixin:    {MIXIN_FILE}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际拆分'}")

    # ---- 前置检查 ----
    print_header("前置检查")

    if not MW.exists():
        print_fail(f"文件不存在: {MW}")
        return 1
    print_ok("main_window.py 存在")

    if MIXIN_FILE.exists():
        print_skip(f"mixin 已存在: {MIXIN_FILE}")
        print_skip("如需重新拆分，请先删除该文件")
        return 0
    print_ok("mixin 文件未创建（可安全执行）")

    # ---- 读取源码 ----
    try:
        with open(MW, 'r', encoding='utf-8') as f:
            source = f.read()
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 1

    source_lines = source.split('\n')

    # ---- 解析 AST ----
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print_fail(f"语法错误: 行 {e.lineno}: {e.msg}")
        return 1

    # ---- 找 MainWindow 类 ----
    main_window_cls = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            main_window_cls = node
            break

    if main_window_cls is None:
        print_fail("未找到 MainWindow 类")
        return 1
    print_ok(f"找到 MainWindow 类（行 {main_window_cls.lineno}）")

    # ---- 找目标方法 ----
    print_header("扫描目标方法")
    found = {}
    for item in main_window_cls.body:
        if isinstance(item, ast.FunctionDef) and item.name in TARGET_METHODS:
            start, end = find_method_range(source_lines, item)
            found[item.name] = {
                'start': start,
                'end': end,
                'lines': source_lines[start:end],
                'node': item,
            }
            print(f"  ✓ {item.name:35s} 行 {start+1:>5d}-{end:<5d} ({end-start:>3d} 行)")

    missing = [m for m in TARGET_METHODS if m not in found]
    if missing:
        print()
        print_warn(f"未找到 {len(missing)} 个方法:")
        for m in missing:
            print(f"      - {m}")
        print()
        print_info("继续执行，只拆分已找到的方法")

    if not found:
        print_fail("未找到任何目标方法，终止")
        return 1

    print()
    print_info(f"将拆分 {len(found)} 个方法，共 "
               f"{sum(len(v['lines']) for v in found.values())} 行")

    if args.dry_run:
        print()
        print("✓ DRY-RUN 完成")
        print("  运行 `python tools/split_stage1.py` 执行")
        return 0

    # ---- 备份 ----
    backup = MW.with_suffix(".py.bak.split")
    if not args.no_backup:
        try:
            shutil.copy2(MW, backup)
            print_ok(f"已备份: {backup.name}")
        except Exception as e:
            print_fail(f"备份失败: {e}")
            return 1

    # ---- 收集方法源码（保持原顺序）----
    ordered = sorted(found.items(), key=lambda kv: kv[1]['start'])

    # ---- 生成 mixin 文件 ----
    print_header("生成 mixin")

    mixin_header = [
        "# -*- coding: utf-8 -*-",
        '"""',
        "青草编辑器 - 状态栏 Mixin",
        "============================",
        "从 ui/main_window.py 拆分出来的状态栏功能。",
        "",
        "包含:",
        "    - _build_status_bar     构建状态栏",
        "    - _update_status_for_editor  更新状态栏（当前文件信息）",
        "    - _refresh_status       定时刷新",
        "    - _update_memory        内存占用显示",
        "    - _update_git_branch    Git 分支显示",
        "    - _on_encoding_changed  编码切换回调",
        "    - _on_eol_changed       行尾符切换回调",
        "    - _on_git_branch_clicked  Git 分支点击回调",
        '"""',
        "",
        "import os",
        "import subprocess",
        "",
        "from PyQt5.QtWidgets import (",
        "    QStatusBar, QLabel, QWidget, QSizePolicy, QMessageBox",
        ")",
        "from PyQt5.QtCore import Qt, QTimer",
        "",
        "",
        "# 从 main_window.py 复制的常量",
        "STATUS_REFRESH_INTERVAL = 3000",
        "MEMORY_WARN_THRESHOLD = 800",
        "",
        "",
        "class StatusBarMixin:",
        '    """状态栏 Mixin —— 由 MainWindow 继承"""',
        "",
        "    # 属性（由 MainWindow.__init__ 创建）:",
        "    #   self._status_timer",
        "    #   self.status_bar, self.cursor_label, self.encoding_label,",
        "    #   self.eol_label, self.mode_label, self.selection_label,",
        "    #   self.lsp_status_label, self.git_branch_label,",
        "    #   self.rec_label, self.mem_label",
        "",
    ]

    mixin_body = []
    for name, info in ordered:
        # 原样搬运方法的行（缩进已经是 4 空格）
        mixin_body.extend(info['lines'])
        mixin_body.append("")

    mixin_content = '\n'.join(mixin_header + mixin_body).rstrip() + '\n'

    # 写 mixin
    try:
        MIXIN_DIR.mkdir(parents=True, exist_ok=True)
        with open(MIXIN_INIT, 'w', encoding='utf-8', newline='\n') as f:
            f.write(
                "# -*- coding: utf-8 -*-\n"
                '"""青草编辑器 - Mixins 包"""\n'
            )
        with open(MIXIN_FILE, 'w', encoding='utf-8', newline='\n') as f:
            f.write(mixin_content)
        print_ok(f"已生成: {MIXIN_DIR.relative_to(ROOT)}\\__init__.py")
        print_ok(f"已生成: {MIXIN_FILE.relative_to(ROOT)}")
    except Exception as e:
        print_fail(f"生成失败: {e}")
        return 1

    # ---- 从 main_window.py 删除这些方法 ----
    print_header("修改 main_window.py")

    # 从后往前删，避免行号偏移
    to_remove = sorted(found.values(), key=lambda v: -v['start'])
    for info in to_remove:
        del source_lines[info['start']:info['end']]

    new_source = '\n'.join(source_lines)

    # ---- 修改 class 声明 ----
    # class MainWindow(QMainWindow) -> class MainWindow(StatusBarMixin, QMainWindow)
    pattern = re.compile(r'^class MainWindow\(([^)]+)\):', re.MULTILINE)
    match = pattern.search(new_source)
    if not match:
        print_fail("未找到 class MainWindow 声明")
        if not args.no_backup:
            shutil.copy2(backup, MW)
            print_warn("已从备份还原")
        return 1

    bases = match.group(1).strip()
    if 'StatusBarMixin' in bases:
        print_skip("class 声明已包含 StatusBarMixin")
    else:
        new_bases = f"StatusBarMixin, {bases}"
        new_source = pattern.sub(
            f"class MainWindow({new_bases}):",
            new_source, count=1
        )
        print_ok(f"class 声明已更新: MainWindow({new_bases})")

    # ---- 加 import ----
    import_line = "from ui.mixins.status_bar_mixin import StatusBarMixin"
    if import_line in new_source:
        print_skip("import 已存在")
    else:
        # 在 "class MainWindow" 之前插入
        pattern2 = re.compile(r'^(class MainWindow\()', re.MULTILINE)
        new_source = pattern2.sub(
            f"{import_line}\n\n\\1",
            new_source, count=1
        )
        print_ok(f"已插入: {import_line}")

    # ---- 写回 ----
    try:
        with open(MW, 'w', encoding='utf-8', newline='\n') as f:
            f.write(new_source)
        print_ok("已写回 main_window.py")
    except Exception as e:
        print_fail(f"写回失败: {e}")
        if not args.no_backup:
            shutil.copy2(backup, MW)
            print_warn("已从备份还原")
        return 1

    # ---- 语法验证 ----
    print_header("语法验证")

    ok1, err1 = validate_syntax(MW)
    if ok1:
        print_ok(f"main_window.py")
    else:
        print_fail(f"main_window.py: {err1}")
        if not args.no_backup:
            shutil.copy2(backup, MW)
            try:
                MIXIN_FILE.unlink()
                MIXIN_INIT.unlink()
                MIXIN_DIR.rmdir()
            except Exception:
                pass
            print_warn("已从备份还原，mixin 已清理")
        return 1

    ok2, err2 = validate_syntax(MIXIN_FILE)
    if ok2:
        print_ok(f"status_bar_mixin.py")
    else:
        print_fail(f"status_bar_mixin.py: {err2}")
        if not args.no_backup:
            shutil.copy2(backup, MW)
            print_warn("main_window.py 已还原，请手动检查 mixin")
        return 1

    # ---- 行数统计 ----
    print_header("行数统计")
    new_lines = len(new_source.split('\n'))
    original_lines = len(source.split('\n'))
    removed = original_lines - new_lines
    print(f"  原 main_window.py:  {original_lines:>5d} 行")
    print(f"  新 main_window.py:  {new_lines:>5d} 行")
    print(f"  已移除:             {removed:>5d} 行")
    print(f"  新 mixin:           {len(mixin_content.split(chr(10))):>5d} 行")

    # ---- 完成 ----
    print_header("完成")
    print_ok("阶段 1 拆分成功")
    print()
    print("  下一步:")
    print("    1. 启动编辑器: python main.py")
    print("    2. 验证状态栏: 编码/行尾符/Git 分支可点击")
    print("    3. 观察启动日志无异常")
    print()
    print("  回滚:")
    print(f"    copy ui\\main_window.py.bak.split ui\\main_window.py")
    print(f"    rmdir /s /q ui\\mixins")
    print()
    print("  如确认无误，可删除备份:")
    print(f"    del ui\\main_window.py.before_split")
    print(f"    del ui\\main_window.py.bak.split")

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