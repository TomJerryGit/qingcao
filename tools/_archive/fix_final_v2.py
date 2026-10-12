#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - 最终收尾 v2
==========================
只改 3 个文件（全是测试/检查脚本，不碰业务代码）：

  G1  覆盖 tests/test_outline_end_lines.py
      改用 SymbolParser（_compute_end_lines 的正确宿主）

  G2  覆盖 tests/test_plugin_updater_close.py
      让 cancel 在 iter_content 中途触发

  G3  覆盖 close_review_v2.py
      删除 P0-4（apply_all_patches 已归档到 tools/_archive/，
      归档文件的 marker 不再重要）

用法：
    python fix_final_v2.py --dry-run
    python fix_final_v2.py
"""

import sys
import shutil
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def print_header(t): print(f"\n{'=' * 60}\n{t}\n{'=' * 60}")
def print_ok(m):   print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")


def write_text(path: Path, content: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8', newline='\n')
        return True
    except Exception as e:
        print_fail(f"写回失败 {path.name}: {e}")
        return False


def backup(path: Path, suffix: str = ".bak.final2") -> bool:
    if not path.exists():
        return True
    bak = Path(str(path) + suffix)
    if bak.exists():
        return True
    try:
        shutil.copy2(path, bak)
        return True
    except Exception:
        return False


# ============================================================
# G1: test_outline_end_lines.py
# ============================================================
TEST_OUTLINE = r'''# -*- coding: utf-8 -*-
"""SymbolParser._compute_end_lines 边界测试（P1-B2）

注意：_compute_end_lines 是 SymbolParser 的方法，不是
OutlinePanel 的。OutlinePanel 内部通过
self.parser._build_hierarchy() → self._compute_end_lines()
间接使用它。
"""
import pytest


def _make_parser():
    try:
        from ui.outline_panel import SymbolParser
    except ImportError:
        pytest.skip("SymbolParser 不可用")
    return SymbolParser()


def _make_node(name, type_, line, indent):
    try:
        from ui.outline_panel import SymbolNode
    except ImportError:
        pytest.skip("SymbolNode 不可用")
    return SymbolNode(name=name, type=type_, line=line, indent=indent)


class TestComputeEndLines:

    def test_simple_sequence(self):
        parser = _make_parser()
        symbols = [
            _make_node("a", "function", 0, 0),
            _make_node("b", "function", 10, 0),
            _make_node("c", "function", 20, 0),
        ]
        parser._compute_end_lines(symbols)
        assert symbols[0].end_line == 9
        assert symbols[1].end_line == 19
        assert symbols[2].end_line == 20

    def test_nested(self):
        parser = _make_parser()
        symbols = [
            _make_node("cls", "class", 0, 0),
            _make_node("m1", "method", 5, 4),
            _make_node("m2", "method", 10, 4),
            _make_node("func", "function", 20, 0),
        ]
        parser._compute_end_lines(symbols)
        assert symbols[0].end_line == 19
        assert symbols[1].end_line == 9
        assert symbols[2].end_line == 19
        assert symbols[3].end_line == 20

    def test_empty(self):
        parser = _make_parser()
        parser._compute_end_lines([])   # 不崩即可

    def test_single(self):
        parser = _make_parser()
        symbols = [_make_node("only", "function", 5, 0)]
        parser._compute_end_lines(symbols)
        assert symbols[0].end_line == 5
'''


def fix_g1(no_backup: bool) -> str:
    path = ROOT / "tests" / "test_outline_end_lines.py"
    if not no_backup:
        backup(path)
    if not write_text(path, TEST_OUTLINE):
        return 'failed'
    print_ok("G1 test_outline_end_lines.py 已覆盖（用 SymbolParser）")
    return 'applied'


# ============================================================
# G2: test_plugin_updater_close.py
# ============================================================
TEST_UPDATER = r'''# -*- coding: utf-8 -*-
"""plugin_updater 取消下载后连接关闭（P1-A3 / F1）

