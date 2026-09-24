#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Vim v2: 修复 2 个真 bug + 1 个测试 fixture
==========================================
真 bug:
  A. _search_next 从 pos 开始 → 命中当前匹配，不前进。
     改为从 pos+1 开始。
  B. "a 寄存器：两次 alnum 输入会覆盖 pending_register。
     改为独立 _waiting_for_register 状态。

测试:
  C. tests/test_vim_mode.py fixture 里 setText 后光标在末尾，
     导致 dd/yy/dw 操作最后一行而非第一行。
     显式 setCursorPosition(0, 0)。

用法:
    python fix_vim_v2.py --dry-run
    python fix_vim_v2.py
"""

import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.v2"


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
# A: _search_next 从 pos+1 开始
# ============================================================
A_MARKER = "# A(v2): 从 pos+1 开始，避免命中当前匹配"

A_OLD = '''    def _search_next(self):
        if self.last_search:
            pos = self.editor.SendScintilla(
                self.editor.SCI_GETCURRENTPOS
            )
            target = self.last_search.encode('utf-8')
            length = self.editor.SendScintilla(
                self.editor.SCI_GETLENGTH
            )
            self.editor.SendScintilla(
                self.editor.SCI_SETTARGETSTART, pos
            )
            self.editor.SendScintilla(
                self.editor.SCI_SETTARGETEND, length
            )
            found = self.editor.SendScintilla(
                self.editor.SCI_SEARCHINTARGET, len(target), target
            )
            if found >= 0:
                self.editor.SendScintilla(
                    self.editor.SCI_GOTOPOS, found
                )'''

A_NEW = '''    def _search_next(self):
        # A(v2): 从 pos+1 开始，避免命中当前匹配
        if self.last_search:
            pos = self.editor.SendScintilla(
                self.editor.SCI_GETCURRENTPOS
            )
            target = self.last_search.encode('utf-8')
            length = self.editor.SendScintilla(
                self.editor.SCI_GETLENGTH
            )
            start = pos + 1
            if start >= length:
                # 循环到开头
                start = 0
            self.editor.SendScintilla(
                self.editor.SCI_SETTARGETSTART, start
            )
            self.editor.SendScintilla(
                self.editor.SCI_SETTARGETEND, length
            )
            found = self.editor.SendScintilla(
                self.editor.SCI_SEARCHINTARGET, len(target), target
            )
            if found < 0 and start > 0:
                # 到末尾未找到 → 从头再搜一次
                self.editor.SendScintilla(
                    self.editor.SCI_SETTARGETSTART, 0
                )
                self.editor.SendScintilla(
                    self.editor.SCI_SETTARGETEND, start
                )
                found = self.editor.SendScintilla(
                    self.editor.SCI_SEARCHINTARGET,
                    len(target), target
                )
            if found >= 0:
                self.editor.SendScintilla(
                    self.editor.SCI_GOTOPOS, found
                )'''


# ============================================================
# B: __init__ 加 _waiting_for_register
# ============================================================
B1_MARKER = "self._waiting_for_register = False"

B1_OLD = '''        # v2 补全: 多寄存器 + 操作符/文本对象状态
        self.registers = {'"': ''}
        self._pending_operator = None
        self._operator_count = 1
        self._pending_register = None
        self._pending_textobj_prefix = None'''

B1_NEW = '''        # v2 补全: 多寄存器 + 操作符/文本对象状态
        self.registers = {'"': ''}
        self._pending_operator = None
        self._operator_count = 1
        self._pending_register = None
        self._pending_textobj_prefix = None
        # B(v2): 独立"等待寄存器名"状态
        self._waiting_for_register = False'''


# ============================================================
# B: _handle_normal 里处理等待寄存器
# ============================================================
B2_MARKER = "# B(v2): 等待寄存器名输入"

B2_OLD = '''        # ==== A3: v2 操作符 + 文本对象 ====
        if self._pending_textobj_prefix is not None:
            return self._handle_textobj(text)

        if self._pending_operator is not None:
            return self._handle_after_operator(key, text)

        if self._pending_register is not None:
            if text and (text.isalnum() or
                          text in ('"', '+', '-', '*', '0', '_')):
                self._pending_register = text
                return True
            self._pending_register = None
            self.status_message.emit("")
            return True

        if (text and text.isdigit()
                and not (text == "0" and not self.count_buffer)):
            self.count_buffer += text
            self.status_message.emit("计数: " + self.count_buffer)
            return True

        count = int(self.count_buffer) if self.count_buffer else 1
        self.count_buffer = ""

        # 寄存器前缀
        if text == '"':
            self._pending_register = ""
            self.status_message.emit('"')
            return True'''

B2_NEW = '''        # ==== A3: v2 操作符 + 文本对象 ====
        if self._pending_textobj_prefix is not None:
            return self._handle_textobj(text)

        if self._pending_operator is not None:
            return self._handle_after_operator(key, text)

        # B(v2): 等待寄存器名输入
        if self._waiting_for_register:
            self._waiting_for_register = False
            if text and (text.isalnum() or
                          text in ('"', '+', '-', '*', '0', '_')):
                self._pending_register = text
                return True
            self._pending_register = None
            self.status_message.emit("")
            return True

        if (text and text.isdigit()
                and not (text == "0" and not self.count_buffer)):
            self.count_buffer += text
            self.status_message.emit("计数: " + self.count_buffer)
            return True

        count = int(self.count_buffer) if self.count_buffer else 1
        self.count_buffer = ""

        # 寄存器前缀
        if text == '"':
            self._waiting_for_register = True
            self.status_message.emit('"')
            return True'''


# ============================================================
# B: _clear_pending 里也清理
# ============================================================
B3_MARKER = "self._waiting_for_register = False\n        self.count_buffer"

B3_OLD = '''    def _clear_pending(self):
        self._pending_operator = None
        self._operator_count = 1
        self._pending_register = None
        self._pending_textobj_prefix = None
        self.count_buffer = ""
        self.status_message.emit("")'''

B3_NEW = '''    def _clear_pending(self):
        self._pending_operator = None
        self._operator_count = 1
        self._pending_register = None
        self._pending_textobj_prefix = None
        self._waiting_for_register = False
        self.count_buffer = ""
        self.status_message.emit("")'''


# ============================================================
# C: 测试 fixture 加 setCursorPosition
# ============================================================
C_MARKER = "# C(v2): 显式设置光标到 (0, 0)"

C_OLD = '''    editor = QsciScintilla()
    editor.setUtf8(True)
    editor.setText("hello world\\nfoo bar\\nbaz qux\\n")

    vm = VimMode(editor)
    vm.set_enabled(True)
    return vm, editor, VimState'''

C_NEW = '''    editor = QsciScintilla()
    editor.setUtf8(True)
    editor.setText("hello world\\nfoo bar\\nbaz qux\\n")
    # C(v2): 显式设置光标到 (0, 0)
    # setText 后光标位置在不同 Qt/Scintilla 版本下不一致，
    # 可能是末尾或 0。明确指定，避免 dd/yy/dw 操作错行。
    editor.setCursorPosition(0, 0)

    vm = VimMode(editor)
    vm.set_enabled(True)
    return vm, editor, VimState'''


# ============================================================
# 主流程
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("Vim v2: 修复 5 个失败")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")

    if args.dry_run:
        print()
        print_info("[DRY-RUN] 将修复：")
        print_info("  A. vim_mode.py: _search_next 从 pos+1 开始")
        print_info("  B. vim_mode.py: \"a 寄存器：独立 waiting 状态")
        print_info("  C. tests/test_vim_mode.py: fixture 加 setCursorPosition")
        print()
        return 0

    vim = ROOT / "core" / "vim_mode.py"
    tests = ROOT / "tests" / "test_vim_mode.py"

    print_header("A: _search_next 从 pos+1 开始")
    r1 = apply_replace(vim, A_OLD, A_NEW, A_MARKER, args.no_backup)

    print_header("B1: __init__ 加 _waiting_for_register")
    r2 = apply_replace(vim, B1_OLD, B1_NEW, B1_MARKER, args.no_backup)

    print_header("B2: _handle_normal 寄存器等待状态")
    r3 = apply_replace(vim, B2_OLD, B2_NEW, B2_MARKER, args.no_backup)

    print_header("B3: _clear_pending 清理等待状态")
    r4 = apply_replace(vim, B3_OLD, B3_NEW, B3_MARKER, args.no_backup)

    print_header("C: 测试 fixture 光标位置")
    r5 = apply_replace(tests, C_OLD, C_NEW, C_MARKER, args.no_backup)

    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    results = [
        ("A", "search_next", r1),
        ("B1", "init waiting", r2),
        ("B2", "handle_normal", r3),
        ("B3", "clear_pending", r4),
        ("C", "test fixture", r5),
    ]
    failed = 0
    for pid, name, r in results:
        marker = {'applied': '✓', 'skipped': '-', 'failed': '✗'}[r]
        print(f"  {marker} {pid}: {name} [{r}]")
        if r == 'failed':
            failed += 1

    if failed:
        print(f"\n✗ 有 {failed} 项失败")
        return 1

    print()
    print("=" * 60)
    print("✓ Vim v2 修复完成")
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