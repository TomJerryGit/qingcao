#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Vim 状态栏 + Ctrl+Alt+V + 快捷键冲突修复
==========================================
修复 3 类问题：

  A. Vim 状态栏被覆盖 → 缩短启用提示，让 VimMode 状态显示
  B. Ctrl+Alt+V 在 Windows 无效（AltGr 冲突）→ 改用 Ctrl+Shift+V
  C. 5 处真快捷键冲突
     - AI 助手: Ctrl+Shift+E → Ctrl+Alt+E
                Ctrl+Shift+R → Ctrl+Alt+Shift+R
     - Markdown: Ctrl+Shift+M → Ctrl+Alt+M
     - PyDebug:  F5           → F6
     - TODO:     Ctrl+Shift+T → Ctrl+Alt+T

用法:
    python fix_vim_shortcuts.py --dry-run
    python fix_vim_shortcuts.py
"""

import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple, List

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.vs"


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
    """sections: [(marker, old, new), ...]"""
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
# A + B: main_window.py —— Vim 状态栏 & 快捷键
# ============================================================
A_MARKER = "# A: 缩短启用提示，避免覆盖 VimMode 的状态显示"

A_OLD = '''                vim.set_enabled(True)

                # 焦点给编辑器，否则按键进不来
                try:
                    editor.setFocus()
                except Exception:
                    pass

                self.status_bar.showMessage(
                    "Vim 模式已启用（Esc 回到 Normal，"
                    "再按 Ctrl+Alt+V 关闭）", 4000
                )
                print("[MainWindow] Vim 模式已启用")'''

A_NEW = '''                vim.set_enabled(True)

                # 焦点给编辑器，否则按键进不来
                try:
                    editor.setFocus()
                except Exception:
                    pass

                # A: 缩短启用提示，避免覆盖 VimMode 的状态显示
                # 原来显示 4000ms，会盖住 VimMode 的 "-- 普通 --"
                self.status_bar.showMessage("Vim 模式已启用", 1500)
                print("[MainWindow] Vim 模式已启用")'''


B_MARKER = "# B: Ctrl+Alt+V 在 Windows 被解释为 AltGr+V，改为 Ctrl+Shift+V"

B_OLD = '''        self.vim_mode_action.setShortcut(QKeySequence("Ctrl+Alt+V"))'''

B_NEW = '''        # B: Ctrl+Alt+V 在 Windows 被解释为 AltGr+V，改为 Ctrl+Shift+V
        self.vim_mode_action.setShortcut(QKeySequence("Ctrl+Shift+V"))'''


# ============================================================
# C1: AI 助手快捷键冲突
# ============================================================
C1_MARKER = "# C1: 避开主窗口的 Ctrl+Shift+E / Ctrl+Shift+R"

C1_OLD = '''        menu_items = [
            ("工具/AI 助手/💡 解释代码", self._on_explain, "Ctrl+Shift+E"),
            ("工具/AI 助手/🔧 重构代码", self._on_refactor, "Ctrl+Shift+R"),'''

C1_NEW = '''        # C1: 避开主窗口的 Ctrl+Shift+E / Ctrl+Shift+R
        menu_items = [
            ("工具/AI 助手/💡 解释代码", self._on_explain, "Ctrl+Alt+E"),
            ("工具/AI 助手/🔧 重构代码", self._on_refactor,
             "Ctrl+Alt+Shift+R"),'''

C1_SHORTCUT_OLD = '''        shortcuts = [
            ("Ctrl+Shift+A", self._show_ai_menu),
            ("Ctrl+Shift+E", self._on_explain),
            ("Ctrl+Shift+R", self._on_refactor),
        ]'''

C1_SHORTCUT_NEW = '''        shortcuts = [
            ("Ctrl+Shift+A", self._show_ai_menu),
            ("Ctrl+Alt+E", self._on_explain),
            ("Ctrl+Alt+Shift+R", self._on_refactor),
        ]'''


# ============================================================
# C2: Markdown 预览快捷键
# ============================================================
C2_MARKER = "# C2: 避开主窗口的 Ctrl+Shift+M（回放宏）"

C2_OLD = '''        self.api.add_menu(
            "视图/Markdown 预览",
            self.toggle_preview,
            shortcut="Ctrl+Shift+M"
        )'''

C2_NEW = '''        # C2: 避开主窗口的 Ctrl+Shift+M（回放宏）
        self.api.add_menu(
            "视图/Markdown 预览",
            self.toggle_preview,
            shortcut="Ctrl+Alt+M"
        )'''


# ============================================================
# C3: Python 调试器快捷键
# ============================================================
C3_MARKER = "# C3: 避开主窗口的 F5（插入日期时间）"

C3_OLD = '''        self.api.add_menu(
            "工具/Python 调试/运行当前文件",
            self.run_current,
            shortcut="F5"
        )
        self.api.add_menu(
            "工具/Python 调试/调试当前文件 (pdb)",
            self.debug_current,
            shortcut="F6"
        )'''

C3_NEW = '''        # C3: 避开主窗口的 F5（插入日期时间）
        self.api.add_menu(
            "工具/Python 调试/运行当前文件",
            self.run_current,
            shortcut="F6"
        )
        self.api.add_menu(
            "工具/Python 调试/调试当前文件 (pdb)",
            self.debug_current,
            shortcut="F7"
        )'''


# ============================================================
# C4: TODO 面板快捷键
# ============================================================
C4_MARKER = "# C4: 避开主窗口的 Ctrl+Shift+T（恢复标签）"

C4_OLD = '''        self.api.add_menu(
            "视图/TODO 面板",
            self.show_panel,
            shortcut="Ctrl+Shift+T"
        )'''

C4_NEW = '''        # C4: 避开主窗口的 Ctrl+Shift+T（恢复标签）
        self.api.add_menu(
            "视图/TODO 面板",
            self.show_panel,
            shortcut="Ctrl+Alt+T"
        )'''


# ============================================================
# 主流程
# ============================================================
def fix_A_B(no_backup: bool) -> str:
    path = ROOT / "ui" / "main_window.py"
    return apply_multi(
        path,
        [(A_MARKER, A_OLD, A_NEW),
         (B_MARKER, B_OLD, B_NEW)],
        no_backup,
    )


def fix_C1(no_backup: bool) -> str:
    path = ROOT / "plugins" / "ai_assistant" / "__init__.py"
    return apply_multi(
        path,
        [(C1_MARKER, C1_OLD, C1_NEW),
         ("C1 shortcuts", C1_SHORTCUT_OLD, C1_SHORTCUT_NEW)],
        no_backup,
    )


def fix_C2(no_backup: bool) -> str:
    path = ROOT / "plugins" / "markdown_preview" / "__init__.py"
    return apply_multi(path, [(C2_MARKER, C2_OLD, C2_NEW)], no_backup)


def fix_C3(no_backup: bool) -> str:
    path = ROOT / "plugins" / "python_debugger" / "__init__.py"
    return apply_multi(path, [(C3_MARKER, C3_OLD, C3_NEW)], no_backup)


def fix_C4(no_backup: bool) -> str:
    path = ROOT / "plugins" / "todo_panel" / "__init__.py"
    return apply_multi(path, [(C4_MARKER, C4_OLD, C4_NEW)], no_backup)


FIXES = [
    ("A+B", "Vim 状态栏 + Ctrl+Shift+V", fix_A_B),
    ("C1", "AI 助手快捷键", fix_C1),
    ("C2", "Markdown 预览快捷键", fix_C2),
    ("C3", "Python 调试器快捷键", fix_C3),
    ("C4", "TODO 面板快捷键", fix_C4),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--only', type=str, default='')
    args = parser.parse_args()

    print_header("Vim 状态栏 + 快捷键冲突修复")
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
        if r == 'applied': applied += 1
        elif r == 'skipped': skipped += 1
        else: failed += 1

    if failed:
        print(f"\n✗ 有 {failed} 项失败")
        return 1

    print()
    print("=" * 60)
    print(f"✓ 完成（应用 {applied}，跳过 {skipped}）")
    print("=" * 60)
    print()
    print("新快捷键表:")
    print("  Vim 模式:          Ctrl+Shift+V  ← 改（避开 AltGr）")
    print("  AI 解释代码:        Ctrl+Alt+E")
    print("  AI 重构代码:        Ctrl+Alt+Shift+R")
    print("  Markdown 预览:      Ctrl+Alt+M")
    print("  Python 运行:        F6")
    print("  Python 调试:        F7")
    print("  TODO 面板:          Ctrl+Alt+T")
    print()
    print("验证:")
    print("  python tests/run_all.py")
    print("  python main.py")
    print()
    print("手工验证:")
    print("  1. 打开文件 → Ctrl+Shift+V → 状态栏应显示 '-- 普通 --'")
    print("  2. 按 h/j/k/l → 光标移动（已有）")
    print("  3. 按 Esc → 状态栏 '-- 普通 --' 应保持")
    print("  4. 再按 Ctrl+Shift+V → Vim 模式关闭")
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