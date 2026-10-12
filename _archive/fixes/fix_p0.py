#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - P0 修复脚本
========================
修复 4 项 P0 问题：

  P0-1  requirements.txt 混入 git diff 残留
        -keyring>=23.0.0
        +keyring>=23.0.0
        → pip install -r requirements.txt 直接报错。

  P0-2  session.json 泄露开发者本机路径
        包含 D:\\QingCaoEditor\\... 等绝对路径 + 时间戳。
        同时补齐 .gitignore 中的运行时产物条目。

  P0-3  README.md 尾部 AI 生成残留
        "变更摘要" 之后是 AI 生成过程元数据（对比表、
        检查清单），以及末尾未闭合的 ``` 围栏。

  P0-4  apply_all_patches.py / _v2.py 的 README marker 错误
        marker="# 青草编辑器 (QingCao Editor)" 与实际不符
        → 幂等检测失效，每次运行都尝试重新清理。

特性：
  - 幂等（重复运行不会重复修改）
  - 每项独立处理，一项失败不影响其他
  - 首次修改前备份为 *.bak.p0
  - Python 文件修改后 compile() 验证

用法：
    python fix_p0.py --dry-run     # 预演
    python fix_p0.py               # 应用
    python fix_p0.py --no-backup   # 不备份
"""

import os
import re
import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.p0"


# ============================================================
# 输出辅助
# ============================================================
def print_header(t):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


def print_ok(m):   print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")


# ============================================================
# 备份与写回
# ============================================================
def backup(path: Path) -> bool:
    """首次修改前备份"""
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
    if not no_backup:
        if not backup(path):
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


# ============================================================
# P0-1: requirements.txt 清理 diff 残留
# ============================================================
def fix_requirements(no_backup: bool) -> str:
    path = ROOT / "requirements.txt"
    if not path.exists():
        print_fail("requirements.txt 不存在")
        return 'failed'

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 'failed'

    # 幂等检测：是否有 diff 残留
    has_minus = '-keyring>=23.0.0' in content
    has_plus = '+keyring>=23.0.0' in content
    # 干净的 keyring 行
    has_clean = bool(re.search(
        r'^keyring>=23\.0\.0\s*$', content, re.MULTILINE
    ))

    if not has_minus and not has_plus:
        if has_clean:
            print_skip("无 diff 残留，已是干净版本")
            return 'skipped'
        print_fail("既无 diff 残留，也无 keyring 行 — 请手动检查")
        return 'failed'

    # 逐行清理
    lines = content.split('\n')
    new_lines = []
    inserted_clean = False
    for line in lines:
        stripped = line.strip()
        if stripped == '-keyring>=23.0.0':
            continue
        if stripped == '+keyring>=23.0.0':
            if not inserted_clean and not has_clean:
                new_lines.append('keyring>=23.0.0')
                inserted_clean = True
            continue
        new_lines.append(line)

    # 如果之前有干净的 keyring 行，上面 inserted_clean 逻辑不会插入重复行
    new_content = '\n'.join(new_lines)

    if new_content == content:
        print_skip("无变化")
        return 'skipped'

    if not write_back(path, new_content, no_backup):
        return 'failed'

    print_ok("已清理 diff 残留")
    return 'applied'


# ============================================================
# P0-2: session.json 删除 + .gitignore 补齐
# ============================================================
GITIGNORE_ADDITIONS = [
    "# ---- 运行时产物 ----",
    "session.json",
    "*.session.json",
    "keybindings.json",
    "crash.log",
    "*.crash.log",
]


def fix_session_json(no_backup: bool) -> str:
    session_path = ROOT / "session.json"
    if not session_path.exists():
        print_skip("session.json 不存在")
        return 'skipped'

    # 内容检查：是否是开发者泄露的版本
    try:
        content = session_path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 'failed'

    is_dev_leak = (
        'D:\\\\QingCaoEditor' in content or
        '1.0 QingCaoEditor_Others' in content
    )

    if is_dev_leak:
        print_info("检测到开发者本机路径泄露")
    else:
        print_info("session.json 是运行时产物，删除")

    # 备份后删除
    if not no_backup:
        bak = Path(str(session_path) + BACKUP_SUFFIX)
        if not bak.exists():
            try:
                shutil.copy2(session_path, bak)
                print_info(f"已备份: {bak.name}")
            except Exception as e:
                print_fail(f"备份失败: {e}")
                return 'failed'

    try:
        session_path.unlink()
        print_ok("已删除 session.json")
        return 'applied'
    except Exception as e:
        print_fail(f"删除失败: {e}")
        return 'failed'


def fix_gitignore(no_backup: bool) -> str:
    path = ROOT / ".gitignore"
    if not path.exists():
        print_fail(".gitignore 不存在 — 请先创建")
        return 'failed'

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 'failed'

    # 检查缺失的条目
    missing = []
    for item in GITIGNORE_ADDITIONS:
        if item.startswith('#'):
            continue
        if item not in content:
            missing.append(item)

    if not missing:
        print_skip(".gitignore 已包含全部运行时产物条目")
        return 'skipped'

    # 追加
    if not content.endswith('\n'):
        content += '\n'
    content += '\n' + '\n'.join(GITIGNORE_ADDITIONS) + '\n'

    if not write_back(path, content, no_backup):
        return 'failed'

    print_ok(f"已补齐 {len(missing)} 个条目: {', '.join(missing)}")
    return 'applied'


# ============================================================
# P0-3: README.md 清理 AI 残留
# ============================================================
def fix_readme(no_backup: bool) -> str:
    path = ROOT / "README.md"
    if not path.exists():
        print_fail("README.md 不存在")
        return 'failed'

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 'failed'

    original = content

    # 1) 找"变更摘要"位置
    cut_idx = -1
    for marker in ('\n变更摘要', '\n## 变更摘要'):
        idx = content.find(marker)
        if idx >= 0:
            cut_idx = idx
            break

    if cut_idx >= 0:
        content = content[:cut_idx].rstrip()
        print_info("已截断至 '变更摘要' 之前")

        # 2) 去掉尾部孤立的 ```
        lines = content.split('\n')
        while lines and lines[-1].strip() == '```':
            lines.pop()
        content = '\n'.join(lines).rstrip() + '\n'

    # 3) 检查围栏配对
    fence_count = len(re.findall(r'^```', content, re.MULTILINE))
    if fence_count % 2 == 1:
        content = content.rstrip() + '\n```\n'
        print_info("已补全未闭合的 ``` 围栏")

    if content == original:
        print_skip("README.md 无变化")
        return 'skipped'

    if not write_back(path, content, no_backup):
        return 'failed'

    print_ok("已清理 README.md AI 残留")
    return 'applied'


