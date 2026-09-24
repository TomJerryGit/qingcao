#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - 主题跟随修复 v2
============================================================
修复 v1 的两个问题：

1. 【致命】ThemeLoader._apply_scintilla_styles 用了
   QsciScintilla.SCI_STYLE_DEFAULT 等不存在的类属性 →
   改为 no-op（高层 API 已覆盖主要样式）。

2. 【锚点】global_search_panel / outline_panel / lsp_panel
   有多个 _apply_style 方法 → 改用类感知策略，只在目标
   类内插入 refresh_theme。

特性：
    - 幂等
    - 逐文件备份 *.bak.themefollow2
    - 修改后 compile() 验证
    - 单文件失败不影响其他

用法：
    python fix_theme_follow_v2.py --dry-run
    python fix_theme_follow_v2.py
"""

import os
import sys
import re
import shutil
import argparse
import traceback
from pathlib import Path
from typing import List, Tuple, Optional

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.themefollow2"


def print_header(t): print(f"\n{'=' * 60}\n{t}\n{'=' * 60}")
def print_ok(m): print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")


# ============================================================
# 补丁 1：theme_loader.py 的 _apply_scintilla_styles 改 no-op
# ============================================================
LOADER_FILE = "infrastructure/theme_loader.py"
LOADER_MARKER = "# v3.1: 本方法已改为 no-op"

LOADER_OLD = '''    def _apply_scintilla_styles(self, editor, colors: ThemeColors):
        """通过 Scintilla API 设置样式"""
        try:
            SCI = QsciScintilla

            # 默认样式
            editor.SendScintilla(
                SCI.SCI_STYLESETFORE, SCI.SCI_STYLE_DEFAULT,
                QColor(colors.foreground)
            )
            editor.SendScintilla(
                SCI.SCI_STYLESETBACK, SCI.SCI_STYLE_DEFAULT,
                QColor(colors.background)
            )

            # 行号样式
            editor.SendScintilla(
                SCI.SCI_STYLESETFORE, SCI.SCI_STYLE_LINENUMBER,
                QColor(colors.line_number_fg)
            )
            editor.SendScintilla(
                SCI.SCI_STYLESETBACK, SCI.SCI_STYLE_LINENUMBER,
                QColor(colors.line_number_bg)
            )

            # 括号匹配
            editor.SendScintilla(
                SCI.SCI_STYLESETFORE, SCI.SCI_STYLE_BRACELIGHT,
                QColor(colors.brace_light_fg)
            )
            editor.SendScintilla(
                SCI.SCI_STYLESETBACK, SCI.SCI_STYLE_BRACELIGHT,
                QColor(colors.brace_light_bg)
            )
            editor.SendScintilla(
                SCI.SCI_STYLESETFORE, SCI.SCI_STYLE_BRACEBAD,
                QColor(colors.brace_bad_fg)
            )

            # 缩进辅助线
            editor.SendScintilla(
                SCI.SCI_STYLESETFORE, SCI.SCI_STYLE_INDENTGUIDE,
                QColor(colors.indent_guide)
            )

        except Exception as e:
            print(f"[ThemeLoader] 设置 Scintilla 样式失败: {e}")'''

LOADER_NEW = '''    def _apply_scintilla_styles(self, editor, colors: ThemeColors):
        """通过 Scintilla API 设置样式

        v3.1: 本方法已改为 no-op。

        原因：
            PyQt5 的 QsciScintilla 类不导出 SCI_STYLE_DEFAULT /
            SCI_STYLESETFORE 等常量（它们是实例属性），
            原代码 `QsciScintilla.SCI_STYLE_DEFAULT` 会抛
            AttributeError，在控制台反复刷警告。

        替代：
            apply() 中已通过 QsciScintilla 高层 API 设置：
              - setColor / setPaper
              - setMarginsBackgroundColor / setMarginsForegroundColor
              - setMatchedBraceForegroundColor / BackgroundColor
              - setUnmatchedBraceForegroundColor
              - setIndentationGuidesForegroundColor
            已覆盖本方法原本要做的全部工作。
        """
        # 无需实现，颜色已由 apply() 中的高层 API 设置
        pass'''


# ============================================================
# 补丁 2：3 个面板的 refresh_theme（类感知）
# ============================================================
REFRESH_METHOD = '''
    def refresh_theme(self, theme):
        """主题变更时刷新样式（v3.0）"""
        try:
            from infrastructure.theme_loader import adapt_qss_colors
            if not hasattr(self, '_original_qss') or not self._original_qss:
                self._original_qss = self.styleSheet()
            if self._original_qss:
                qss = adapt_qss_colors(self._original_qss, theme)
                self.setStyleSheet(qss)
        except Exception as e:
            print(f"[{self.__class__.__name__}] refresh_theme 失败: {e}")

'''


# (文件, 类名, 锚点方法名)
SMART_PANELS = [
    ("ui/global_search_panel.py", "GlobalSearchPanel", "_apply_style"),
    ("ui/outline_panel.py", "OutlinePanel", "_apply_style"),
    ("ui/lsp_panel.py", "LspPanel", "_apply_style"),
]


# ============================================================
# 工具
# ============================================================
def validate_python(content, filepath):
    try:
        compile(content, filepath, 'exec')
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


def write_back(path: Path, new_content: str, no_backup: bool) -> bool:
    """备份 + 写回"""
    if not no_backup:
        backup = Path(str(path) + BACKUP_SUFFIX)
        if not backup.exists():
            try:
                shutil.copy2(path, backup)
            except Exception:
                pass
    try:
        path.write_text(new_content, encoding='utf-8', newline='\n')
        return True
    except Exception as e:
        print_fail(f"写回失败: {e}")
        return False


# ============================================================
# 补丁 1 应用
# ============================================================
def apply_loader_patch(dry_run: bool, no_backup: bool) -> str:
    path = ROOT / LOADER_FILE
    if not path.exists():
        print_fail(f"{LOADER_FILE}: 文件不存在")
        return 'failed'

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 'failed'

    if LOADER_MARKER in content:
        print_skip(f"{LOADER_FILE}: 已应用")
        return 'skipped'

    if LOADER_OLD not in content:
        print_fail(f"{LOADER_FILE}: 锚点未找到")
        print_info("期望锚点前 3 行：")
        for line in LOADER_OLD.split('\n')[:3]:
            print(f"    | {line}")
        return 'failed'

    if content.count(LOADER_OLD) > 1:
        print_fail(f"{LOADER_FILE}: 锚点重复")
        return 'failed'

    if dry_run:
        print_info(f"[DRY-RUN] {LOADER_FILE}: 会替换 _apply_scintilla_styles")
        return 'applied'

    new_content = content.replace(LOADER_OLD, LOADER_NEW, 1)

    ok, err = validate_python(new_content, str(path))
    if not ok:
        print_fail(f"{LOADER_FILE}: 语法错误 ({err})")
        return 'failed'

    if not write_back(path, new_content, no_backup):
        return 'failed'

    print_ok(f"{LOADER_FILE}: _apply_scintilla_styles 已改为 no-op")
    return 'applied'


# ============================================================
# 补丁 2 应用（类感知）
# ============================================================
def apply_smart_panel(path: Path, class_name: str,
                       anchor_method: str,
                       dry_run: bool, no_backup: bool) -> str:
    """在指定类内查找第一个 anchor_method 并插入 refresh_theme"""
    if not path.exists():
        print_skip(f"{path.name}: 文件不存在")
        return 'skipped'

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"{path.name}: 读取失败 ({e})")
        return 'failed'

    # 幂等
    if "def refresh_theme(self, theme):" in content:
        print_skip(f"{path.name}: 已有 refresh_theme")
        return 'skipped'

    # 定位类定义
    class_pattern = re.compile(
        rf'^class\s+{re.escape(class_name)}\s*\(', re.MULTILINE
    )
    m_class = class_pattern.search(content)
    if not m_class:
        print_fail(f"{path.name}: 类 {class_name} 未找到")
        return 'failed'

    # 找下一个类定义作为边界
    next_class_pattern = re.compile(r'^class\s+\w+', re.MULTILINE)
    m_next = next_class_pattern.search(content, m_class.end())
    class_end = m_next.start() if m_next else len(content)

    # 类范围内找第一个锚点
    class_body = content[m_class.start():class_end]
    anchor_pattern = re.compile(
        rf'^(    def {re.escape(anchor_method)}\(self\):)',
        re.MULTILINE
    )
    m_anchor = anchor_pattern.search(class_body)
    if not m_anchor:
        print_fail(
            f"{path.name}: 类 {class_name} 内未找到 {anchor_method}"
        )
        return 'failed'

    # 相对位置转绝对位置
    abs_pos = m_class.start() + m_anchor.start()

    if dry_run:
        print_info(
            f"[DRY-RUN] {path.name}: 会在类 {class_name} 内插入 refresh_theme"
        )
        return 'applied'

    # 插入
    new_content = (
        content[:abs_pos]
        + REFRESH_METHOD.lstrip('\n')
        + content[abs_pos:]
    )

    ok, err = validate_python(new_content, str(path))
    if not ok:
        print_fail(f"{path.name}: 语法错误 ({err})")
        return 'failed'

    if not write_back(path, new_content, no_backup):
        return 'failed'

    print_ok(f"{path.name}: 已在类 {class_name} 内插入 refresh_theme")
    return 'applied'


# ============================================================
# 主流程
# ============================================================
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--only', type=str, default='',
                        help='只处理指定项：loader / panels / 全部')
    args = parser.parse_args()

    print_header("主题跟随修复 v2")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")

    applied = 0
    skipped = 0
    failed = 0

    only = args.only.strip().lower()
    do_loader = (not only) or only in ('loader', 'all')
    do_panels = (not only) or only in ('panels', 'all')

    # ---- 补丁 1：theme_loader ----
    if do_loader:
        print_header("补丁 1: theme_loader._apply_scintilla_styles")
        r = apply_loader_patch(args.dry_run, args.no_backup)
        if r == 'applied': applied += 1
        elif r == 'skipped': skipped += 1
        else: failed += 1

    # ---- 补丁 2：3 个面板 ----
    if do_panels:
        print_header("补丁 2: 3 个面板的 refresh_theme（类感知）")
        for path_str, cls_name, anchor in SMART_PANELS:
            r = apply_smart_panel(
                ROOT / path_str, cls_name, anchor,
                args.dry_run, args.no_backup
            )
            if r == 'applied': applied += 1
            elif r == 'skipped': skipped += 1
            else: failed += 1

    # ---- 汇总 ----
    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    print(f"  已应用: {applied}")
    print(f"  已跳过: {skipped}")
    print(f"  失败:   {failed}")

    if args.dry_run:
        print()
        print("⚠ DRY-RUN 模式，未修改文件")
        print("  运行 `python fix_theme_follow_v2.py` 应用")
    elif failed == 0 and applied > 0:
        print()
        print("=" * 60)
        print("✓ 修复完成")
        print("=" * 60)
        print()
        print("下一步:")
        print("  python main.py")
        print("  观察控制台不再有 SCI_STYLE_DEFAULT 警告")
        print("  切换主题（视图 → 主题）验证所有面板跟随")

    return 0 if failed == 0 else 1


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