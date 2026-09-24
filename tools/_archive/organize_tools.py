#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
整理 tools/ 目录，构建统一 CLI
============================================================
1. 创建 tools/_archive/
2. 移动一次性脚本到 _archive/
3. 生成 tools/qingcao.py（CLI 主入口）
4. 生成 tools/README.md
5. 生成 tools/_archive/README.md

用法：
    python tools/organize_tools.py --dry-run
    python tools/organize_tools.py
"""

import os
import sys
import shutil
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
ARCHIVE = TOOLS / "_archive"


# 归档的一次性脚本
ARCHIVE_SCRIPTS = [
    "fix_ai_plugin.py",
    "fix_gbk.py",
    "fix_health.py",
    "fix_p0.py",
    "fix_p0_2.py",
    "fix_p0_3.py",
    "fix_p2p3.py",
    "fix_p3_3.py",
    "create_all_plugins.py",
]


# ============================================================
# qingcao.py 内容（列表 join 避免三引号嵌套）
# ============================================================
QINGCAO_PY = "\n".join([
    '#!/usr/bin/env python',
    '# -*- coding: utf-8 -*-',
    '"""',
    '青草编辑器 - 开发工具 CLI',
    '============================================================',
    '',
    '用法：',
    '    python tools/qingcao.py <command> [args...]',
    '',
    '命令：',
    '    check            依赖检查',
    '    health           项目健康扫描',
    '    diagnose-ai      AI 配置诊断',
    '    diagnose-proxy   代理环境诊断',
    '    quick-check      快速自检',
    '    new-plugin NAME  创建插件骨架',
    '    list             列出所有命令',
    '',
    '示例：',
    '    python tools/qingcao.py check',
    '    python tools/qingcao.py health',
    '    python tools/qingcao.py diagnose-ai',
    '    python tools/qingcao.py new-plugin my_plugin',
    '"""',
    '',
    'import os',
    'import sys',
    'import subprocess',
    '',
    '',
    'TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))',
    'ROOT = os.path.dirname(TOOLS_DIR)',
    '',
    '',
    '# 命令 -> (脚本文件名, 说明)',
    'COMMANDS = {',
    "    'check':          ('check_deps.py',     '依赖检查'),",
    "    'health':         ('health_check.py',   '项目健康扫描'),",
    "    'diagnose-ai':    ('diagnose_ai.py',    'AI 配置诊断'),",
    "    'diagnose-proxy': ('diagnose_proxy.py', '代理环境诊断'),",
    "    'quick-check':    ('quick_check.py',    '快速自检'),",
    "    'new-plugin':     ('create_plugin.py',  '创建插件骨架'),",
    '}',
    '',
    '',
    'def print_usage():',
    '    print(__doc__)',
    '',
    '',
    'def print_commands():',
    "    print('可用命令：')",
    '    for cmd, (_, desc) in sorted(COMMANDS.items()):',
    "        print('  {:16s} {}'.format(cmd, desc))",
    '',
    '',
    'def run_script(script_name, extra_args):',
    '    """通过 subprocess 调用 tools/ 下的脚本"""',
    '    script_path = os.path.join(TOOLS_DIR, script_name)',
    '    if not os.path.exists(script_path):',
    "        print('[ERROR] 脚本不存在: {}'.format(script_path))",
    '        return 1',
    '    cmd = [sys.executable, script_path] + list(extra_args)',
    '    try:',
    '        return subprocess.run(cmd, cwd=ROOT).returncode',
    '    except KeyboardInterrupt:',
    "        print('\\n用户中断')",
    '        return 130',
    '',
    '',
    'def main():',
    '    if len(sys.argv) < 2:',
    '        print_usage()',
    '        return 1',
    '',
    '    command = sys.argv[1]',
    '    extra = sys.argv[2:]',
    '',
    "    if command in ('-h', '--help', 'help'):",
    '        print_usage()',
    '        return 0',
    '',
    "    if command == 'list':",
    '        print_commands()',
    '        return 0',
    '',
    '    if command not in COMMANDS:',
    "        print('[ERROR] 未知命令: {}'.format(command))",
    '        print()',
    '        print_commands()',
    '        return 1',
    '',
    '    script_name, _ = COMMANDS[command]',
    '    return run_script(script_name, extra)',
    '',
    '',
    "if __name__ == '__main__':",
    '    sys.exit(main())',
    '',
])


