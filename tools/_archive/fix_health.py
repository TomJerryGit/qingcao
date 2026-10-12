#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
健康检查后续修复
============================================================
处理 3 项：

  1. 修复 .gitignore 编码（GBK → UTF-8，去重）
  2. 创建 LICENSE（MIT）
  3. 移动 quick_check.py 到 tools/

用法：
    python tools/fix_health.py --dry-run
    python tools/fix_health.py
============================================================
"""

import os
import sys
import shutil
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def print_header(t):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


def print_ok(m):
    print("  [OK]   " + m)


def print_skip(m):
    print("  [SKIP] " + m)


def print_warn(m):
    print("  [WARN] " + m)


def print_fail(m):
    print("  [FAIL] " + m)


def print_info(m):
    print("  [INFO] " + m)


# ============================================================
# 修复 1: .gitignore 编码
# ============================================================
GITIGNORE_CONTENT = """# ============================================================
# 青草编辑器 - Git 忽略规则
# ============================================================

# ---- Python ----
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# ---- 虚拟环境 ----
venv/
.venv/
env/
.env/
ENV/

# ---- IDE ----
.idea/
.vscode/
*.swp
*.swo
*~

# ---- 测试与覆盖率 ----
.pytest_cache/
.coverage
coverage.xml
htmlcov/
.tox/
.mypy_cache/
.ruff_cache/

# ---- 应用运行时数据 ----
logs/
backup/
data/
session.json
crash.log
keybindings.json
plugin_config.json
sync_config.json
snippets.json

# ---- 备份文件（修复脚本生成）----
*.bak.p0
*.bak.p0_2
*.bak.p0_3
*.bak.p2p3
*.bak.p3
*.bak

# ---- 打包产物 ----
*.spec.bak
installer/*.exe
installer/*.deb
installer/*.dmg

# ---- 操作系统 ----
.DS_Store
Thumbs.db
desktop.ini

# ---- 用户目录（开发测试用）----
1.0 QingCaoEditor_Others/
_archived_tools/
QingCaoEditor_RCWJ/
"""


def fix_gitignore(dry_run=False):
    print_header("修复 1/3: .gitignore 编码")

    path = ROOT / ".gitignore"

    # 检查当前编码
    if path.exists():
        try:
            with open(path, 'rb') as f:
                raw = f.read()
            # 尝试 UTF-8
            try:
                raw.decode('utf-8')
                print_info("当前 .gitignore 是 UTF-8")
                current_ok = True
            except UnicodeDecodeError:
                print_warn("当前 .gitignore 不是 UTF-8（可能是 GBK）")
                current_ok = False
        except Exception as e:
            print_warn(f"读取失败: {e}")
            current_ok = False
    else:
        print_info(".gitignore 不存在，将创建")
        current_ok = False

    if current_ok:
        print_skip("无需修复")
        return False

    if dry_run:
        print_ok("[DRY-RUN] 会重写 .gitignore 为 UTF-8")
        return True

    # 备份
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        try:
            shutil.copy2(path, backup)
            print_ok(f"已备份: {backup.name}")
        except Exception as e:
            print_warn(f"备份失败: {e}")

    # 写入
    try:
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(GITIGNORE_CONTENT)
        print_ok(f"已重写 .gitignore（{len(GITIGNORE_CONTENT)} 字符）")
        return True
    except Exception as e:
        print_fail(f"写入失败: {e}")
        return False


# ============================================================
# 修复 2: 创建 LICENSE
# ============================================================
LICENSE_CONTENT = """MIT License

Copyright (c) 2024-2026 hedongwei

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def create_license(dry_run=False):
    print_header("修复 2/3: 创建 LICENSE")

    path = ROOT / "LICENSE"

    if path.exists():
        print_skip("LICENSE 已存在")
        return False

    if dry_run:
        print_ok("[DRY-RUN] 会创建 LICENSE（MIT）")
        return True

    try:
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(LICENSE_CONTENT)
        print_ok("已创建 LICENSE（MIT，2024-2026 hedongwei）")
        return True
    except Exception as e:
        print_fail(f"创建失败: {e}")
        return False


# ============================================================
# 修复 3: 移动 quick_check.py
# ============================================================
def move_quick_check(dry_run=False):
    print_header("修复 3/3: 移动 quick_check.py 到 tools/")

    src = ROOT / "quick_check.py"
    dst = ROOT / "tools" / "quick_check.py"

    if not src.exists():
        print_skip("quick_check.py 不存在（已移动或已删除）")
        return False

    if dst.exists():
        print_warn("tools/quick_check.py 已存在，将覆盖")
        if dry_run:
            print_ok("[DRY-RUN] 会覆盖 tools/quick_check.py")
            return True

    if dry_run:
        print_ok("[DRY-RUN] 会移动 quick_check.py → tools/")
        return True

    try:
        # 确保 tools/ 存在
        dst.parent.mkdir(exist_ok=True)
        shutil.move(str(src), str(dst))
        print_ok("已移动: quick_check.py → tools/quick_check.py")
        return True
    except Exception as e:
        print_fail(f"移动失败: {e}")
        return False


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="青草编辑器健康检查后续修复"
    )
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("青草编辑器 - 健康检查后续修复")
    print("=" * 60)
    print(f"  项目根目录: {ROOT}")
    print(f"  模式:       "
          f"{'DRY-RUN' if args.dry_run else '实际修复'}")

    fixed = 0

    if fix_gitignore(dry_run=args.dry_run):
        fixed += 1
    if create_license(dry_run=args.dry_run):
        fixed += 1
    if move_quick_check(dry_run=args.dry_run):
        fixed += 1

    print_header("汇总")
    print(f"  已修复: {fixed}")

    if args.dry_run:
        print()
        print("✓ DRY-RUN 完成")
        print("  运行 `python tools/fix_health.py` 执行")
    elif fixed > 0:
        print()
        print("✓ 修复完成")
        print()
        print("  验证:")
        print("    1. type .gitignore      （应无乱码）")
        print("    2. type LICENSE         （MIT 文本）")
        print("    3. dir tools\\*.py       （应有 quick_check.py）")
    else:
        print()
        print("✓ 无需修复")

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