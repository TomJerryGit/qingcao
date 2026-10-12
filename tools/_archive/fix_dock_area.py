#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - 修复 addDockWidget 的 area 参数类型
============================================================
修复 QMainWindow::addDockWidget: invalid 'area' argument 警告。

问题：
    PyQt5 5.15+ 要求 addDockWidget 的第二个参数必须是
    Qt.DockWidgetArea 枚举，传入裸 int 会触发 Qt 内部警告。

涉及 5 处：
    1. app/session.py            _restore_docks
    2. plugins/todo_panel/        show_panel
    3. plugins/markdown_preview/  toggle_preview
    4. plugins/wordcount/         show_panel
    5. plugins/logtail/           show_panel

用法:
    python fix_dock_area.py --dry-run
    python fix_dock_area.py
"""

import sys
import shutil
import argparse
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.dock"


def print_header(t):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


def print_ok(m):
    print(f"  [OK]   {m}")


def print_skip(m):
    print(f"  [SKIP] {m}")


def print_fail(m):
    print(f"  [FAIL] {m}")


def print_info(m):
    print(f"  [INFO] {m}")


# ============================================================
# 修复定义
# ============================================================
FIXES = [
    # ---- 1. session.py ----
    {
        "id": "1",
        "file": "app/session.py",
        "name": "session._restore_docks 使用显式 area 映射",
        "old": '''        try:
            for dock in main_window.findChildren(QDockWidget):
                name = dock.objectName() or dock.windowTitle()
                info = docks_data.get(name)
                if not info:
                    continue

                try:
                    if info.get('floating'):
                        dock.setFloating(True)
                    else:
                        area = Qt.DockWidgetArea(info.get('area', 2))
                        main_window.addDockWidget(area, dock)
                    dock.setVisible(info.get('visible', True))
                except Exception:
                    pass
        except Exception as e:
            print(f"[Session] 恢复面板失败: {e}")''',
        "new": '''        # area 值映射（PyQt5 5.15+ 要求必须是 Qt.DockWidgetArea 枚举）
        AREA_MAP = {
            1: Qt.LeftDockWidgetArea,
            2: Qt.RightDockWidgetArea,
            4: Qt.TopDockWidgetArea,
            8: Qt.BottomDockWidgetArea,
        }

        try:
            for dock in main_window.findChildren(QDockWidget):
                name = dock.objectName() or dock.windowTitle()
                info = docks_data.get(name)
                if not info:
                    continue

                try:
                    if info.get('floating'):
                        dock.setFloating(True)
                    else:
                        area_value = info.get('area', 2)
                        area = AREA_MAP.get(
                            area_value, Qt.RightDockWidgetArea
                        )
                        main_window.addDockWidget(area, dock)
                    dock.setVisible(info.get('visible', True))
                except Exception:
                    pass
        except Exception as e:
            print(f"[Session] 恢复面板失败: {e}")''',
        "marker": "AREA_MAP = {",
    },

    # ---- 2. todo_panel ----
    {
        "id": "2",
        "file": "plugins/todo_panel/__init__.py",
        "name": "todo_panel 使用 Qt.BottomDockWidgetArea",
        "old": '''    def show_panel(self):
        if not self._panel.isVisible():
            self.api.win.addDockWidget(8, self._panel)
        self._panel.setVisible(True)
        self._panel.raise_()''',
        "new": '''    def show_panel(self):
        # 修复: 使用 Qt 枚举而非裸 int
        if not self._panel.isVisible():
            self.api.win.addDockWidget(
                Qt.BottomDockWidgetArea, self._panel
            )
        self._panel.setVisible(True)
        self._panel.raise_()''',
        "marker": "Qt.BottomDockWidgetArea, self._panel",
    },

    # ---- 3. markdown_preview ----
    {
        "id": "3",
        "file": "plugins/markdown_preview/__init__.py",
        "name": "markdown_preview 使用 Qt.RightDockWidgetArea",
        "old": '''        if not self._panel:
            self._panel = MarkdownPanel(self.api.win)
            self.api.win.addDockWidget(2, self._panel)  # RightDockWidgetArea''',
        "new": '''        if not self._panel:
            self._panel = MarkdownPanel(self.api.win)
            # 修复: 使用 Qt 枚举而非裸 int
            self.api.win.addDockWidget(
                Qt.RightDockWidgetArea, self._panel
            )''',
        "marker": "Qt.RightDockWidgetArea, self._panel",
    },

    # ---- 4. wordcount ----
    {
        "id": "4",
        "file": "plugins/wordcount/__init__.py",
        "name": "wordcount 使用 Qt.RightDockWidgetArea",
        "old": '''    def show_panel(self):
        if not self._panel.isVisible():
            self.api.win.addDockWidget(2, self._panel)
        self._panel.setVisible(True)
        self._panel.raise_()
        self._panel.refresh()''',
        "new": '''    def show_panel(self):
        # 修复: 使用 Qt 枚举而非裸 int
        if not self._panel.isVisible():
            self.api.win.addDockWidget(
                Qt.RightDockWidgetArea, self._panel
            )
        self._panel.setVisible(True)
        self._panel.raise_()
        self._panel.refresh()''',
        "marker": "Qt.RightDockWidgetArea, self._panel",
    },

    # ---- 5. logtail ----
    {
        "id": "5",
        "file": "plugins/logtail/__init__.py",
        "name": "logtail 使用 Qt.BottomDockWidgetArea",
        "old": '''    def show_panel(self):
        """显示面板"""
        if not self._panel:
            self._panel = LogTailPanel(self.api.win)
            self.api.win.addDockWidget(
                self.api.win.qt.Qt.BottomDockWidgetArea
                if hasattr(self.api.win, 'qt') else 8,
                self._panel
            )
        self._panel.show()
        self._panel.raise_()''',
        "new": '''    def show_panel(self):
        """显示面板"""
        if not self._panel:
            self._panel = LogTailPanel(self.api.win)
            # 修复: 使用 Qt 枚举而非裸 int
            self.api.win.addDockWidget(
                Qt.BottomDockWidgetArea, self._panel
            )
        self._panel.show()
        self._panel.raise_()''',
        "marker": "Qt.BottomDockWidgetArea, self._panel",
    },
]


# ============================================================
# 应用逻辑
# ============================================================
def ensure_qt_import(content: str, filepath: str) -> Tuple[str, bool]:
    """
    确保文件有 `from PyQt5.QtCore import Qt` 导入。

    返回: (新内容, 是否变更)
    """
    # 已有导入？
    if 'from PyQt5.QtCore import' in content and 'Qt' in content.split(
        'from PyQt5.QtCore import', 1
    )[1].split('\n', 1)[0]:
        return content, False

    # 检查是否有其他方式导入
    if 'import Qt' in content:
        return content, False

    # 简单检查：内容里是否已使用 Qt.
    if 'Qt.' not in content:
        return content, False

    # 找 from PyQt5.QtCore import ... 行，追加 Qt
    import re
    pattern = re.compile(
        r'^from PyQt5\.QtCore import (.+)$',
        re.MULTILINE,
    )
    m = pattern.search(content)
    if m:
        existing = m.group(1)
        if 'Qt' not in [x.strip() for x in existing.split(',')]:
            new_line = f"from PyQt5.QtCore import {existing}, Qt"
            return pattern.sub(new_line, content, count=1), True
        return content, False

    # 没有 QtCore 导入，插入到第一个非注释、非编码声明行之后
    lines = content.split('\n')
    insert_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (not stripped or
                stripped.startswith('#') or
                stripped.startswith('"""') or
                stripped.startswith("'''")):
            insert_idx = i + 1
            continue
        # 遇到第一个真正的语句（如 import）
        if stripped.startswith(('import ', 'from ')):
            insert_idx = i
            break
        insert_idx = i
        break

    lines.insert(insert_idx, "from PyQt5.QtCore import Qt")
    return '\n'.join(lines), True