# ============================================================
# tools/README.md
# ============================================================
TOOLS_README = "\n".join([
    '# tools/ - 开发工具集',
    '',
    '青草编辑器的辅助工具目录。',
    '',
    '## 统一 CLI',
    '',
    '所有常用工具通过 `qingcao.py` 统一调用：',
    '',
    '```bash',
    '# 列出所有命令',
    'python tools/qingcao.py list',
    '',
    '# 依赖检查',
    'python tools/qingcao.py check',
    '',
    '# 项目健康扫描',
    'python tools/qingcao.py health',
    '',
    '# AI 配置诊断',
    'python tools/qingcao.py diagnose-ai',
    '',
    '# 代理环境诊断',
    'python tools/qingcao.py diagnose-proxy',
    '',
    '# 快速自检',
    'python tools/qingcao.py quick-check',
    '',
    '# 创建插件骨架',
    'python tools/qingcao.py new-plugin my_plugin',
    '```',
    '',
    '## 目录说明',
    '',
    '| 文件 | 说明 |',
    '|------|------|',
    '| `qingcao.py` | CLI 主入口 |',
    '| `check_deps.py` | 依赖版本检查 |',
    '| `health_check.py` | 项目健康扫描 |',
    '| `diagnose_ai.py` | AI 配置诊断 |',
    '| `diagnose_proxy.py` | 代理环境诊断 |',
    '| `quick_check.py` | 快速验证修复 |',
    '| `create_plugin.py` | 插件脚手架 |',
    '| `_archive/` | 一次性修复脚本归档 |',
    '',
    '## 单独运行',
    '',
    '每个脚本仍可独立执行：',
    '',
    '```bash',
    'python tools/check_deps.py',
    'python tools/health_check.py',
    '```',
    '',
    '## 归档脚本（`_archive/`）',
    '',
    '2026-09 的 P0/P2/P3 修复脚本已完成使命，',
    '归档保留以备参考。**日常不需要执行**。',
    '',
])


# ============================================================
# _archive/README.md
# ============================================================
ARCHIVE_README = "\n".join([
    '# tools/_archive/ - 一次性脚本归档',
    '',
    '本目录保存已完成使命的一次性脚本，**仅供历史参考**。',
    '',
    '## 脚本列表',
    '',
    '| 脚本 | 用途 | 状态 |',
    '|------|------|------|',
    '| `fix_p0.py` | EditorProxy.prov 别名 + OutlinePanel 修复 | ✅ 已应用 |',
    '| `fix_p0_2.py` | prov setter + tabs/plugins 迁移 | ✅ 已应用 |',
    '| `fix_p0_3.py` | provider 显式 open + 草稿保存防御 | ✅ 已应用 |',
    '| `fix_p2p3.py` | AI 404 提示优化 + PNG 清理 | ✅ 已应用 |',
    '| `fix_p3_3.py` | 状态栏组件集成 + 冗余文件清理 | ✅ 已应用 |',
    '| `fix_ai_plugin.py` | AI 插件诊断（缩进/隐藏字符） | ✅ 已应用 |',
    '| `fix_gbk.py` | 批量 GBK → UTF-8 转换 | ✅ 已应用 |',
    '| `fix_health.py` | .gitignore + LICENSE + 文件整理 | ✅ 已应用 |',
    '| `create_all_plugins.py` | 一键创建所有插件骨架 | ✅ 已完成 |',
    '',
    '## 如果需要重新执行',
    '',
    '**不推荐**——这些脚本已经被 `tools/` 下的正式工具替代：',
    '',
    '- `fix_health.py` → `qingcao.py health`',
    '- `fix_ai_plugin.py` → `qingcao.py diagnose-ai`',
    '- 其他 `fix_*` → 均已写入代码，重复执行会显示"已跳过"',
    '',
    '## 删除条件',
    '',
    '满足以下任一即可安全删除本目录：',
    '',
    '1. 项目稳定运行 1 个月无相关回归',
    '2. 项目已发新版本并通过完整回归测试',
    '3. 不再需要追溯历史修复记录',
    '',
])


