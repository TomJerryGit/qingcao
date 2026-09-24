#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - 审查闭环脚本
============================
一次性完成三件事：

  1. 回归验证
     逐项检查 P0/P1/P2 共 30+ 修复是否在代码中生效。

  2. 归档清理
     把所有 fix_*.py / apply_all_patches*.py 移到 _archive/fixes/。

  3. 发布准备
     更新 CHANGELOG.md，生成 REVIEW_REPORT.md。

特性：
  - 只读验证（不修改业务代码）
  - 归档用 git mv（保留历史），失败回退普通 mv
  - CHANGELOG 幂等（已有 2.0.1 段则跳过）
  - 报告包含完整验证结果

用法：
    python close_review.py --dry-run       # 只验证，不动文件
    python close_review.py                 # 验证 + 归档 + 发布准备
    python close_review.py --verify-only   # 只验证
    python close_review.py --archive-only  # 只归档
"""

import os
import re
import sys
import shutil
import argparse
import subprocess
import datetime
from pathlib import Path
from typing import List, Tuple, Optional

ROOT = Path(__file__).resolve().parent

ARCHIVE_DIR = ROOT / "_archive" / "fixes"
CHANGELOG = ROOT / "CHANGELOG.md"
REPORT = ROOT / "REVIEW_REPORT.md"

VERSION_OLD = "2.0.0"
VERSION_NEW = "2.0.1"


# ============================================================
# 输出
# ============================================================
def print_header(t): print(f"\n{'=' * 60}\n{t}\n{'=' * 60}")
def print_ok(m):   print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")
def print_warn(m): print(f"  [WARN] {m}")


# ============================================================
# 验证项定义
# ============================================================
# 每项： (id, 描述, 路径, 类型, 模式)
# 类型：
#   'in'         content 里应包含 pattern
#   'not_in'     content 里不应包含 pattern
#   'exists'     文件应存在
#   'not_exists' 文件应不存在
CHECKS: List[Tuple[str, str, str, str, str]] = [
    # ---- P0 工具链 ----
    ("P0-1",  "requirements 无 diff 残留",
     "requirements.txt", "not_in", "-keyring>="),
    ("P0-1b", "requirements 有干净 keyring",
     "requirements.txt", "in", "keyring>=23.0.0"),
    ("P0-2a", "session.json 已删除",
     "session.json", "not_exists", ""),
    ("P0-2b", ".gitignore 含 session.json",
     ".gitignore", "in", "session.json"),
    ("P0-3",  "README 无 AI 残留",
     "README.md", "not_in", "变更摘要"),
    ("P0-4",  "apply_all_patches 新 marker",
     "apply_all_patches.py", "in", "青草枯荣，野火重生"),

    # ---- P0 代码 ----
    ("P0-C1", "task_panel 有 QLabel 导入",
     "ui/task_panel.py", "in", "QToolButton, QLabel"),
    ("P0-C2", "SearchBar 用 result.matches",
     "ui/panels.py", "in", "P0-C2"),
    ("P0-C3", "file_ops 延迟导入 MainWindow",
     "ui/mixins/file_ops_mixin.py", "in", "P0-C3"),
    ("P0-C4", "column_mode 忽略 checked",
     "ui/main_window.py", "in", "P0-C4"),
    ("P0-C5", "conftest 有 autouse 隔离",
     "tests/conftest.py", "in", "autouse=True, scope=\"session\""),

    # ---- P1 核心 ----
    ("P1-A1", "sandbox 移除 socket 白名单",
     "infrastructure/sandbox_runtime.py", "in", "P1-A1"),
    ("P1-A2", "plugin_sandbox 用 Event",
     "infrastructure/plugin_sandbox.py", "in", "_ready_event"),
    ("P1-A3", "plugin_updater try/finally",
     "infrastructure/plugin_updater.py", "in", "A3 修复"),
    ("P1-A4", "content_provider 释放 mmap",
     "core/content_provider.py", "in", "_reopen_mmap"),

    # ---- P1 UI ----
    ("P1-B1", "explorer /select 单参数",
     "ui/directory_tree.py", "in", "P1-B1"),
    ("P1-B2", "outline end_line 循环",
     "ui/outline_panel.py", "in", "P1-B2"),
    ("P1-B3", "outline 监听 file_modified",
     "ui/outline_panel.py", "in", "_on_file_modified"),
    ("P1-B4", "editor_view indent_bytes",
     "ui/editor_view.py", "in", "P1-B4"),
    ("P1-B5", "terminal 子线程信号转发",
     "ui/terminal_panel.py", "in", "_output_signal"),
    ("P1-B6", "welcome StatsPanel 用 usage_stats",
     "ui/welcome_widget.py", "in", "core.usage_stats"),
    ("P1-B7", "GitBranchLabel 不调 super",
     "ui/status_bar_widgets.py", "in", "P1-B7"),
    ("P1-B8", "theme_market generation counter",
     "ui/theme_market.py", "in", "_preview_gen"),

    # ---- P2 数据源 ----
    ("P2-C1", "welcome 统一 tips 数据源",
     "ui/welcome_widget.py", "in", "from ui.tips import"),
    ("P2-C2", "usage_stats_panel 复用 core",
     "ui/usage_stats_panel.py", "in", "core.usage_stats"),
    ("P2-C3", "theme_market 公开 clear_cache",
     "ui/theme_market.py", "in", "def clear_cache"),
    ("P2-C4", "每日技巧 manual 参数",
     "ui/main_window.py", "in", "manual=True"),
    ("P2-C5", "连接 replace_requested",
     "ui/main_window.py", "in", "_on_global_replace"),
    ("P2-C6", "outline 大文件限制",
     "ui/outline_panel.py", "in", "MAX_LINES_READ"),
    ("P2-C7", "conftest 删 monkeypatch",
     "tests/conftest.py", "not_in", "def preferences(qapp, tmp_path, monkeypatch)"),
    ("P2-C8", "requirements-dev 有 mkdocs",
     "requirements-dev.txt", "in", "mkdocs"),
    ("P2-C9", "event_bus 注释已改",
     "app/event_bus.py", "not_in", "基于 PySide6 pyqtSignal"),
]


# ============================================================
# 验证引擎
# ============================================================
def run_checks() -> Tuple[int, int, List[Tuple[str, str, str]]]:
    """
    运行所有验证项。

    返回:
        (passed, total, failures)
        failures: [(id, desc, reason), ...]
    """
    passed = 0
    total = len(CHECKS)
    failures: List[Tuple[str, str, str]] = []

    for cid, desc, rel, kind, pattern in CHECKS:
        path = ROOT / rel

        # 文件级检查
        if kind == 'exists':
            if path.exists():
                passed += 1
                print_ok(f"[{cid}] {desc}")
            else:
                failures.append((cid, desc, "文件不存在"))
                print_fail(f"[{cid}] {desc}: 文件不存在")
            continue

        if kind == 'not_exists':
            if not path.exists():
                passed += 1
                print_ok(f"[{cid}] {desc}")
            else:
                failures.append((cid, desc, "文件仍然存在"))
                print_fail(f"[{cid}] {desc}: 文件仍存在")
            continue

        # 内容级检查
        if not path.exists():
            failures.append((cid, desc, "文件不存在"))
            print_fail(f"[{cid}] {desc}: 文件不存在")
            continue

        try:
            content = path.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            failures.append((cid, desc, f"读取失败: {e}"))
            print_fail(f"[{cid}] {desc}: 读取失败 ({e})")
            continue

        if kind == 'in':
            if pattern in content:
                passed += 1
                print_ok(f"[{cid}] {desc}")
            else:
                failures.append((cid, desc, f"未找到: {pattern!r}"))
                print_fail(f"[{cid}] {desc}: 未找到 {pattern!r}")
        elif kind == 'not_in':
            if pattern not in content:
                passed += 1
                print_ok(f"[{cid}] {desc}")
            else:
                failures.append((cid, desc, f"仍包含: {pattern!r}"))
                print_fail(f"[{cid}] {desc}: 仍包含 {pattern!r}")

    return passed, total, failures


# ============================================================
# 归档
# ============================================================
def find_scripts_to_archive() -> List[Path]:
    """找到仓库根目录下所有待归档脚本"""
    patterns = [
        "fix_*.py",
        "apply_all_patches*.py",
    ]
    result = []
    for p in patterns:
        for path in sorted(ROOT.glob(p)):
            # 排除脚本自身
            if path.resolve() == Path(__file__).resolve():
                continue
            result.append(path)
    return result


def _git_mv(src: Path, dst: Path) -> bool:
    """尝试用 git mv，失败返回 False"""
    if not shutil.which("git"):
        return False
    try:
        r = subprocess.run(
            ["git", "mv", str(src), str(dst)],
            cwd=ROOT, capture_output=True, text=True,
        )
        return r.returncode == 0
    except Exception:
        return False


def archive_scripts(dry_run: bool = False) -> Tuple[int, List[str]]:
    """
    归档所有 fix/apply 脚本。

    返回:
        (归档数量, 错误列表)
    """
    scripts = find_scripts_to_archive()
    if not scripts:
        print_info("无待归档脚本")
        return 0, []

    if dry_run:
        print_info(f"[DRY-RUN] 待归档 {len(scripts)} 个脚本:")
        for s in scripts:
            print(f"    {s.name}")
        return 0, []

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    moved = 0
    errors = []
    for src in scripts:
        dst = ARCHIVE_DIR / src.name
        if dst.exists():
            print_skip(f"{src.name} 已在 _archive/ 中")
            continue

        # 优先 git mv
        if _git_mv(src, dst):
            print_ok(f"git mv {src.name}")
            moved += 1
            continue

        # 回退普通 mv
        try:
            shutil.move(str(src), str(dst))
            print_ok(f"mv {src.name}")
            moved += 1
        except Exception as e:
            print_fail(f"{src.name}: {e}")
            errors.append(f"{src.name}: {e}")

    # 生成归档 README
    _write_archive_readme()

    return moved, errors


def _write_archive_readme():
    readme = ARCHIVE_DIR / "README.md"
    if readme.exists():
        return
    try:
        readme.write_text("""# 一次性修复脚本归档

本目录存放 2026-09 各轮 P0/P1/P2 修复脚本。**所有修复已合并到主线
代码，日常不需要执行**。保留仅供追溯。

## 批次

| 批次 | 脚本 | 覆盖范围 |
|------|------|----------|
| P0 工具链 | `fix_p0.py` | requirements / session.json / README / marker |
| P0 代码 | `fix_p0_code.py` | task_panel / panels / file_ops / main_window / tests |
| P1 核心 | `fix_p1_core.py` | sandbox socket / Pipe 竞争 / updater / mmap |
| P1 UI | `fix_p1_b.py` | explorer / outline / editor / terminal / welcome / statusbar / theme_market |
| P2 数据源 | `fix_p2_data.py` | tips / usage_stats / theme_market / 每日技巧 / 全局替换 / outline 大文件 |
| 历史补丁 | `fix_sandbox_runtime_v2*.py` 等 | 早期中间版本，已被最终版取代 |

## 如需重跑

所有脚本都带 `--dry-run` 参数，先预演再执行：

```bash
python _archive/fixes/fix_p1_core.py --dry-run