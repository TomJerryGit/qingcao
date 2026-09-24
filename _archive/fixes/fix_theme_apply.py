#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
主题切换根本性修复
==============================
根因:
    themes/*.json 里没有 "qss" 字段，而 main_window.py 的
    _apply_theme_by_name 只在 `if theme.qss:` 时才 setStyleSheet，
    导致 QSS 从未被应用。

    ThemeLoader.apply_qss() 本来有"从 colors 生成 QSS"的回退逻辑，
    但 _apply_theme_by_name 没调用它。

修复:
    1. _apply_theme_by_name 改调 loader.apply_qss()
    2. 菜单项显示 display_name（晨曦）而不是文件名（light_clean）

用法:
    python fix_theme_apply.py --dry-run
    python fix_theme_apply.py
"""

import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.themeapply"


def print_header(t): print(f"\n{'=' * 60}\n{t}\n{'=' * 60}")
def print_ok(m):   print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")


def backup(path: Path) -> bool:
    bak = Path(str(path) + BACKUP_SUFFIX)
    if bak.exists():
        return True
    try:
        shutil.copy2(path, bak)
        print_info(f"已备份: {bak.name}")
        return True
    except Exception as e:
        print_fail(f"备份失败: {e}")
        return False


def write_back(path: Path, content: str, no_backup: bool) -> bool:
    if not no_backup and not backup(path):
        return False
    try:
        path.write_text(content, encoding='utf-8', newline='\n')
        return True
    except Exception as e:
        print_fail(f"写回失败: {e}")
        return False


def validate_python(content: str, filepath: str) -> Tuple[bool, str]:
    try:
        compile(content, filepath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"


def apply_replace(path: Path, old: str, new: str,
                  marker: str, no_backup: bool) -> str:
    if not path.exists():
        print_fail(f"{path.relative_to(ROOT)}: 不存在")
        return 'failed'
    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败 ({e})")
        return 'failed'

    if marker and marker in content:
        print_skip(f"{path.relative_to(ROOT)}: 已修复")
        return 'skipped'

    cnt = content.count(old)
    if cnt == 0:
        print_fail(f"{path.relative_to(ROOT)}: 锚点未找到")
        for line in old.split('\n')[:3]:
            print(f"      | {line}")
        return 'failed'
    if cnt > 1:
        print_fail(f"{path.relative_to(ROOT)}: 锚点重复 {cnt} 次")
        return 'failed'

    new_content = content.replace(old, new, 1)

    if path.suffix == '.py':
        ok, err = validate_python(new_content, str(path))
        if not ok:
            print_fail(f"语法错误 ({err})")
            return 'failed'

    if not write_back(path, new_content, no_backup):
        return 'failed'
    print_ok(f"{path.relative_to(ROOT)}: 已修复")
    return 'applied'


# ============================================================
# A: _apply_theme_by_name 用 loader.apply_qss
# ============================================================
A_MARKER = "# A(主题): 用 loader.apply_qss 处理无 qss 主题"

A_OLD = '''            for i in range(self.tabs.count()):
                loader.apply(self.tabs.widget(i), theme)
            if theme.qss:
                self.setStyleSheet(theme.qss)'''

A_NEW = '''            for i in range(self.tabs.count()):
                loader.apply(self.tabs.widget(i), theme)

            # A(主题): 用 loader.apply_qss 处理无 qss 主题
            # 原实现只在 `if theme.qss:` 时才 setStyleSheet，而
            # themes/*.json 里都没有 qss 字段，导致 QSS 从未应用。
            # apply_qss 会在 qss 为空时从 colors 生成 QSS。
            try:
                from PyQt5.QtWidgets import QApplication
                _app = QApplication.instance()
                if _app is not None:
                    loader.apply_qss(_app, theme)
                    # 有些 QSS 选择器（QMainWindow 等）需要重设
                    _app.setStyleSheet(_app.styleSheet())
            except Exception as _e:
                print(f"[Theme] apply_qss 失败: {_e}")
                if theme.qss:
                    self.setStyleSheet(theme.qss)'''


# ============================================================
# B: 菜单显示 display_name
# ============================================================
B_MARKER = "# B(主题): 菜单显示 display_name"

B_OLD = '''        # 动态扫描 themes/
        themes_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "themes"
        )
        if os.path.isdir(themes_dir):
            for f in sorted(os.listdir(themes_dir)):
                if f.endswith('.json'):
                    name = os.path.splitext(f)[0]
                    self._add_action(
                        self.theme_menu, name, None,
                        lambda checked=False, n=name:
                        self._apply_theme_by_name(n)
                    )'''

B_NEW = '''        # 动态扫描 themes/
        themes_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "themes"
        )
        if os.path.isdir(themes_dir):
            for f in sorted(os.listdir(themes_dir)):
                if f.endswith('.json'):
                    name = os.path.splitext(f)[0]
                    # B(主题): 菜单显示 display_name
                    # 读取 display_name 用于展示，name 保留给回调用
                    display = name
                    try:
                        import json as _json
                        with open(
                            os.path.join(themes_dir, f),
                            'r', encoding='utf-8'
                        ) as _fp:
                            _data = _json.load(_fp)
                        display = _data.get('display_name', name)
                    except Exception:
                        pass
                    self._add_action(
                        self.theme_menu, display, None,
                        lambda checked=False, n=name:
                        self._apply_theme_by_name(n)
                    )'''


FIXES = [
    ("A", "main_window._apply_theme_by_name 用 apply_qss",
     lambda nb: apply_replace(
         ROOT / "ui" / "main_window.py",
         A_OLD, A_NEW, A_MARKER, nb)),
    ("B", "主题菜单显示 display_name",
     lambda nb: apply_replace(
         ROOT / "ui" / "main_window.py",
         B_OLD, B_NEW, B_MARKER, nb)),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("主题切换根本性修复")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")

    if args.dry_run:
        print()
        print_info("[DRY-RUN] 将处理：")
        print_info("  A. _apply_theme_by_name 用 loader.apply_qss")
        print_info("  B. 菜单显示 display_name（晨曦 而非 light_clean）")
        return 0

    results = []
    for pid, name, fn in FIXES:
        print_header(f"{pid}: {name}")
        r = fn(args.no_backup)
        results.append((pid, name, r))

    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    applied = skipped = failed = 0
    for pid, name, r in results:
        marker = {'applied': '✓', 'skipped': '-', 'failed': '✗'}[r]
        print(f"  {marker} {pid}: {name} [{r}]")
        if r == 'applied':
            applied += 1
        elif r == 'skipped':
            skipped += 1
        else:
            failed += 1

    if failed:
        print(f"\n✗ 有 {failed} 项失败")
        return 1

    print()
    print("=" * 60)
    print(f"✓ 完成（应用 {applied}，跳过 {skipped}）")
    print("=" * 60)
    print()
    print("验证:")
    print("  python tests/run_all.py")
    print("  python main.py")
    print()
    print("手工验证:")
    print("  1. 视图 → 主题 → 晨曦")
    print("  2. 界面应变白")
    print("  3. 切回 dark_night → 变黑")
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