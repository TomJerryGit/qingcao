#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Vim v3: 修复 yy 后 p 粘贴失败
================================
根因:
    v2 补丁把 yank 结果写入 self.registers['"']，
    但 _paste_after / _paste_before 仍读 self.register（空）→
    直接 return，什么都不粘贴。

修复:
    _paste_after / _paste_before 改为从 self.registers['"'] 读，
    并把 copy 也同步到 self.registers['"']，保持两者一致。

用法:
    python fix_vim_v3.py --dry-run
    python fix_vim_v3.py
"""

import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.v3"


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
        print_fail(f"锚点未找到")
        for line in old.split('\n')[:3]:
            print(f"      | {line}")
        return 'failed'
    if cnt > 1:
        print_fail(f"锚点重复 {cnt} 次")
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
# 新的 _paste_after / _paste_before
# ============================================================
PASTE_MARKER = "# v3: 统一从 self.registers['\"'] 读"

OLD_PASTE = '''    def _paste_after(self):
        if not self.register:
            return
        if self.register_is_line:
            line, _ = self.editor.getCursorPosition()
            end = self.editor.SendScintilla(
                self.editor.SCI_GETLINEENDPOSITION, line
            )
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, end,
                ("\\n" + self.register).encode('utf-8')
            )
        else:
            pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, pos + 1,
                self.register.encode('utf-8')
            )

    def _paste_before(self):
        if not self.register:
            return
        if self.register_is_line:
            line, _ = self.editor.getCursorPosition()
            start = self.editor.SendScintilla(
                self.editor.SCI_POSITIONFROMLINE, line
            )
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, start,
                (self.register + "\\n").encode('utf-8')
            )
        else:
            pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, pos,
                self.register.encode('utf-8')
            )'''

NEW_PASTE = '''    def _paste_after(self):
        # v3: 统一从 self.registers['"'] 读
        # 原实现读 self.register，但 v2 起 yank 写入 registers['"']，
        # 导致 yy 后 p 无效。
        text = self.registers.get('"') or self.register
        if not text:
            return
        if self.register_is_line or text.endswith('\\n'):
            # 行粘贴：在下一行插入
            line, _ = self.editor.getCursorPosition()
            end = self.editor.SendScintilla(
                self.editor.SCI_GETLINEENDPOSITION, line
            )
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, end,
                ("\\n" + text.rstrip('\\n')).encode('utf-8')
            )
        else:
            pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, pos + 1,
                text.encode('utf-8')
            )

    def _paste_before(self):
        # v3: 统一从 self.registers['"'] 读
        text = self.registers.get('"') or self.register
        if not text:
            return
        if self.register_is_line or text.endswith('\\n'):
            line, _ = self.editor.getCursorPosition()
            start = self.editor.SendScintilla(
                self.editor.SCI_POSITIONFROMLINE, line
            )
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, start,
                (text.rstrip('\\n') + "\\n").encode('utf-8')
            )
        else:
            pos = self.editor.SendScintilla(self.editor.SCI_GETCURRENTPOS)
            self.editor.SendScintilla(
                self.editor.SCI_INSERTTEXT, pos,
                text.encode('utf-8')
            )'''


# ============================================================
# 同步 registers['"'] 到 self.register（保持兼容）
# ============================================================
SYNC_MARKER = "self.register = text  # v3: 同步旧属性"

OLD_SYNC_1 = '''        text = self.editor.text()[start:end]
        reg = self._pending_register or '"'
        if reg:
            self.registers[reg] = text
            self.registers['"'] = text'''

NEW_SYNC_1 = '''        text = self.editor.text()[start:end]
        reg = self._pending_register or '"'
        if reg:
            self.registers[reg] = text
            self.registers['"'] = text
            self.register = text  # v3: 同步旧属性
            self.register_is_line = False'''

OLD_SYNC_2 = '''            text = self.editor.text()[start:end_with]
            reg = self._pending_register or '"'
            if reg:
                self.registers[reg] = text
                self.registers['"'] = text'''

NEW_SYNC_2 = '''            text = self.editor.text()[start:end_with]
            reg = self._pending_register or '"'
            if reg:
                self.registers[reg] = text
                self.registers['"'] = text
                self.register = text  # v3: 同步旧属性
                self.register_is_line = True'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("Vim v3: 修复 yy+p 粘贴")
    print(f"  项目目录: {ROOT}")

    if args.dry_run:
        print()
        print_info("将修复 vim_mode.py:")
        print_info("  1. _paste_after / _paste_before 从 registers['\"'] 读")
        print_info("  2. yank 时同步 self.register（兼容旧代码）")
        return 0

    path = ROOT / "core" / "vim_mode.py"

    print_header("修复 1: _paste_after / _paste_before")
    r1 = apply_replace(path, OLD_PASTE, NEW_PASTE,
                       PASTE_MARKER, args.no_backup)

    print_header("修复 2a: 字符操作同步 self.register")
    r2 = apply_replace(path, OLD_SYNC_1, NEW_SYNC_1,
                       SYNC_MARKER, args.no_backup)

    print_header("修复 2b: 行操作同步 self.register")
    r3 = apply_replace(path, OLD_SYNC_2, NEW_SYNC_2,
                       SYNC_MARKER + " (line)", args.no_backup)

    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    for pid, r in [("paste", r1), ("sync-char", r2), ("sync-line", r3)]:
        marker = {'applied': '✓', 'skipped': '-', 'failed': '✗'}[r]
        print(f"  {marker} {pid}: [{r}]")

    if 'failed' in (r1, r2, r3):
        return 1

    print()
    print("=" * 60)
    print("✓ 完成")
    print("=" * 60)
    print()
    print("验证:")
    print("  python -m pytest tests/test_vim_mode.py -v")
    print("  python tests/run_all.py")
    print()
    print("预期: 198 passed")
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