# ============================================================
# 工具函数
# ============================================================
def print_header(t):
    print()
    print("=" * 60)
    print(t)
    print("=" * 60)


def print_ok(m):
    print("  [OK]   " + m)


def print_skip(m):
    print("  [SKIP] " + m)


def print_fail(m):
    print("  [FAIL] " + m)


def write_file(path, content, dry_run=False):
    """写入文件（幂等：内容相同则跳过）"""
    if path.exists():
        try:
            existing = path.read_text(encoding='utf-8')
            if existing == content:
                print_skip(f"内容未变: {path.name}")
                return False
        except Exception:
            pass

    if dry_run:
        print_ok(f"[DRY-RUN] 会生成: {path.relative_to(ROOT)}")
        return True

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
        print_ok(f"已生成: {path.relative_to(ROOT)}")
        return True
    except Exception as e:
        print_fail(f"写入失败 {path.name}: {e}")
        return False


def move_to_archive(name, dry_run=False):
    """移动脚本到 _archive/"""
    src = TOOLS / name
    dst = ARCHIVE / name

    if not src.exists():
        print_skip(f"源文件不存在: {name}")
        return False

    if dst.exists():
        print_skip(f"已归档: {name}")
        return False

    if dry_run:
        print_ok(f"[DRY-RUN] 会移动: {name} -> _archive/")
        return True

    try:
        shutil.move(str(src), str(dst))
        print_ok(f"已归档: {name}")
        return True
    except Exception as e:
        print_fail(f"移动失败 {name}: {e}")
        return False


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="整理 tools/ 目录，构建统一 CLI"
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='仅检测，不修改')
    parser.add_argument('--no-archive', action='store_true',
                        help='不归档一次性脚本')
    args = parser.parse_args()

    print_header("整理 tools/ 目录")
    print(f"  项目根目录: {ROOT}")
    print(f"  tools/ 目录: {TOOLS}")
    print(f"  模式:       "
          f"{'DRY-RUN' if args.dry_run else '实际整理'}")

    changed = 0

    # ---- 1. 创建 _archive/ ----
    print_header("步骤 1: 创建 _archive/ 目录")
    if ARCHIVE.exists():
        print_skip("_archive/ 已存在")
    elif args.dry_run:
        print_ok("[DRY-RUN] 会创建: tools/_archive/")
        changed += 1
    else:
        try:
            ARCHIVE.mkdir(parents=True, exist_ok=True)
            print_ok("已创建: tools/_archive/")
            changed += 1
        except Exception as e:
            print_fail(f"创建失败: {e}")

    # ---- 2. 归档一次性脚本 ----
    if not args.no_archive:
        print_header("步骤 2: 归档一次性脚本")
        archived = 0
        for name in ARCHIVE_SCRIPTS:
            if move_to_archive(name, dry_run=args.dry_run):
                archived += 1
        print()
        print(f"  已归档 {archived} 个脚本")
        changed += archived

    # ---- 3. 生成 qingcao.py ----
    print_header("步骤 3: 生成 tools/qingcao.py")
    if write_file(TOOLS / "qingcao.py", QINGCAO_PY,
                  dry_run=args.dry_run):
        changed += 1

    # ---- 4. 生成 tools/README.md ----
    print_header("步骤 4: 生成 tools/README.md")
    if write_file(TOOLS / "README.md", TOOLS_README,
                  dry_run=args.dry_run):
        changed += 1

    # ---- 5. 生成 _archive/README.md ----
    if not args.no_archive:
        print_header("步骤 5: 生成 _archive/README.md")
        if write_file(ARCHIVE / "README.md", ARCHIVE_README,
                      dry_run=args.dry_run):
            changed += 1

    # ---- 汇总 ----
    print_header("汇总")
    print(f"  共变更 {changed} 项")

    if args.dry_run:
        print()
        print("✓ DRY-RUN 完成")
        print("  运行 `python tools\\organize_tools.py` 执行")
    elif changed > 0:
        print()
        print("✓ 整理完成")
        print()
        print("  验证：")
        print("    dir tools\\")
        print("    dir tools\\_archive\\")
        print("    python tools\\qingcao.py list")
        print("    python tools\\qingcao.py health")
    else:
        print()
        print("✓ 已经是整理后的状态")

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