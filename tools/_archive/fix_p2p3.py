#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P2/P3 问题处理脚本（修正版）
============================================================
自动修复：
  1. P3-1: 清理 resources/icons/qingcao.png 元数据
  2. P2-1b: 改进 AI 助手 404 错误提示（针对 Ollama）

只扫描：
  3. P3-3: 输出 main_window.py 中 _build_status_bar 的当前代码
  4. P3-2: 扫描 ai_actions.py / search_worker.py 的引用情况

用法：
    python fix_p2p3.py --dry-run     # 只检测
    python fix_p2p3.py               # 执行
    python fix_p2p3.py --only-scan   # 只扫描
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


def print_info(msg):
    print("  [INFO] " + msg)


def backup_file(path, suffix=".bak.p2p3"):
    backup = path + suffix
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
        print("         期望片段：")
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
# 修复 1: P3-1 —— 清理 PNG 元数据
# ============================================================
def fix_png_metadata(dry_run=False, no_backup=False):
    candidates = [
        os.path.join(ROOT, "resources", "icons", "qingcao.png"),
        os.path.join(ROOT, "resources", "qingcao.png"),
    ]

    png_path = None
    for c in candidates:
        if os.path.exists(c):
            png_path = c
            break

    if not png_path:
        print_warn("未找到 qingcao.png")
        return False

    print_info(f"目标: {png_path}")

    if dry_run:
        print_ok("[DRY-RUN] 会清理 PNG 元数据")
        return True

    try:
        from PIL import Image
    except ImportError:
        print_warn("缺少 Pillow，请运行: pip install Pillow")
        print_info("（PNG 清理失败不影响功能，仅消除日志警告）")
        return False

    if not no_backup:
        backup_file(png_path, ".bak.p2p3")

    try:
        img = Image.open(png_path)
        img.load()
        img.save(png_path, format='PNG', optimize=True)
        print_ok("已清理 PNG 元数据")
        return True
    except Exception as e:
        print_fail(f"清理失败: {e}")
        return False


# ============================================================
# 修复 2: P2-1b —— AI 助手 404 提示优化
# ============================================================
def fix_ai_404_hint(dry_run=False, no_backup=False):
    path = os.path.join(ROOT, "plugins", "ai_assistant", "__init__.py")

    old_block = (
        '        # 404 / 找不到\n'
        "        if '404' in raw:\n"
        '            return (\n'
        '                f"服务器返回 404（模型或路径不存在）。\\n\\n"\n'
        '                f"请检查 Model 名称是否正确。\\n"\n'
        '                f"当前 base_url: {base_url or \'未知\'}"\n'
        '            )'
    )

    new_block = (
        '        # 404 / 找不到\n'
        "        if '404' in raw or 'not found' in raw.lower():\n"
        "            if provider == 'ollama':\n"
        "                model = getattr(client, 'model', '') if client else ''\n"
        '                return (\n'
        '                    f"Ollama 未找到模型 \'{model}\'。\\n\\n"\n'
        '                    f"请尝试：\\n"\n'
        '                    f"  1. 查看已有模型：ollama list\\n"\n'
        '                    f"  2. 拉取指定模型：ollama pull {model}\\n"\n'
        '                    f"  3. 或在配置界面选择已存在的模型\\n\\n"\n'
        '                    f"配置位置：工具 → AI 助手 → ⚙ 配置 AI..."\n'
        '                )\n'
        '            return (\n'
        '                f"服务器返回 404（模型或路径不存在）。\\n\\n"\n'
        '                f"请检查 Model 名称是否正确。\\n"\n'
        '                f"当前 base_url: {base_url or \'未知\'}"\n'
        '            )'
    )

    return apply_fix(
        path, old_block, new_block,
        "AI 助手 404 错误提示优化",
        applied_marker="Ollama 未找到模型",
        dry_run=dry_run, no_backup=no_backup,
    )


