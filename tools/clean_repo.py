#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""仓库清理工具（P2）

默认是 **dry-run**，只报告不修改；加 ``--apply`` 才真正删除。

清理对象:
    1. ``*.bak.*`` / ``*.bak`` 备份文件（修复前共 103 个、约 6.9 万行）
    2. 根目录一次性修复脚本 ``fix_*.py``（已归档到 ``_archive/fixes/``）
    3. 误命名文件（如 ``python fix_batch_1_crash.py``、``findstr``）
    4. 运行时残留（``session.json``、``crash.log``、``msg.txt``、
       ``.coverage``、``.qingcao-tasks.json``）

用法::

    python tools/clean_repo.py            # 预演（默认）
    python tools/clean_repo.py --apply    # 实际删除
    python tools/clean_repo.py --apply --keep-archive  # 保留归档脚本
"""
import fnmatch
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 需要保留的目录（不要在里面删东西）
PROTECTED_DIRS = {'.git', '.github', 'node_modules'}

# 文件名模式（相对仓库根）
BACKUP_PATTERNS = ['*.bak', '*.bak.*', '*.orig', '*.rej']

# 根目录下的一次性脚本
ROOT_JUNK_PATTERNS = [
    'fix_*.py',
    'python fix_*.py',
    'findstr',
    'msg.txt',
    '.qingcao-tasks.json',
    '.coverage',
    'archive_scripts.py',
]

# 即使在根目录也不该删的（显式白名单，防误删）
NEVER_DELETE = {
    'version.py', 'main.py', 'release.py', 'build.py',
    'build_installer.py', 'build_linux.py', 'build_macos.py',
    'archive_scripts.py',   # 虽然是历史脚本，但被 README 引用为归档工具
}


def iter_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in PROTECTED_DIRS]
        for name in filenames:
            yield os.path.join(dirpath, name)


def matches(name, patterns):
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def collect(keep_archive: bool = True):
    """返回 (backups, root_junk) 两个列表"""
    backups = []
    root_junk = []

    for path in iter_files():
        name = os.path.basename(path)
        rel = os.path.relpath(path, ROOT)

        # 备份文件：任意深度
        if matches(name, BACKUP_PATTERNS):
            backups.append(path)
            continue

        # 根目录杂项：只在根目录
        if os.path.dirname(path) != ROOT:
            continue
        if name in NEVER_DELETE:
            continue
        if matches(name, ROOT_JUNK_PATTERNS):
            root_junk.append(path)

    return sorted(backups), sorted(root_junk)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    apply_changes = '--apply' in argv

    backups, junk = collect()

    total_bytes = 0
    for p in backups + junk:
        try:
            total_bytes += os.path.getsize(p)
        except OSError:
            pass

    print("[clean_repo] 仓库根: %s" % ROOT)
    print("[clean_repo] 备份文件: %d 个" % len(backups))
    print("[clean_repo] 根目录杂项: %d 个" % len(junk))
    print("[clean_repo] 合计可回收: %.1f KB" % (total_bytes / 1024.0))

    if not backups and not junk:
        print("[clean_repo] 无需清理")
        return 0

    show = 12
    for label, items in (("备份", backups), ("杂项", junk)):
        for p in items[:show]:
            print("  [%s] %s" % (label, os.path.relpath(p, ROOT)))
        if len(items) > show:
            print("  [%s] ... 其余 %d 个" % (label, len(items) - show))

    if not apply_changes:
        print()
        print("[clean_repo] 这是预演（dry-run）。"
              "确认无误后执行: python tools/clean_repo.py --apply")
        return 0

    removed = 0
    failed = 0
    for p in backups + junk:
        # 安全检查：必须位于仓库内
        if not os.path.abspath(p).startswith(os.path.abspath(ROOT)):
            print("  [SKIP] 越界路径: %s" % p)
            failed += 1
            continue
        try:
            os.remove(p)
            removed += 1
        except OSError as e:
            print("  [FAIL] %s: %s" % (os.path.relpath(p, ROOT), e))
            failed += 1

    print()
    print("[clean_repo] 已删除 %d 个文件，失败 %d 个" % (removed, failed))
    print("[clean_repo] 提示：清理后请运行 "
          "`python -m pytest tests` 与 `python -m ruff check .` 复核")
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
