#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - 主题跟随修复
============================================================
修复：切换主题时，各面板（全局搜索/性能监控/插件/目录树/大纲）
      的 QSS 硬编码颜色不跟随。

方案：
    1. theme_loader.py 增加：
       - adapt_qss_colors(qss, theme): 颜色替换
       - notify_widgets(root, theme): 遍历子控件调用 refresh_theme
    2. main_window.py 在切主题时调用 notify_widgets
    3. 各面板增加 refresh_theme(theme) 方法

特性：
    - 幂等
    - 逐文件备份为 *.bak.themefollow
    - 修改后 compile() 验证
    - 单文件失败不影响其他文件

用法：
    python fix_theme_follow.py --dry-run
    python fix_theme_follow.py
"""

import os
import sys
import shutil
import argparse
import traceback
from pathlib import Path
from typing import List, Tuple, Optional

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.themefollow"


def print_header(t): print(f"\n{'=' * 60}\n{t}\n{'=' * 60}")
def print_ok(m): print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")


# ============================================================
# 各面板的 refresh_theme 方法（统一模板）
# ============================================================
REFRESH_METHOD = '''
    def refresh_theme(self, theme):
        """主题变更时刷新样式（v3.0）"""
        try:
            from infrastructure.theme_loader import adapt_qss_colors
            # 保存原始 QSS（只保存一次）
            if not hasattr(self, '_original_qss') or not self._original_qss:
                self._original_qss = self.styleSheet()
            if self._original_qss:
                qss = adapt_qss_colors(self._original_qss, theme)
                self.setStyleSheet(qss)
        except Exception as e:
            print(f"[{self.__class__.__name__}] refresh_theme 失败: {e}")

'''


# ============================================================
# 前置检查：确保 theme_loader 已打补丁
# ============================================================
def check_loader_patched() -> bool:
    path = ROOT / "infrastructure" / "theme_loader.py"
    if not path.exists():
        return False
    try:
        content = path.read_text(encoding='utf-8')
    except Exception:
        return False
    return 'def adapt_qss_colors(' in content and \
           'def notify_widgets(' in content


# ============================================================
# 补丁定义
# ============================================================
# 补丁 A: theme_loader.py 增加 adapt_qss_colors 和 notify_widgets
LOADER_FILE = "infrastructure/theme_loader.py"
LOADER_MARKER = "def adapt_qss_colors("

LOADER_ANCHOR = '''# ============================================================
# 主题加载器
# ============================================================
class ThemeLoader(QObject):'''

LOADER_NEW = '''# ============================================================
# 主题色辅助（v3.0）
# ============================================================
def adapt_qss_colors(qss: str, theme) -> str:
    """
    把 QSS 中的硬编码深色替换为主题色。

    参数:
        qss: 原始 QSS 字符串
        theme: Theme 对象

    返回:
        替换后的 QSS
    """
    if not qss or theme is None:
        return qss

    try:
        c = theme.colors
    except Exception:
        return qss

    # 老深色 → 主题色（按优先级，先长后短）
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
    ]

    for old, new in replacements:
        if old and new and old != new:
            qss = qss.replace(old, new)

    return qss


def notify_widgets(root, theme):
    """
    遍历控件树，通知所有 refresh_theme 方法（v3.0）。

    参数:
        root: 根控件（通常是 QMainWindow）
        theme: Theme 对象
    """
    from PyQt5.QtWidgets import QWidget
    if root is None or theme is None:
        return
    try:
        for widget in root.findChildren(QWidget):
            fn = getattr(widget, 'refresh_theme', None)
            if callable(fn):
                try:
                    fn(theme)
                except Exception:
                    pass
    except Exception:
        pass


# ============================================================
# 主题加载器
# ============================================================
class ThemeLoader(QObject):'''


# 补丁 B: main_window.py 在切主题时调用 notify_widgets
MW_FILE = "ui/main_window.py"
MW_MARKER = "ThemeLoader.notify_widgets(self, theme)"

MW_OLD = '''            for i in range(self.tabs.count()):
                loader.apply(self.tabs.widget(i), theme)
            if theme.qss:
                self.setStyleSheet(theme.qss)

            # 持久化
            from PyQt5.QtCore import QSettings
            settings = QSettings("QingCao", "Editor")
            settings.setValue("theme_name", name)'''

MW_NEW = '''            for i in range(self.tabs.count()):
                loader.apply(self.tabs.widget(i), theme)
            if theme.qss:
                self.setStyleSheet(theme.qss)

            # v3.0: 通知所有面板刷新样式
            loader.notify_widgets(self, theme)

            # 持久化
            from PyQt5.QtCore import QSettings
            settings = QSettings("QingCao", "Editor")
            settings.setValue("theme_name", name)'''


# 各面板：插入 refresh_theme 方法
PANELS = [
    # (文件路径, 类名, 锚点方法名)
    ("ui/global_search_panel.py", "GlobalSearchPanel", "def _apply_style"),
    ("ui/perf_monitor.py", "PerfMonitor", "def _apply_style"),
    ("ui/plugins_panel.py", "PluginsPanel", "def _apply_style"),
    ("ui/directory_tree.py", "DirectoryTree", "def _apply_style"),
    ("ui/outline_panel.py", "OutlinePanel", "def _apply_style"),
    ("ui/problems_panel.py", "ProblemsPanel", "def _apply_style"),
    ("ui/git_panel.py", "GitPanel", "def _apply_style"),
    ("ui/lsp_panel.py", "LspPanel", "def _apply_style"),
    ("ui/log_viewer.py", "LogViewer", "def _apply_style"),
    ("ui/task_panel.py", "TaskPanel", "def _apply_style"),
    ("ui/terminal_panel.py", "TerminalPanel", "def _apply_style"),
    ("ui/undo_history_panel.py", "UndoHistoryPanel", "def _apply_style"),
]


# ============================================================
# 应用函数
# ============================================================
def validate_python(content, filepath):
    try:
        compile(content, filepath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def apply_replace(path: Path, old: str, new: str,
                  marker: str, name: str,
                  dry_run: bool,
                  no_backup: bool) -> str:
    """通用替换。返回 'applied' / 'skipped' / 'failed'"""
    if not path.exists():
        print_fail(f"{name}: 文件不存在")
        return 'failed'

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"{name}: 读取失败 ({e})")
        return 'failed'

    if marker in content:
        print_skip(f"{name}: 已应用")
        return 'skipped'

    if old not in content:
        print_fail(f"{name}: 锚点未找到")
        return 'failed'

    if content.count(old) > 1:
        print_fail(f"{name}: 锚点重复 {content.count(old)} 次")
        return 'failed'

    if dry_run:
        print_info(f"[DRY-RUN] {name}: 会修改")
        return 'applied'

    new_content = content.replace(old, new, 1)

    ok, err = validate_python(new_content, str(path))
    if not ok:
        print_fail(f"{name}: 语法错误 ({err})")
        return 'failed'

    if not no_backup:
        backup = Path(str(path) + BACKUP_SUFFIX)
        if not backup.exists():
            try:
                shutil.copy2(path, backup)
            except Exception:
                pass

    try:
        path.write_text(new_content, encoding='utf-8', newline='\n')
        print_ok(f"{name}: 已应用")
        return 'applied'
    except Exception as e:
        print_fail(f"{name}: 写回失败 ({e})")
        return 'failed'


def apply_panel(path: Path, class_name: str, anchor_method: str,
                dry_run: bool, no_backup: bool) -> str:
    """给面板插入 refresh_theme 方法"""
    if not path.exists():
        print_skip(f"{path.name}: 文件不存在，跳过")
        return 'skipped'

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"{path.name}: 读取失败 ({e})")
        return 'failed'

    # 幂等
    if "def refresh_theme(self, theme):" in content:
        print_skip(f"{path.name}: 已有 refresh_theme")
        return 'skipped'

    # 找锚点
    anchor = f"    {anchor_method}(self):"
    if anchor not in content:
        print_fail(f"{path.name}: 锚点 `{anchor_method}` 未找到")
        return 'failed'

    if content.count(anchor) > 1:
        print_fail(f"{path.name}: 锚点重复")
        return 'failed'

    if dry_run:
        print_info(f"[DRY-RUN] {path.name}: 会插入 refresh_theme")
        return 'applied'

    new_content = content.replace(
        anchor, REFRESH_METHOD + anchor, 1
    )

    ok, err = validate_python(new_content, str(path))
    if not ok:
        print_fail(f"{path.name}: 语法错误 ({err})")
        return 'failed'

    if not no_backup:
        backup = Path(str(path) + BACKUP_SUFFIX)
        if not backup.exists():
            try:
                shutil.copy2(path, backup)
            except Exception:
                pass

    try:
        path.write_text(new_content, encoding='utf-8', newline='\n')
        print_ok(f"{path.name}: 已插入 refresh_theme")
        return 'applied'
    except Exception as e:
        print_fail(f"{path.name}: 写回失败 ({e})")
        return 'failed'


# ============================================================
# 主流程
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--skip-loader', action='store_true',
                        help='跳过 theme_loader 补丁')
    parser.add_argument('--skip-window', action='store_true',
                        help='跳过 main_window 补丁')
    parser.add_argument('--only-panels', action='store_true',
                        help='只处理面板')
    args = parser.parse_args()

    print_header("主题跟随修复")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")

    applied = 0
    skipped = 0
    failed = 0

    # ---- 补丁 A：theme_loader.py ----
    if not args.skip_loader and not args.only_panels:
        print_header("补丁 A: theme_loader.py")
        r = apply_replace(
            ROOT / LOADER_FILE,
            LOADER_ANCHOR, LOADER_NEW,
            LOADER_MARKER,
            "theme_loader.py",
            args.dry_run, args.no_backup
        )
        if r == 'applied': applied += 1
        elif r == 'skipped': skipped += 1
        else: failed += 1

    # ---- 补丁 B：main_window.py ----
    if not args.skip_window and not args.only_panels:
        print_header("补丁 B: main_window.py")
        r = apply_replace(
            ROOT / MW_FILE,
            MW_OLD, MW_NEW,
            MW_MARKER,
            "main_window.py",
            args.dry_run, args.no_backup
        )
        if r == 'applied': applied += 1
        elif r == 'skipped': skipped += 1
        else: failed += 1

    # ---- 补丁 C：各面板 ----
    if not args.skip_loader and not args.skip_window:
        # 完整模式：检查前置
        if not args.dry_run and not check_loader_patched():
            print()
            print_fail("theme_loader.py 补丁未生效")
            print_info("请先单独运行：python fix_theme_follow.py --skip-window --skip-loader ...")
            print_info("或分步执行")
            return 1

    print_header("补丁 C: 各面板加 refresh_theme")
    for path_str, cls_name, anchor in PANELS:
        r = apply_panel(
            ROOT / path_str, cls_name, anchor,
            args.dry_run, args.no_backup
        )
        if r == 'applied': applied += 1
        elif r == 'skipped': skipped += 1
        else: failed += 1

    # ---- 汇总 ----
    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    print(f"  已应用: {applied}")
    print(f"  已跳过: {skipped}")
    print(f"  失败:   {failed}")

    if args.dry_run:
        print()
        print("⚠ DRY-RUN 模式，未修改文件")
        print("  运行 `python fix_theme_follow.py` 应用")
    elif failed == 0 and applied > 0:
        print()
        print("=" * 60)
        print("✓ 修复完成")
        print("=" * 60)
        print()
        print("下一步:")
        print("  python main.py")
        print("  然后切换主题（视图 → 主题）验证效果")

    return 0 if failed == 0 else 1


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