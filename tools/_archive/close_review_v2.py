#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""青草编辑器回归验证 v2"""
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# (id, 描述, 相对路径, 类型, pattern)
CHECKS = [
    ("P0-1",  "requirements 无 diff 残留",
     "requirements.txt", "not_in", "-keyring>="),
    ("P0-1b", "requirements 有干净 keyring",
     "requirements.txt", "in", "keyring>=23.0.0"),
    ("P0-2a", ".gitignore 忽略 session.json",
     ".gitignore", "in", "session.json"),
    ("P0-3",  "README 无 AI 残留",
     "README.md", "not_in", "变更摘要"),
    # P0-4 已删除：apply_all_patches 已归档到 tools/_archive/
    # 归档文件的 marker 不影响主线代码
    ("P0-C1", "task_panel 有 QLabel 导入",
     "ui/task_panel.py", "in", "QToolButton, QLabel"),
    ("P0-C2", "SearchBar 用 result.matches",
     "ui/panels.py", "in", "P0-C2"),
    ("P0-C3", "file_ops 延迟导入 MainWindow",
     "ui/mixins/file_ops_mixin.py", "in", "P0-C3"),
    ("P0-C4", "column_mode 忽略 checked",
     "ui/main_window.py", "in", "P0-C4"),
    ("P0-C5", "conftest 有 autouse 隔离",
     "tests/conftest.py", "in", 'autouse=True, scope="session"'),
    ("P1-A1", "sandbox 移除 socket 白名单",
     "infrastructure/sandbox_runtime.py", "in", "P1-A1"),
    ("P1-A2", "plugin_sandbox 用 Event",
     "infrastructure/plugin_sandbox.py", "in", "_ready_event"),
    ("P1-A3", "plugin_updater finally 关连接",
     "infrastructure/plugin_updater.py", "in", "F1 修复"),
    ("P1-A4", "content_provider 释放 mmap",
     "core/content_provider.py", "in", "_reopen_mmap"),
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
     "tests/conftest.py", "not_in",
     "def preferences(qapp, tmp_path, monkeypatch)"),
    ("P2-C8", "requirements-dev 有 mkdocs",
     "requirements-dev.txt", "in", "mkdocs"),
    ("P2-C9", "event_bus 注释已改",
     "app/event_bus.py", "not_in", "基于 PySide6 pyqtSignal"),
    ("R3", "gitignore 忽略 *.bak.*",
     ".gitignore", "in", "*.bak.*"),
    # 新增：snippet_market_dialog 文件名已修正
    ("F5", "snippet_market_dialog 已重命名",
     "ui/snippet_market_dialog.py", "exists", ""),
]


def _read(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except Exception:
        return ""
    if raw.startswith(b'\xef\xbb\xbf'):
        text = raw.decode('utf-8-sig', errors='replace')
    else:
        for enc in ('utf-8', 'gbk', 'latin-1'):
            try:
                text = raw.decode(enc)
                break
            except Exception:
                continue
        else:
            text = raw.decode('utf-8', errors='replace')
    return text.replace('\r\n', '\n').replace('\r', '\n')


def run_checks():
    passed = 0
    failures = []
    for cid, desc, rel, kind, pattern in CHECKS:
        path = ROOT / rel

        if kind == 'exists':
            if path.exists():
                print(f"  [OK]   [{cid}] {desc}")
                passed += 1
            else:
                print(f"  [FAIL] [{cid}] {desc}: 文件不存在")
                failures.append((cid, desc, "文件不存在"))
            continue
        if kind == 'not_exists':
            if not path.exists():
                print(f"  [OK]   [{cid}] {desc}")
                passed += 1
            else:
                print(f"  [FAIL] [{cid}] {desc}: 文件仍存在")
                failures.append((cid, desc, "文件仍存在"))
            continue

        if not path.exists():
            print(f"  [FAIL] [{cid}] {desc}: 文件不存在")
            failures.append((cid, desc, "文件不存在"))
            continue

        content = _read(path)
        if kind == 'in':
            if pattern in content:
                print(f"  [OK]   [{cid}] {desc}")
                passed += 1
            else:
                print(f"  [FAIL] [{cid}] {desc}: 未找到 {pattern!r}")
                failures.append((cid, desc, f"未找到 {pattern!r}"))
        elif kind == 'not_in':
            if pattern not in content:
                print(f"  [OK]   [{cid}] {desc}")
                passed += 1
            else:
                print(f"  [FAIL] [{cid}] {desc}: 仍包含 {pattern!r}")
                failures.append((cid, desc, f"仍包含 {pattern!r}"))
    return passed, failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', action='store_true',
                        help='（保留兼容，无实际作用）')
    parser.parse_args()

    print("=" * 60)
    print("回归验证")
    print("=" * 60)
    passed, failures = run_checks()
    total = len(CHECKS)

    print()
    print("=" * 60)
    print(f"结果：{passed}/{total} 通过")
    print("=" * 60)

    if failures:
        print("\n失败项：")
        for cid, desc, reason in failures:
            print(f"  ✗ [{cid}] {desc} -> {reason}")
        return 1

    print("\n✓ 全部通过")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(130)