def apply_fix(fix, dry_run=False, no_backup=False):
    """应用单个修复"""
    filepath = ROOT / fix['file']
    if not filepath.exists():
        print_fail(f"[{fix['id']}] {fix['file']} 不存在")
        return False

    try:
        content = filepath.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"[{fix['id']}] 读取失败: {e}")
        return False

    # 幂等检测
    if fix['marker'] in content:
        print_skip(f"[{fix['id']}] {fix['name']}（已应用）")
        return None  # 表示已跳过

    if fix['old'] not in content:
        print_fail(f"[{fix['id']}] {fix['name']}：锚点未找到")
        return False

    if dry_run:
        print_info(f"[{fix['id']}] [DRY-RUN] {fix['name']}")
        return True

    # 应用
    new_content = content.replace(fix['old'], fix['new'], 1)

    # 确保 Qt 导入
    if fix['file'].endswith('.py'):
        new_content, added_import = ensure_qt_import(
            new_content, str(filepath)
        )
        if added_import:
            print_info(f"[{fix['id']}] 已添加 `from PyQt5.QtCore import Qt`")

    # 语法验证
    if fix['file'].endswith('.py'):
        try:
            compile(new_content, str(filepath), 'exec')
        except SyntaxError as e:
            print_fail(
                f"[{fix['id']}] 语法错误: line {e.lineno}: {e.msg}"
            )
            return False

    # 备份
    if not no_backup:
        backup = Path(str(filepath) + BACKUP_SUFFIX)
        if not backup.exists():
            try:
                shutil.copy2(filepath, backup)
            except Exception:
                pass

    # 写回
    filepath.write_text(new_content, encoding='utf-8', newline='\n')
    print_ok(f"[{fix['id']}] {fix['name']}")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("修复 addDockWidget 的 area 参数类型")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际修复'}")
    print(f"  备份:     {'禁用' if args.no_backup else '启用'}")
    print()

    applied = 0
    skipped = 0
    failed = 0

    for fix in FIXES:
        print(f"【{fix['id']}】{fix['file']}")
        result = apply_fix(fix,
                           dry_run=args.dry_run,
                           no_backup=args.no_backup)
        if result is True:
            applied += 1
        elif result is None:
            skipped += 1
        else:
            failed += 1
        print()

    # 汇总
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    print(f"  已应用: {applied}")
    print(f"  已跳过: {skipped}")
    print(f"  失败:   {failed}")

    if args.dry_run:
        print()
        print("⚠ DRY-RUN 模式，未修改文件")
        print("  运行 `python fix_dock_area.py` 应用")

    return 0 if failed == 0 else 1


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