# ============================================================
# P0-4: apply_all_patches*.py 的 marker 修正
# ============================================================
PATCH_FILES = [
    "apply_all_patches.py",
    "apply_all_patches_v2.py",
]

OLD_MARKER_RE = re.compile(
    r'marker="# 青草编辑器 \(QingCao Editor\)",'
)
NEW_MARKER = 'marker="青草枯荣，野火重生",'


def fix_patch_markers(no_backup: bool) -> str:
    applied_count = 0
    skipped_count = 0
    failed_count = 0

    for rel in PATCH_FILES:
        path = ROOT / rel
        if not path.exists():
            print_skip(f"{rel} 不存在")
            skipped_count += 1
            continue

        try:
            content = path.read_text(encoding='utf-8')
        except Exception as e:
            print_fail(f"{rel} 读取失败: {e}")
            failed_count += 1
            continue

        # 幂等：检查新 marker 是否已存在
        if NEW_MARKER in content:
            print_skip(f"{rel} 已是新 marker")
            skipped_count += 1
            continue

        # 检查旧 marker
        if not OLD_MARKER_RE.search(content):
            print_fail(f"{rel} 未找到旧 marker")
            failed_count += 1
            continue

        new_content = OLD_MARKER_RE.sub(NEW_MARKER, content)

        # 语法验证
        ok, err = validate_python(new_content, str(path))
        if not ok:
            print_fail(f"{rel} 语法错误: {err}")
            failed_count += 1
            continue

        if not write_back(path, new_content, no_backup):
            failed_count += 1
            continue

        print_ok(f"{rel} marker 已修正")
        applied_count += 1

    if failed_count > 0:
        return 'failed'
    if applied_count > 0:
        return 'applied'
    return 'skipped'


# ============================================================
# 主流程
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser(
        description="青草编辑器 P0 修复"
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("青草编辑器 P0 修复")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")
    print(f"  备份:     {'禁用' if args.no_backup else '启用'}")

    if args.dry_run:
        print()
        print_info("[DRY-RUN] 将处理以下 4 项：")
        print_info("  P0-1  requirements.txt 清理 diff 残留")
        print_info("  P0-2  session.json 删除 + .gitignore 补齐")
        print_info("  P0-3  README.md 清理 AI 生成残留")
        print_info("  P0-4  apply_all_patches*.py marker 修正")
        print()
        print("  去掉 --dry-run 即可应用。")
        return 0

    results = {}

    print_header("P0-1: requirements.txt 清理")
    results['P0-1'] = fix_requirements(args.no_backup)

    print_header("P0-2a: session.json 删除")
    results['P0-2a'] = fix_session_json(args.no_backup)

    print_header("P0-2b: .gitignore 补齐")
    results['P0-2b'] = fix_gitignore(args.no_backup)

    print_header("P0-3: README.md 清理")
    results['P0-3'] = fix_readme(args.no_backup)

    print_header("P0-4: apply_all_patches*.py marker 修正")
    results['P0-4'] = fix_patch_markers(args.no_backup)

    # ---- 汇总 ----
    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    for pid, r in results.items():
        marker = {'applied': '✓', 'skipped': '-', 'failed': '✗'}[r]
        print(f"  {marker} {pid}: {r}")

    failed = sum(1 for r in results.values() if r == 'failed')
    applied = sum(1 for r in results.values() if r == 'applied')

    print()
    if failed > 0:
        print("=" * 60)
        print(f"✗ 有 {failed} 项失败，请检查上方输出")
        print("=" * 60)
        return 1

    print("=" * 60)
    print(f"✓ 完成（应用 {applied} 项，跳过 {len(results) - applied} 项）")
    print("=" * 60)
    print()
    print("验证步骤:")
    print("  1. pip install -r requirements.txt --dry-run")
    print("  2. 查看 README.md 尾部，应无 '变更摘要'")
    print("  3. 确认 session.json 已删除")
    print("  4. git status 查看变更")
    print()
    print("清理备份:")
    print("  Windows:       del /s *.bak.p0")
    print("  Linux/macOS:   find . -name '*.bak.p0' -delete")

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