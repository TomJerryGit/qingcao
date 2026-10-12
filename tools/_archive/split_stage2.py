#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
阶段 2 拆分 ui/main_window.py
============================================================
拆出:
    1. FileOpsMixin   -> ui/mixins/file_ops_mixin.py
    2. EditOpsMixin   -> ui/mixins/edit_ops_mixin.py

用法:
    python tools/split_stage2.py --dry-run
    python tools/split_stage2.py

前置:
    阶段 1 已执行（StatusBarMixin 已在 MainWindow 上）
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
FILE_MIXIN = MIXIN_DIR / "file_ops_mixin.py"
EDIT_MIXIN = MIXIN_DIR / "edit_ops_mixin.py"


FILE_OPS_METHODS = [
    "_new_file", "_get_template_for_ext",
    "_open_file", "_open_folder",
    "_save_file", "_save_file_as", "_save_all",
    "_close_current_tab", "_close_all_tabs",
    "_restore_closed_tab", "_open_startup_files",
    "_open_recent_file", "_open_recent_project",
    "open_project", "save_project", "close_project",
    "_new_window",
    "_on_file_opened", "_on_file_saved",
]

EDIT_OPS_METHODS = [
    "_undo", "_redo",
    "_cut", "_copy", "_paste", "_select_all",
    "_duplicate_line",
    "_move_line_up", "_move_line_down",
    "_select_next_occurrence",
    "_toggle_comment",
    "_eval_expression", "_insert_datetime",
    "_to_upper", "_to_lower",
    "_auto_complete",
]


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
    start = node.lineno - 1
    if node.decorator_list:
        start = min(d.lineno for d in node.decorator_list) - 1
    # 前置分节注释
    i = start - 1
    while i >= 0 and source_lines[i].strip().startswith('#'):
        i -= 1
    if i + 1 < start:
        first_comment = source_lines[i + 1].strip()
        if first_comment.startswith('# ===') or \
           first_comment.startswith('# ---'):
            start = i + 1
    end = getattr(node, 'end_lineno', node.lineno)
    # 吞尾部空行
    while end < len(source_lines) and source_lines[end].strip() == '':
        end += 1
    return start, end


def build_mixin(header_lines, methods, source_lines):
    """构造 mixin 文件内容（返回 str）"""
    body = []
    for name, info in methods:
        body.extend(info['lines'])
        body.append("")
    content = "\n".join(header_lines) + "\n\n" + "\n".join(body)
    return content.rstrip() + "\n"


FILE_HEADER = [
    "# -*- coding: utf-8 -*-",
    '"""',
    "青草编辑器 - 文件操作 Mixin",
    "============================",
    "从 ui/main_window.py 拆分出来的文件操作相关方法。",
    '"""',
    "",
    "import os",
    "",
    "from PyQt5.QtWidgets import (",
    "    QFileDialog, QMessageBox, QInputDialog, QDialog,",
    ")",
    "from PyQt5.QtCore import Qt",
    "",
    "",
    "class FileOpsMixin:",
    '    """文件操作 Mixin —— 由 MainWindow 继承"""',
    "",
    "    # 依赖属性: self.tabs, self.central_stack, self.status_bar",
    "    #          self.api, self.prefs, self.session",
]


