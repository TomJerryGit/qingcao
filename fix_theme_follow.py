#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
主题跟随完整补丁
==============================
修复"切换主题后部分面板不跟随"。

  A. theme_loader.py: adapt_qss_colors 替换表扩展
     加入 #0d0d0d（终端背景）、#2a2d2e（目录树 hover）、
     #333333 / #4c4c4c（面板变体）、#c0c0c0（次要文字）等

  B. main_window.py: _apply_theme_by_name 遍历顶层窗口
     让独立打开的对话框也能响应主题切换

  C. ui/panels.py: SearchBar 加 refresh_theme

  D. ui/python_console.py: PythonConsole 加 refresh_theme

用法:
    python fix_theme_follow.py --dry-run
    python fix_theme_follow.py
"""

import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple, List

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.theme"


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


def apply_multi(path: Path,
                sections: List[Tuple[str, str, str]],
                no_backup: bool) -> str:
    if not path.exists():
        print_fail(f"{path.relative_to(ROOT)}: 不存在")
        return 'failed'
    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败 ({e})")
        return 'failed'

    if all(m in content for m, _, _ in sections):
        print_skip(f"{path.relative_to(ROOT)}: 已修复")
        return 'skipped'

    new_content = content
    for i, (marker, old, new) in enumerate(sections, 1):
        if marker in new_content:
            print_info(f"  段 {i}: 已应用")
            continue
        cnt = new_content.count(old)
        if cnt == 0:
            print_fail(f"  段 {i}: 锚点未找到")
            for line in old.split('\n')[:3]:
                print(f"      | {line}")
            return 'failed'
        if cnt > 1:
            print_fail(f"  段 {i}: 锚点重复 {cnt} 次")
            return 'failed'
        new_content = new_content.replace(old, new, 1)
        print_info(f"  段 {i}: 已替换")

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
# A: adapt_qss_colors 扩表
# ============================================================
A_MARKER = "# A: 补充终端/控制台/次要文字等颜色"

A_OLD = '''    # 老深色 → 主题色（按优先级，先长后短）
    replacements = [
        ('#252526', c.panel_bg),
        ('#1e1e1e', c.background),
        ('#2d2d2d', c.menubar_bg),
        ('#3c3c3c', c.border),
        ('#d4d4d4', c.foreground),
        ('#cccccc', c.tab_fg),
        ('#888888', c.line_number_fg),
        ('#666666', c.line_number_fg),
        ('#555555', c.input_border),
        ('#888', c.line_number_fg),
        ('#666', c.line_number_fg),
        ('#555', c.input_border),
        ('#094771', c.menu_selection),
        ('#7ec850', c.accent),
        ('#0e639c', c.button_bg),
        ('#1177bb', c.button_hover),
        ('#f14c4c', c.error),
        ('#f0ad4e', c.warning),
        ('#4dabf7', c.info),
    ]'''

A_NEW = '''    # 老深色 → 主题色（按优先级，先长后短）
    #
    # A: 补充终端/控制台/次要文字等颜色
    # 顺序重要：6 位色必须在 3 位色之前，避免误伤
    replacements = [
        # ==== 原表 ====
        ('#252526', c.panel_bg),
        ('#1e1e1e', c.background),
        ('#2d2d2d', c.menubar_bg),
        ('#3c3c3c', c.border),
        ('#d4d4d4', c.foreground),
        ('#cccccc', c.tab_fg),
        ('#888888', c.line_number_fg),
        ('#666666', c.line_number_fg),
        ('#555555', c.input_border),
        ('#888', c.line_number_fg),
        ('#666', c.line_number_fg),
        ('#555', c.input_border),
        ('#094771', c.menu_selection),
        ('#7ec850', c.accent),
        ('#0e639c', c.button_bg),
        ('#1177bb', c.button_hover),
        ('#f14c4c', c.error),
        ('#f0ad4e', c.warning),
        ('#4dabf7', c.info),

        # ==== A: 补充 ====
        # 终端/控制台背景（关键）
        ('#0d0d0d', c.background),
        # 目录树 hover
        ('#2a2d2e', c.panel_bg),
        # 面板变体
        ('#333333', c.panel_bg),
        ('#4c4c4c', c.border),
        # 次要文字
        ('#858585', c.line_number_fg),
        ('#808080', c.line_number_fg),
        ('#c0c0c0', c.tab_fg),
        # 缩进辅助线
        ('#404040', c.indent_guide),
        # 禁用/危险按钮
        ('#5a5a5a', c.border),
        ('#8f1e1e', c.error),
    ]'''


# ============================================================
# B: main_window.py 遍历顶层窗口
# ============================================================
B_MARKER = "# B: 遍历所有顶层窗口（含独立对话框）"

B_OLD = '''            # v3.0: 通知所有面板刷新样式
            loader.notify_widgets(self, theme)'''

B_NEW = '''            # v3.0: 通知所有面板刷新样式
            loader.notify_widgets(self, theme)

            # B: 遍历所有顶层窗口（含独立对话框）
            # notify_widgets 只处理 self.findChildren，独立打开的
            # 对话框（AI 配置、Git 提交、快捷键编辑器等）不在其中
            try:
                from PyQt5.QtWidgets import QApplication
                for w in QApplication.topLevelWidgets():
                    if w is self:
                        continue
                    fn = getattr(w, 'refresh_theme', None)
                    if callable(fn):
                        try:
                            fn(theme)
                        except Exception:
                            pass
            except Exception:
                pass'''


# ============================================================
# C: SearchBar 加 refresh_theme
# ============================================================
C_MARKER = "# C: SearchBar 主题刷新"

C_OLD = '''    def dump(self) -> str:
        """导出搜索栏信息"""
        lines = ["SearchBar", "=" * 60]
        lines.append(f"查找: {self.pattern_edit.text()}")
        lines.append(f"替换: {self.replace_edit.text()}")
        lines.append(f"正则: {self.regex_cb.isChecked()}")
        lines.append(f"大小写: {self.case_cb.isChecked()}")
        lines.append(f"全词: {self.whole_word_cb.isChecked()}")
        lines.append(f"转义: {self.escape_cb.isChecked()}")
        lines.append(f"历史: {len(self._search_history)} 条")
        return "\\n".join(lines)'''

C_NEW = '''    # C: SearchBar 主题刷新
    def refresh_theme(self, theme):
        """主题变更时刷新样式"""
        try:
            from infrastructure.theme_loader import adapt_qss_colors
            if not hasattr(self, '_original_qss') or not self._original_qss:
                self._original_qss = self.styleSheet()
            if self._original_qss:
                qss = adapt_qss_colors(self._original_qss, theme)
                self.setStyleSheet(qss)
        except Exception as e:
            print(f"[SearchBar] refresh_theme 失败: {e}")

    def dump(self) -> str:
        """导出搜索栏信息"""
        lines = ["SearchBar", "=" * 60]
        lines.append(f"查找: {self.pattern_edit.text()}")
        lines.append(f"替换: {self.replace_edit.text()}")
        lines.append(f"正则: {self.regex_cb.isChecked()}")
        lines.append(f"大小写: {self.case_cb.isChecked()}")
        lines.append(f"全词: {self.whole_word_cb.isChecked()}")
        lines.append(f"转义: {self.escape_cb.isChecked()}")
        lines.append(f"历史: {len(self._search_history)} 条")
        return "\\n".join(lines)'''


# ============================================================
# D: PythonConsole 加 refresh_theme
# ============================================================
D_MARKER = "# D: PythonConsole 主题刷新"

D_OLD = '''    def dump(self) -> str:
        """导出控制台信息"""
        lines = ["PythonConsole", "=" * 60]
        lines.append(f"Python: {sys.version.split()[0]}")
        lines.append(
            f"命名空间变量: "
            f"{len([k for k in self.namespace.keys() if not k.startswith('_')])}"
        )
        lines.append(f"历史记录: {len(self.history.get_all())}")
        lines.append(f"输出行数: {len(self.output.toPlainText().splitlines())}")
        return "\\n".join(lines)'''

D_NEW = '''    # D: PythonConsole 主题刷新
    def refresh_theme(self, theme):
        """主题变更时刷新样式"""
        try:
            from infrastructure.theme_loader import adapt_qss_colors

            if not hasattr(self, '_original_qss'):
                self._original_qss = self.styleSheet()
                self._original_output_qss = (
                    self.output.styleSheet() if self.output else ""
                )
                self._original_input_qss = (
                    self.input_edit.styleSheet() if self.input_edit else ""
                )

            if self._original_qss:
                self.setStyleSheet(
                    adapt_qss_colors(self._original_qss, theme)
                )
            if self.output and self._original_output_qss:
                self.output.setStyleSheet(
                    adapt_qss_colors(self._original_output_qss, theme)
                )
            if self.input_edit and self._original_input_qss:
                self.input_edit.setStyleSheet(
                    adapt_qss_colors(self._original_input_qss, theme)
                )
        except Exception as e:
            print(f"[PythonConsole] refresh_theme 失败: {e}")

    def dump(self) -> str:
        """导出控制台信息"""
        lines = ["PythonConsole", "=" * 60]
        lines.append(f"Python: {sys.version.split()[0]}")
        lines.append(
            f"命名空间变量: "
            f"{len([k for k in self.namespace.keys() if not k.startswith('_')])}"
        )
        lines.append(f"历史记录: {len(self.history.get_all())}")
        lines.append(f"输出行数: {len(self.output.toPlainText().splitlines())}")
        return "\\n".join(lines)'''


FIXES = [
    ("A", "theme_loader adapt_qss_colors 扩表", lambda nb: apply_multi(
        ROOT / "infrastructure" / "theme_loader.py",
        [(A_MARKER, A_OLD, A_NEW)], nb)),
    ("B", "main_window 遍历顶层窗口", lambda nb: apply_multi(
        ROOT / "ui" / "main_window.py",
        [(B_MARKER, B_OLD, B_NEW)], nb)),
    ("C", "SearchBar refresh_theme", lambda nb: apply_multi(
        ROOT / "ui" / "panels.py",
        [(C_MARKER, C_OLD, C_NEW)], nb)),
    ("D", "PythonConsole refresh_theme", lambda nb: apply_multi(
        ROOT / "ui" / "python_console.py",
        [(D_MARKER, D_OLD, D_NEW)], nb)),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--only', type=str, default='')
    args = parser.parse_args()

    print_header("主题跟随完整补丁")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")

    fixes = FIXES
    if args.only:
        only = {x.strip().upper() for x in args.only.split(',')}
        fixes = [f for f in fixes if f[0] in only]

    if args.dry_run:
        print()
        print_info(f"[DRY-RUN] 将处理 {len(fixes)} 项：")
        for pid, name, _ in fixes:
            print_info(f"  {pid}: {name}")
        return 0

    results = []
    for pid, name, fn in fixes:
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
    print("  1. 打开文件")
    print("  2. 打开 Python 控制台（Ctrl+`）")
    print("  3. Ctrl+F 显示搜索栏")
    print("  4. 视图 → 主题 → 晨曦")
    print("  5. 观察：控制台/搜索栏 背景应变亮")
    print("  6. 再切回暗夜，应恢复")
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