# ============================================================
# 扫描 1: P3-3 —— 输出 _build_status_bar
# ============================================================
def scan_status_bar():
    print_header("扫描 1/2: P3-3 —— 状态栏组件集成")
    print_info("目标: ui/main_window.py 中的 _build_status_bar 方法")

    path = os.path.join(ROOT, "ui", "main_window.py")
    if not os.path.exists(path):
        print_fail(f"文件不存在: {path}")
        return

    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return

    start = None
    for i, line in enumerate(lines):
        if 'def _build_status_bar' in line:
            start = i
            break

    if start is None:
        print_warn("未找到 _build_status_bar 方法")
        return

    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if not line.strip():
            continue
        cur_indent = len(line) - len(line.lstrip())
        if cur_indent <= indent and line.strip().startswith(('def ', 'class ', '@')):
            end = i
            break

    print()
    print(f"  ── _build_status_bar 位于第 {start + 1} 到 {end} 行 ──")
    print()
    for i in range(start, end):
        print(f"  {i + 1:4d} | {lines[i].rstrip()}")

    # 用三引号字符串，避免括号配对问题
    hint = """
  ── 集成建议 ──

  若要让编码/行尾符/Git 分支可点击切换，可将：
    self.encoding_label = QLabel(...)
  替换为：
    from ui.status_bar_widgets import EncodingLabel
    self.encoding_label = EncodingLabel(self)
    self.encoding_label.encoding_changed.connect(self._on_encoding_changed)

  ⚠ 需要在 MainWindow 中新增 _on_encoding_changed 方法：
      def _on_encoding_changed(self, encoding):
          proxy = self.tabs.current_proxy()
          if proxy and proxy.document:
              proxy.document.change_encoding(encoding)

  行尾符（EolLabel）、Git 分支（GitBranchLabel）同理。
"""
    print(hint)


# ============================================================
# 扫描 2: P3-2 —— 冗余文件引用
# ============================================================
def scan_redundant():
    print_header("扫描 2/2: P3-2 —— 冗余文件引用检查")

    targets = [
        ("ui/ai_actions.py", [
            "from ui.ai_actions",
            "import ui.ai_actions",
            "ui.ai_actions",
        ]),
        ("core/search_worker.py", [
            "from core.search_worker",
            "import core.search_worker",
            "core.search_worker",
        ]),
    ]

    SKIP_DIRS = {
        '__pycache__', '.git', '.github', '.venv', 'venv',
        'env', '.env', 'build', 'dist', 'node_modules',
        'backup', 'data', 'logs',
    }

    for rel_path, patterns in targets:
        full_path = os.path.join(ROOT, rel_path)
        print()
        print(f"  ── {rel_path} ──")

        if not os.path.exists(full_path):
            print_skip("文件不存在")
            continue

        try:
            size = os.path.getsize(full_path)
            print_info(f"文件大小: {size} 字节")
        except Exception:
            pass

        references = []
        for root, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for fname in files:
                if not fname.endswith('.py'):
                    continue

                fpath = os.path.join(root, fname)
                if os.path.abspath(fpath) == os.path.abspath(full_path):
                    continue

                try:
                    with open(fpath, 'r', encoding='utf-8',
                              errors='replace') as f:
                        content = f.read()
                except Exception:
                    continue

                for pattern in patterns:
                    if pattern in content:
                        rel = os.path.relpath(fpath, ROOT)
                        references.append(rel)
                        break

        if not references:
            print_ok("未发现引用 ✓ 可安全删除（建议再人工确认）")
        else:
            print_warn(f"发现 {len(references)} 处引用：")
            for ref in sorted(set(references)):
                print(f"      {ref}")
            print_info("请先修改上述引用，再删除")


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="青草编辑器 P2/P3 问题处理"
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='仅检测，不修改')
    parser.add_argument('--no-backup', action='store_true',
                        help='不生成备份')
    parser.add_argument('--only-scan', action='store_true',
                        help='只做扫描，不修改代码')
    args = parser.parse_args()

    print_header("青草编辑器 P2/P3 处理")
    print(f"  项目根目录: {ROOT}")
    print(f"  模式:       "
          f"{'仅扫描' if args.only_scan else ('DRY-RUN' if args.dry_run else '实际修复')}")

    fixed = 0
    skipped = 0

    if not args.only_scan:
        print_header("修复 1/2: P3-1 —— 清理 PNG 元数据")
        try:
            if fix_png_metadata(dry_run=args.dry_run,
                                 no_backup=args.no_backup):
                fixed += 1
            else:
                skipped += 1
        except Exception as e:
            print_fail(f"异常: {e}")
            traceback.print_exc()

    if not args.only_scan:
        print_header("修复 2/2: P2-1b —— AI 404 错误提示优化")
        try:
            if fix_ai_404_hint(dry_run=args.dry_run,
                                no_backup=args.no_backup):
                fixed += 1
            else:
                skipped += 1
        except Exception as e:
            print_fail(f"异常: {e}")
            traceback.print_exc()

    scan_status_bar()
    scan_redundant()

    print_header("汇总")
    if not args.only_scan:
        print(f"  已修复: {fixed}")
        print(f"  已跳过: {skipped}")
    print()
    print("  剩余问题（手动处理）：")
    print("    P2-1a: AI 404 —— 运行 ollama pull llama3.2")
    print("                      或配置界面切换已有模型")
    print("    P2-2:  PluginStore 网络失败 —— 环境问题")
    print()
    print("  剩余问题（人工决策）：")
    print("    P3-2:  按上面扫描结果确认是否删除冗余文件")
    print("    P3-3:  按上面扫描结果决定是否集成状态栏组件")
    print()

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