EDIT_HEADER = [
    "# -*- coding: utf-8 -*-",
    '"""',
    "青草编辑器 - 编辑操作 Mixin",
    "============================",
    "从 ui/main_window.py 拆分出来的编辑相关方法。",
    '"""',
    "",
    "import datetime",
    "",
    "",
    "class EditOpsMixin:",
    '    """编辑操作 Mixin —— 由 MainWindow 继承"""',
    "",
    "    # 依赖属性: self.tabs",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("阶段 2 拆分")
    print(f"  源文件: {MW}")
    print(f"  模式:   {'DRY-RUN' if args.dry_run else '实际拆分'}")

    # --- 前置检查 ---
    print_header("前置检查")
    if not MW.exists():
        print_fail(f"文件不存在: {MW}")
        return 1
    print_ok("main_window.py 存在")

    if FILE_MIXIN.exists() or EDIT_MIXIN.exists():
        print_fail("mixin 文件已存在")
        print_info(f"  - {FILE_MIXIN.name}")
        print_info(f"  - {EDIT_MIXIN.name}")
        print_info("请先删除这两个文件，或从 main_window.py.bak.split2 还原")
        return 1
    print_ok("mixin 文件未创建")

    try:
        source = MW.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 1

    if "StatusBarMixin" not in source:
        print_fail("阶段 1 未完成")
        return 1
    print_ok("阶段 1 已完成")

    source_lines = source.split('\n')

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print_fail(f"语法错误: 行 {e.lineno}: {e.msg}")
        return 1

    main_cls = None
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n.name == "MainWindow":
            main_cls = n
            break
    if main_cls is None:
        print_fail("未找到 MainWindow 类")
        return 1
    print_ok(f"找到 MainWindow 类（行 {main_cls.lineno}）")

    # --- 收集方法 ---
    print_header("扫描方法")

    def collect(names, label):
        found = {}
        for item in main_cls.body:
            if isinstance(item, ast.FunctionDef) and item.name in names:
                start, end = find_method_range(source_lines, item)
                found[item.name] = {
                    'start': start, 'end': end,
                    'lines': source_lines[start:end],
                }
        total = sum(len(v['lines']) for v in found.values())
        print_info(f"  {label}: {len(found)} 个方法, {total} 行")
        return found

    file_found = collect(FILE_OPS_METHODS, "FileOpsMixin")
    edit_found = collect(EDIT_OPS_METHODS, "EditOpsMixin")

    if not file_found and not edit_found:
        print_fail("未找到任何方法")
        return 1

    # --- Dry-run 结束 ---
    if args.dry_run:
        total = sum(len(v['lines']) for v in file_found.values()) + \
                sum(len(v['lines']) for v in edit_found.values())
        print()
        print(f"  DRY-RUN 汇总: 将拆分 {total} 行")
        print()
        print("✓ DRY-RUN 完成，运行 `python tools\\split_stage2.py` 执行")
        return 0

    # --- 备份 ---
    print_header("备份")
    backup = MW.with_suffix(".py.bak.split2")
    try:
        shutil.copy2(MW, backup)
        print_ok(f"已备份: {backup.name}")
    except Exception as e:
        print_fail(f"备份失败: {e}")
        return 1

    try:
        # --- 1. 构造 mixin 内容 ---
        print_header("生成 mixin 文件")

        file_content = build_mixin(
            FILE_HEADER,
            sorted(file_found.items(),
                   key=lambda kv: kv[1]['start']),
            source_lines,
        )
        edit_content = build_mixin(
            EDIT_HEADER,
            sorted(edit_found.items(),
                   key=lambda kv: kv[1]['start']),
            source_lines,
        )

        FILE_MIXIN.write_text(file_content, encoding='utf-8')
        EDIT_MIXIN.write_text(edit_content, encoding='utf-8')
        print_ok(f"已生成: {FILE_MIXIN.name}")
        print_ok(f"已生成: {EDIT_MIXIN.name}")

        # --- 2. 从 main_window.py 删除方法 ---
        print_header("修改 main_window.py")

        to_remove = []
        for info in file_found.values():
            to_remove.append((info['start'], info['end']))
        for info in edit_found.values():
            to_remove.append((info['start'], info['end']))

        # 去重 + 合并重叠
        to_remove.sort()
        merged = []
        for s, e in to_remove:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))

        for s, e in reversed(merged):
            del source_lines[s:e]

        new_source = '\n'.join(source_lines)

        # --- 3. 修改 class 声明 ---
        class_re = re.compile(r'^class MainWindow\(([^)]+)\):',
                              re.MULTILINE)
        m = class_re.search(new_source)
        if not m:
            raise RuntimeError("未找到 class MainWindow 声明")

        bases = m.group(1).strip()
        if 'FileOpsMixin' not in bases:
            new_bases = f"FileOpsMixin, EditOpsMixin, {bases}"
            new_source = class_re.sub(
                f"class MainWindow({new_bases}):",
                new_source, count=1,
            )
            print_ok(f"class 声明已更新")

        # --- 4. 插入 import ---
        # 先清理残留的旧 import（幂等）
        new_source = re.sub(
            r'^from ui\.mixins\.file_ops_mixin import FileOpsMixin\s*\n',
            '', new_source, flags=re.MULTILINE,
        )
        new_source = re.sub(
            r'^from ui\.mixins\.edit_ops_mixin import EditOpsMixin\s*\n',
            '', new_source, flags=re.MULTILINE,
        )

        import_block = (
            "from ui.mixins.file_ops_mixin import FileOpsMixin\n"
            "from ui.mixins.edit_ops_mixin import EditOpsMixin\n"
        )

        # 在 class MainWindow 前一次性插入
        class_pattern = re.compile(r'^class MainWindow\(',
                                   re.MULTILINE)
        new_source = class_pattern.sub(
            import_block + "\nclass MainWindow(",
            new_source, count=1,
        )
        print_ok("已插入 2 个 import")

        # --- 5. 写回 ---
        MW.write_text(new_source, encoding='utf-8')
        print_ok("已写回 main_window.py")

        # --- 6. 语法验证 ---
        print_header("语法验证")
        all_ok = True
        for p in [MW, FILE_MIXIN, EDIT_MIXIN]:
            ok, err = validate_syntax(p)
            if ok:
                print_ok(str(p.relative_to(ROOT)))
            else:
                print_fail(f"{p.name}: {err}")
                all_ok = False

        if not all_ok:
            raise RuntimeError("语法检查失败")

        # --- 7. 统计 ---
        print_header("完成")
        orig = len(source.split('\n'))
        now = len(new_source.split('\n'))
        print(f"  原 main_window.py:    {orig:>5d} 行")
        print(f"  新 main_window.py:    {now:>5d} 行")
        print(f"  已移除:               {orig - now:>5d} 行")
        print(f"  file_ops_mixin.py:    "
              f"{len(file_content.split(chr(10))):>5d} 行")
        print(f"  edit_ops_mixin.py:    "
              f"{len(edit_content.split(chr(10))):>5d} 行")
        print()
        print("  回滚:")
        print(f"    copy ui\\main_window.py.bak.split2 ui\\main_window.py")
        print(f"    del ui\\mixins\\file_ops_mixin.py")
        print(f"    del ui\\mixins\\edit_ops_mixin.py")
        print()

        return 0

    except Exception as e:
        print()
        print_fail(f"拆分失败: {e}")
        traceback.print_exc()
        # 回滚
        try:
            shutil.copy2(backup, MW)
            print_warn("main_window.py 已从备份还原")
        except Exception:
            print_fail("还原失败，请手动执行:")
            print(f"  copy ui\\main_window.py.bak.split2 ui\\main_window.py")
        # 清理 mixin
        for p in [FILE_MIXIN, EDIT_MIXIN]:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass
        return 1


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