注意：
    _download_update 在 for attempt 循环开头有：

        if self._cancelled:
            return None

    所以不能一开始就把 _cancelled = True，否则 requests.get
    根本不会被调用。测试改为在 iter_content 中途触发 cancel。
"""
import pytest
from unittest.mock import MagicMock, patch


class TestDownloadClose:

    def _make_updater(self):
        try:
            from infrastructure.plugin_updater import PluginUpdater
        except ImportError:
            pytest.skip("plugin_updater 不可用")
        return PluginUpdater()

    def test_cancel_closes_connection(self, qapp):
        """下载中途取消 → resp 应被关闭"""
        updater = self._make_updater()
        updater._cancelled = False

        # iter_content 第一次 yield 后触发 cancel
        def iter_content_side(chunk_size):
            yield b"x" * chunk_size
            updater._cancelled = True   # 中途取消
            yield b"y" * chunk_size     # 应该被 for 循环检测到而返回

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.headers = {'content-length': '10000'}
        fake_resp.iter_content = iter_content_side

        with patch('requests.get', return_value=fake_resp):
            result = updater._download_update(
                "http://example.com/fake.zip", "test"
            )

        assert result is None
        assert fake_resp.close.called, "取消后 resp.close() 未被调用"

    def test_normal_download_closes(self, qapp):
        """正常下载完成后 resp 应被关闭"""
        updater = self._make_updater()
        updater._cancelled = False

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.headers = {'content-length': '5'}
        fake_resp.iter_content = lambda chunk_size: iter([b"hello"])

        with patch('requests.get', return_value=fake_resp):
            result = updater._download_update(
                "http://example.com/fake.zip", "test"
            )

        assert result == b"hello"
        assert fake_resp.close.called
'''


def fix_g2(no_backup: bool) -> str:
    path = ROOT / "tests" / "test_plugin_updater_close.py"
    if not no_backup:
        backup(path)
    if not write_text(path, TEST_UPDATER):
        return 'failed'
    print_ok("G2 test_plugin_updater_close.py 已覆盖")
    return 'applied'


# ============================================================
# G3: close_review_v2.py —— 删除 P0-4
# ============================================================
CLOSE_REVIEW_V2 = r'''#!/usr/bin/env python
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
'''


def fix_g3(no_backup: bool) -> str:
    path = ROOT / "close_review_v2.py"
    if not no_backup:
        backup(path)
    if not write_text(path, CLOSE_REVIEW_V2):
        return 'failed'
    print_ok("G3 close_review_v2.py 已覆盖（去掉 P0-4）")
    return 'applied'


# ============================================================
# 主流程
# ============================================================
FIXES = [
    ("G1", "覆盖 test_outline_end_lines.py（用 SymbolParser）", fix_g1),
    ("G2", "覆盖 test_plugin_updater_close.py（cancel 中途触发）", fix_g2),
    ("G3", "覆盖 close_review_v2.py（去掉 P0-4）", fix_g3),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("青草编辑器最终收尾 v2")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")

    if args.dry_run:
        print_info(f"[DRY-RUN] 将处理 {len(FIXES)} 项：")
        for pid, name, _ in FIXES:
            print_info(f"  {pid}: {name}")
        return 0

    results = []
    for pid, name, fn in FIXES:
        print_header(f"{pid}: {name}")
        results.append((pid, name, fn(args.no_backup)))

    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    applied = skipped = failed = 0
    for pid, name, r in results:
        mark = {'applied': '✓', 'skipped': '-', 'failed': '✗'}[r]
        print(f"  {mark} {pid}: {name} [{r}]")
        if r == 'applied': applied += 1
        elif r == 'skipped': skipped += 1
        else: failed += 1

    print()
    if failed:
        print(f"✗ {failed} 项失败")
        return 1
    print(f"✓ 完成（应用 {applied} 项）")
    print()
    print("下一步：")
    print("  python close_review_v2.py")
    print("  python tests/run_all.py")
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