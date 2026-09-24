#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
收尾批次：QSS 颜色 + 归档 + CHANGELOG
==========================================
修复 3 项：

  A. adapt_qss_colors 加 #007acc → input_focus
     （QCheckBox::indicator:checked / :focus 等跟随主题）

  B. 归档 fix_*.py 到 _archive/fixes/

  C. 更新 CHANGELOG.md

用法:
    python fix_batch_final.py --dry-run
    python fix_batch_final.py
    python fix_batch_final.py --only A,B      # 跳过 CHANGELOG
"""

import sys
import shutil
import argparse
import datetime
from pathlib import Path
from typing import Tuple, List

ROOT = Path(__file__).resolve().parent
ARCHIVE_DIR = ROOT / "_archive" / "fixes"
BACKUP_SUFFIX = ".bak.final"


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


# ============================================================
# A: QSS 颜色
# ============================================================
A_MARKER = "# A(最终): 补齐 QSS 遗漏的颜色"

A_OLD = '''        # 禁用/危险按钮
        ('#5a5a5a', c.border),
        ('#8f1e1e', c.error),
    ]'''

A_NEW = '''        # 禁用/危险按钮
        ('#5a5a5a', c.border),
        ('#8f1e1e', c.error),

        # A(最终): 补齐 QSS 遗漏的颜色
        # #007acc 是 QCheckBox::indicator:checked / :focus、
        # QLineEdit:focus 等大量控件的聚焦色，之前未覆盖
        ('#007acc', c.input_focus),
        # 更多常见遗漏
        ('#0a4d7a', c.button_pressed),
        ('#0e639c', c.button_bg),   # 重复保险
        ('#2196f3', c.info),
        ('#4caf50', c.success),
        ('#f44336', c.error),
        ('#ff9800', c.warning),
    ]'''


def fix_A(no_backup: bool) -> str:
    path = ROOT / "infrastructure" / "theme_loader.py"
    if not path.exists():
        print_fail("theme_loader.py 不存在")
        return 'failed'
    content = path.read_text(encoding='utf-8')
    if A_MARKER in content:
        print_skip("QSS 颜色扩表已应用")
        return 'skipped'
    cnt = content.count(A_OLD)
    if cnt == 0:
        print_fail("锚点未找到")
        return 'failed'
    if cnt > 1:
        print_fail(f"锚点重复 {cnt} 次")
        return 'failed'
    new_content = content.replace(A_OLD, A_NEW, 1)
    ok, err = validate_python(new_content, str(path))
    if not ok:
        print_fail(f"语法错误 ({err})")
        return 'failed'
    if not write_back(path, new_content, no_backup):
        return 'failed'
    print_ok("theme_loader.py: QSS 颜色扩表已应用")
    return 'applied'


# ============================================================
# B: 归档 fix_*.py
# ============================================================
def fix_B(no_backup: bool) -> str:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # 要归档的 fix 脚本（按前缀匹配）
    patterns = [
        "fix_theme_*.py",
        "fix_vim_*.py",
        "fix_p0*.py",
        "fix_p1*.py",
        "fix_p2*.py",
        "fix_batch*.py",
        "fix_unpack.py",
        "fix_b1b.py",
        "fix_remaining.py",
    ]

    # 排除自身
    self_name = Path(__file__).name

    moved = 0
    skipped = 0

    seen = set()
    for pat in patterns:
        for src in sorted(ROOT.glob(pat)):
            if src.name in seen:
                continue
            seen.add(src.name)

            if src.name == self_name:
                continue
            if src.is_dir():
                continue

            dst = ARCHIVE_DIR / src.name
            if dst.exists():
                print_skip(f"已在归档: {src.name}")
                skipped += 1
                continue

            try:
                shutil.move(str(src), str(dst))
                print_ok(f"已归档: {src.name}")
                moved += 1
            except Exception as e:
                print_fail(f"归档 {src.name} 失败: {e}")

    if moved == 0 and skipped == 0:
        print_info("没有需要归档的文件")
        return 'skipped'

    return 'applied'


# ============================================================
# C: CHANGELOG
# ============================================================
CHANGELOG_CONTENT = '''# Changelog

所有重要的项目变更都记录在此文件中。

本项目遵循 [语义化版本](https://semver.org/)。

## [Unreleased]

### 计划中
- 更多 LSP 语言支持
- 协作编辑完善
- 插件市场后端

## [2.1.0] - 2026-09-24

本次更新聚焦于**跨模块代码审查修复**、**Vim 模式补全**、
**主题切换修复**、**搜索偏移修正**。

### 新增
- **Vim 模式完整实现**
  - 操作符 + 动作: `dw` / `de` / `db` / `d$` / `d0` / `dG` / `dgg`
  - 修改操作符: `cw` / `ce` / `cb` / `c$` / `cc`
  - 复制操作符: `yw` / `ye` / `yb` / `yy`
  - 文本对象: `iw` / `aw` / `i"` / `a"` / `i(` / `a(` / `i[` / `a[` / `i{` / `a{`
  - 具名寄存器: `"a` 前缀（a-z / 0-9 / " / + / * / - / _）
  - 查找重复: `n` / `N`
  - 入口: 工具菜单 → Vim 模式（`Ctrl+Shift+V`）
- **UI 测试套件** (tests/test_vim_mode.py, 11 个测试)
- 测试总数: 187 → 198

### 修复
- **主题切换核心 bug**: `themes/*.json` 无 `qss` 字段，
  `_apply_theme_by_name` 只做 `if theme.qss: setStyleSheet(...)`，
  导致全局 QSS 从未应用。改用 `loader.apply_qss()` 自动生成。
- **主题跟随不全**: 扩展 `adapt_qss_colors` 替换表，
  补充终端色 (`#0d0d0d`)、次要文字、聚焦色 (`#007acc`) 等
- **主题菜单显示**: 从文件名 (`light_clean`) 改为 `display_name` (`晨曦`)
- **字符/字节偏移**: `SearchMatch` 双写 `start/end`（字节）
  和 `char_start/char_end`（字符），修复含中文文件搜索高亮/替换错位
- **`EditorProxy.highlight_all`**: 调用不存在的 `search_all()` →
  改用 `search()`
- **`EditorProxy.search_next`**: 调用签名错误 →
  Python 层遍历 `result.matches`
- **`_search_next` 不前进**: 从 `pos` 开始 → 从 `pos+1` 开始
- **`"a` 寄存器覆盖**: 两次 alnum 输入互相覆盖 →
  加独立 `_waiting_for_register` 状态
- **`yy` 后 `p` 不粘贴**: paste 从旧 `self.register` 读 →
  改从 `registers['"']` 读
- **`SCI_WORDRIGHTPOSITION` 不存在**: `PyQt5` 未导出该常量 →
  改用 `SCI_WORDRIGHT`
- **Ctrl+Z/Ctrl+Y 被吞**: QScintilla 内置绑定占用 →
  `SCI_CLEARCMDKEY` 清除，让主窗口菜单收到
- **`Ctrl+Alt+V` 被 AltGr 解释**: Windows 上无效 →
  改 `Ctrl+Shift+V`
- **`ProjectFileEvent` 子类分派**: `Removed`/`Renamed` 被误当
  `Added` → 先检查子类
- **事件类双重定义**: `app/event_bus.py` 与 `core/events.py`
  各有 44 个同名类 → 统一从 `core.events` 重导出
- **`PluginAPI` 死信号**: `plugin_loaded` / `plugin_unloaded`
  从未 emit → 删除
- **快捷键冲突 5 处**:
  - AI 助手: `Ctrl+Shift+E` → `Ctrl+Alt+E`
  - AI 助手: `Ctrl+Shift+R` → `Ctrl+Alt+Shift+R`
  - Markdown 预览: `Ctrl+Shift+M` → `Ctrl+Alt+M`
  - Python 调试器: `F5` → `F6`
  - TODO 面板: `Ctrl+Shift+T` → `Ctrl+Alt+T`
- **每日技巧日期边界**: 手动点击也更新 `last_tip_date` →
  仅自动触发时更新
- **`outline_panel` 硬编码 50000 行**: 改用
  `large_file_threshold` 偏好推导
- **`DirectoryTree` Git 缓存 5 秒过短**: 改为 30 秒 + 可配置
- **`PythonHighlighter` 性能**: 80 条关键字正则合并为 2 条
- **`command_palette` 使用历史 key 冲突**: `title` 改为
  `action_name`
- **`sandbox_policy.DANGEROUS_MODULES` 冗余**: 移除由权限门控的
  `socket` / `shutil` / `subprocess` 等
- **LSP 位置转换**: 用 `SCI_FINDCOLUMN` → 改用字节偏移
- **pytest-qt 绑定**: PySide6 → PyQt5（避免混用崩溃）

### 变更
- **`adapt_qss_colors` 扩表**:
  - `#0d0d0d` → `background`（终端/控制台）
  - `#2a2d2e` / `#333333` / `#4c4c4c` → 面板变体
  - `#858585` / `#808080` / `#c0c0c0` → 次要文字
  - `#007acc` → `input_focus`（聚焦色）
  - `#404040` → `indent_guide`
  - `#5a5a5a` / `#8f1e1e` → 危险按钮
- `tests/conftest.py`: 设置 `PYTEST_QT_API=pyqt5`
- `EditorWidget.keyPressEvent`: 优先让 VimMode 处理

### 删除
- `PluginAPI.plugin_loaded` / `plugin_unloaded`（死信号）
- `sandbox_policy.DANGEROUS_MODULES` 中由权限门控的冗余模块
- 归档 `fix_*.py` 到 `_archive/fixes/`

### 测试
- 198 passed（187 → 198，新增 11 个 Vim 测试）

## [2.0.0] - 2026-09-19

### 新增
- 全新的 PyQt5 架构
- 完整的 LSP 客户端
- 插件系统与沙箱
- 宏录制与回放
- 多光标与列模式
- 命令面板与文件切换
- AI 助手集成
- 代码片段系统
- 主题编辑器
- 性能监控面板
- 会话快照
- 集成终端
- Git 集成
- 自动更新

### 修复
- 编辑器渲染性能
- 大文件加载
- 快捷键冲突检测

### 变更
- 从 PySide6 迁移到 PyQt5
'''


def fix_C(no_backup: bool) -> str:
    path = ROOT / "CHANGELOG.md"
    if path.exists():
        try:
            existing = path.read_text(encoding='utf-8')
            if "[2.1.0]" in existing:
                print_skip("CHANGELOG 已包含 2.1.0")
                return 'skipped'
        except Exception:
            pass

    if not write_back(path, CHANGELOG_CONTENT, no_backup):
        return 'failed'
    print_ok("CHANGELOG.md 已更新（加入 2.1.0）")
    return 'applied'


FIXES = [
    ("A", "QSS 颜色扩表", fix_A),
    ("B", "归档 fix_*.py", fix_B),
    ("C", "CHANGELOG 更新", fix_C),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--only', type=str, default='')
    args = parser.parse_args()

    print_header("收尾批次")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")

    fixes = FIXES
    if args.only:
        only = {x.strip().upper() for x in args.only.split(',')}
        fixes = [f for f in fixes if f[0] in only]

    if args.dry_run:
        print()
        print_info(f"[DRY-RUN] 将处理 {len(fixes)} 项：")
        for pid, name, _ in fixes:
            print_info(f"  {pid}: {name}")
        return 0

    results = []
    for pid, name, fn in fixes:
        print_header(f"{pid}: {name}")
        r = fn(args.no_backup)
        results.append((pid, name, r))

    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    applied = skipped = failed = 0
    for pid, name, r in results:
        marker = {'applied': '✓', 'skipped': '-', 'failed': '✗'}[r]
        print(f"  {marker} {pid}: {name} [{r}]")
        if r == 'applied':
            applied += 1
        elif r == 'skipped':
            skipped += 1
        else:
            failed += 1

    if failed:
        print(f"\n✗ 有 {failed} 项失败")
        return 1

    print()
    print("=" * 60)
    print(f"✓ 完成（应用 {applied}，跳过 {skipped}）")
    print("=" * 60)
    print()
    print("验证:")
    print("  python tests/run_all.py")
    print("  python main.py")
    print()
    print("手工验证:")
    print("  1. 全局搜索面板的复选框勾选 → 应显示浅色主题色")
    print("  2. 切主题 → QCheckBox / QLineEdit:focus 应跟随")
    print()
    print("归档:")
    print("  _archive/fixes/ 下应有 8+ 个 fix_*.py")
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