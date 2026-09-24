#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P0 修复脚本（第三轮）
============================================================
修复新建文件后草稿保存报"提供者未打开"的问题。

  1. ui/editor_view.py  —— EditorWidget.__init__ 创建
                            MemoryProvider 后调用 open()
  2. core/document.py   —— _save_draft 加防御性检查

用法：
    python fix_p0_3.py --dry-run
    python fix_p0_3.py
============================================================
"""

import os
import sys
import shutil
import argparse
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))


def print_header(title):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def print_ok(msg):
    print("  [OK]   " + msg)


def print_skip(msg):
    print("  [SKIP] " + msg)


def print_warn(msg):
    print("  [WARN] " + msg)


def print_fail(msg):
    print("  [FAIL] " + msg)


def backup_file(path):
    backup = path + ".bak.p0_3"
    try:
        shutil.copy2(path, backup)
        return backup
    except Exception as e:
        print_warn(f"备份失败: {e}")
        return None


def restore_backup(path, backup):
    if backup and os.path.exists(backup):
        try:
            shutil.copy2(backup, path)
            return True
        except Exception:
            return False
    return False


def validate_syntax(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            source = f.read()
        compile(source, path, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def apply_fix(path, old_block, new_block, description,
              applied_marker=None, dry_run=False, no_backup=False):
    if not os.path.exists(path):
        print_fail(f"文件不存在: {path}")
        return False

    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return False

    marker = applied_marker if applied_marker else new_block
    if marker in content:
        print_skip(f"已修复，跳过: {description}")
        return False

    if old_block not in content:
        print_fail(f"未找到锚点: {description}")
        print("         期望片段（前 10 行）：")
        preview = old_block[:300]
        for line in preview.split('\n')[:10]:
            print(f"         | {line}")
        return False

    if dry_run:
        print_ok(f"[DRY-RUN] 会修改: {description}")
        return True

    backup = None
    if not no_backup:
        backup = backup_file(path)
        if backup:
            print_ok(f"已备份: {os.path.basename(backup)}")

    new_content = content.replace(old_block, new_block, 1)

    try:
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(new_content)
    except Exception as e:
        print_fail(f"写入失败: {e}")
        if backup:
            restore_backup(path, backup)
        return False

    ok, err = validate_syntax(path)
    if not ok:
        print_fail(f"语法检查失败: {err}")
        if backup:
            restore_backup(path, backup)
            print_warn("已从备份还原")
        return False

    print_ok(f"已修改: {description}")
    return True


# ============================================================
# 修复 1: ui/editor_view.py —— provider 显式 open
# ============================================================
def fix_editor_view_provider(dry_run=False, no_backup=False):
    """EditorWidget.__init__ 创建 MemoryProvider 后调用 open()"""
    path = os.path.join(ROOT, "ui", "editor_view.py")

    old_block = '''        # 偏好设置
        self.prefs = prefs or Preferences()

        # 内容提供者
        self.prov = provider or MemoryProvider()'''

    new_block = '''        # 偏好设置
        self.prefs = prefs or Preferences()

        # 内容提供者
        if provider is not None:
            # 显式传入的 provider（如打开文件时）
            self.prov = provider
        else:
            # 未指定：创建空的内存提供者，必须显式 open()
            # 否则 provider 状态为 CLOSED，_save_draft 时会报
            # "提供者未打开"
            self.prov = MemoryProvider()
            try:
                self.prov.open(initial_text="")
            except Exception as _e:
                print(f"[EditorWidget] 初始化 MemoryProvider 失败: {_e}")'''

    return apply_fix(
        path, old_block, new_block,
        "ui/editor_view.py: provider 显式 open",
        applied_marker="未指定：创建空的内存提供者，必须显式 open()",
        dry_run=dry_run, no_backup=no_backup,
    )


# ============================================================
# 修复 2: core/document.py —— _save_draft 防御性检查
# ============================================================
def fix_document_draft_guard(dry_run=False, no_backup=False):
    """_save_draft 加 provider 状态检查"""
    path = os.path.join(ROOT, "core", "document.py")

    old_block = '''    def _save_draft(self):
        """保存草稿到临时目录"""
        if not self.meta.modified:
            self._draft_timer.stop()
            return

        try:'''

    new_block = '''    def _save_draft(self):
        """保存草稿到临时目录"""
        if not self.meta.modified:
            self._draft_timer.stop()
            return

        # 防御：provider 未打开时静默跳过，避免无意义的错误日志
        if not self.provider or not self.provider.is_open:
            self._draft_timer.stop()
            return

        try:'''

    return apply_fix(
        path, old_block, new_block,
        "core/document.py: _save_draft 防御性检查",
        applied_marker="# 防御：provider 未打开时静默跳过",
        dry_run=dry_run, no_backup=no_backup,
    )


# ============================================================
# 自检
# ============================================================
def self_check():
    print_header("自检")

    try:
        with open(os.path.join(ROOT, "ui", "editor_view.py"),
                  'r', encoding='utf-8') as f:
            content = f.read()
        if "未指定：创建空的内存提供者，必须显式 open()" in content:
            print_ok("ui/editor_view.py: provider 显式 open 已添加")
        else:
            print_fail("ui/editor_view.py: 未找到修复标记")
    except Exception as e:
        print_fail(f"ui/editor_view.py 检查失败: {e}")

    try:
        with open(os.path.join(ROOT, "core", "document.py"),
                  'r', encoding='utf-8') as f:
            content = f.read()
        if "# 防御：provider 未打开时静默跳过" in content:
            print_ok("core/document.py: _save_draft 防御检查已添加")
        else:
            print_fail("core/document.py: 未找到修复标记")
    except Exception as e:
        print_fail(f"core/document.py 检查失败: {e}")

    print()
    print("编译检查：")
    for rel in ["ui/editor_view.py", "core/document.py"]:
        path = os.path.join(ROOT, rel)
        ok, err = validate_syntax(path)
        if ok:
            print_ok(rel)
        else:
            print_fail(f"{rel}: {err}")


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="青草编辑器 P0 修复（第三轮）"
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='仅检测，不修改')
    parser.add_argument('--no-backup', action='store_true',
                        help='不生成备份文件')
    args = parser.parse_args()

    print_header("青草编辑器 P0 修复（第三轮）")
    print(f"  项目根目录: {ROOT}")
    print(f"  模式:       {'DRY-RUN' if args.dry_run else '实际修复'}")
    print(f"  备份:       {'禁用' if args.no_backup else '启用'}")

    fixed = 0
    skipped = 0
    failed = 0

    print_header("修复 1/2: ui/editor_view.py —— provider 显式 open")
    try:
        if fix_editor_view_provider(
                dry_run=args.dry_run, no_backup=args.no_backup):
            fixed += 1
        else:
            skipped += 1
    except Exception as e:
        print_fail(f"异常: {e}")
        traceback.print_exc()
        failed += 1

    print_header("修复 2/2: core/document.py —— _save_draft 防御检查")
    try:
        if fix_document_draft_guard(
                dry_run=args.dry_run, no_backup=args.no_backup):
            fixed += 1
        else:
            skipped += 1
    except Exception as e:
        print_fail(f"异常: {e}")
        traceback.print_exc()
        failed += 1

    print_header("汇总")
    print(f"  已修复: {fixed}")
    print(f"  已跳过: {skipped}")
    print(f"  失败:   {failed}")

    if not args.dry_run and fixed > 0:
        self_check()

    print()
    if failed > 0:
        print("✗ 存在失败项，请检查上述错误")
        return 1

    if args.dry_run:
        print("✓ DRY-RUN 完成")
        print("  运行 `python fix_p0_3.py` 执行实际修复")
    elif fixed > 0:
        print("✓ 修复完成，请重新启动编辑器验证：")
        print("    python main.py")
        print()
        print("  验证清单：")
        print("    1. 新建一个 .py 文件")
        print("    2. 输入一些内容")
        print("    3. 等待 60 秒以上")
        print("    4. 观察控制台，应不再出现")
        print("       '提供者未打开' 相关错误")
        print()
        print("  备份文件：")
        print("    del ui\\editor_view.py.bak.p0_3")
        print("    del core\\document.py.bak.p0_3")
    else:
        print("✓ 所有修复项均已完成")

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