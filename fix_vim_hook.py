#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Vim 模式接入 + 状态信号连接
==============================
修复两个问题：

  A. EditorWidget.keyPressEvent 未调用 VimMode.handle_key
     → Vim 模式下所有按键都走原逻辑，等于没启用

  B. VimMode.status_message / state_changed 信号未连接
     → 状态栏看不到当前模式

  C. _toggle_vim_mode 未给编辑器 setFocus
     → 菜单点击后焦点可能在菜单，按键进不来

用法:
    python fix_vim_hook.py --dry-run
    python fix_vim_hook.py
"""

import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.vimhook"


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
# A: editor_view.py keyPressEvent 加 vim hook
# ============================================================
A_MARKER = "# Vim 模式：优先让 VimMode 处理"

A_OLD = '''        key = event.key()
        text = event.text()
        modifiers = event.modifiers()

        # Esc：清除多光标
        if key == Qt.Key_Escape:'''

A_NEW = '''        # Vim 模式：优先让 VimMode 处理
        # （VimMode.handle_key 返回 True 表示已消化，直接 return）
        vim = getattr(self, '_vim_mode', None)
        if vim is not None and getattr(vim, 'enabled', False):
            try:
                if vim.handle_key(event):
                    return
            except Exception as e:
                print(f"[EditorWidget] VimMode 处理失败: {e}")

        key = event.key()
        text = event.text()
        modifiers = event.modifiers()

        # Esc：清除多光标
        if key == Qt.Key_Escape:'''


# ============================================================
# B: main_window.py _toggle_vim_mode 增强
# ============================================================
B_MARKER = "VimMode 实例（增强：信号连接 + setFocus）"

B_OLD = '''    # C: Vim 模式切换方法
    def _toggle_vim_mode(self, checked: bool):
        """切换 Vim 模式

        为当前编辑器附加/移除 VimMode 实例。
        """
        try:
            from core.vim_mode import VimMode

            proxy = self.tabs.current_proxy()
            if not proxy or not proxy.sc:
                self.status_bar.showMessage("没有活动的编辑器", 2000)
                self.vim_mode_action.setChecked(False)
                return

            editor = proxy.sc

            if checked:
                # 创建 VimMode 实例并附加到 editor
                vim = getattr(editor, '_vim_mode', None)
                if vim is None:
                    vim = VimMode(editor)
                    editor._vim_mode = vim
                vim.set_enabled(True)
                self.status_bar.showMessage(
                    "Vim 模式已启用（Esc 回到 Normal）", 3000
                )
            else:
                vim = getattr(editor, '_vim_mode', None)
                if vim is not None:
                    vim.set_enabled(False)
                self.status_bar.showMessage("Vim 模式已禁用", 2000)
        except Exception as e:
            print(f"[MainWindow] Vim 切换失败: {e}")
            self.status_bar.showMessage(f"Vim 切换失败: {e}", 3000)'''

B_NEW = '''    # VimMode 实例（增强：信号连接 + setFocus）
    def _toggle_vim_mode(self, checked: bool):
        """切换 Vim 模式

        为当前编辑器附加/移除 VimMode 实例。
        """
        try:
            from core.vim_mode import VimMode

            proxy = self.tabs.current_proxy()
            if not proxy or not proxy.sc:
                self.status_bar.showMessage("没有活动的编辑器", 2000)
                self.vim_mode_action.setChecked(False)
                return

            editor = proxy.sc

            if checked:
                vim = getattr(editor, '_vim_mode', None)
                if vim is None:
                    vim = VimMode(editor)
                    editor._vim_mode = vim

                # 首次创建时连接信号（状态栏显示模式）
                if not getattr(vim, '_signal_connected', False):
                    try:
                        vim.status_message.connect(
                            lambda msg:
                            self.status_bar.showMessage(msg, 2000)
                            if msg else None
                        )
                        vim.state_changed.connect(
                            lambda st:
                            self.status_bar.showMessage(
                                f"Vim: {st}", 1500
                            )
                        )
                        vim._signal_connected = True
                    except Exception:
                        pass

                vim.set_enabled(True)

                # 焦点给编辑器，否则按键进不来
                try:
                    editor.setFocus()
                except Exception:
                    pass

                self.status_bar.showMessage(
                    "Vim 模式已启用（Esc 回到 Normal，"
                    "再按 Ctrl+Alt+V 关闭）", 4000
                )
                print("[MainWindow] Vim 模式已启用")
            else:
                vim = getattr(editor, '_vim_mode', None)
                if vim is not None:
                    vim.set_enabled(False)
                self.status_bar.showMessage("Vim 模式已禁用", 2000)
                print("[MainWindow] Vim 模式已禁用")
        except Exception as e:
            print(f"[MainWindow] Vim 切换失败: {e}")
            import traceback
            traceback.print_exc()
            self.status_bar.showMessage(f"Vim 切换失败: {e}", 3000)'''


# ============================================================
# 主流程
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("Vim 模式接入 + 信号连接")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")

    if args.dry_run:
        print()
        print_info("将修复：")
        print_info("  A. editor_view.py: keyPressEvent 加 vim hook")
        print_info("  B. main_window.py: _toggle_vim_mode 增强")
        return 0

    editor_view = ROOT / "ui" / "editor_view.py"
    main_window = ROOT / "ui" / "main_window.py"

    print_header("A: editor_view.py keyPressEvent 加 vim hook")
    r1 = apply_replace(editor_view, A_OLD, A_NEW, A_MARKER,
                       args.no_backup)

    print_header("B: main_window.py _toggle_vim_mode 增强")
    r2 = apply_replace(main_window, B_OLD, B_NEW, B_MARKER,
                       args.no_backup)

    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    for pid, name, r in [("A", "keyPressEvent hook", r1),
                          ("B", "_toggle_vim_mode", r2)]:
        marker = {'applied': '✓', 'skipped': '-', 'failed': '✗'}[r]
        print(f"  {marker} {pid}: {name} [{r}]")

    if 'failed' in (r1, r2):
        print()
        print_fail("有失败项")
        return 1

    print()
    print("=" * 60)
    print("✓ 完成")
    print("=" * 60)
    print()
    print("验证:")
    print("  python tests/run_all.py")
    print("  python main.py")
    print()
    print("手工验证:")
    print("  1. 工具 → Vim 模式（或 Ctrl+Alt+V）")
    print("  2. 状态栏应显示 'Vim 模式已启用'")
    print("  3. 按 Esc → 状态栏应显示 '-- 普通 --'")
    print("  4. 按 h/j/k/l → 光标移动")
    print("  5. 按 i → 状态栏 '-- 插入 --'")
    print("  6. 按 dd/dw/ciw → 操作符生效")
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