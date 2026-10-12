#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - 最终收尾
========================
一次修 6 项：

  F1  plugin_updater.py A3（用 CRLF 归一化，解决锚点不匹配）
  F2  覆盖 close_review_v2.py（P0-2a / P0-4 检查逻辑修正）
  F3  覆盖 tests/test_outline_end_lines.py（用 qapp 真实构造）
  F4  覆盖 tests/test_plugin_updater_close.py（patch 路径修正）
  F5  ui/nippet_market_dialog.py → ui/snippet_market_dialog.py
  F6  删除 close_review.py（有语法错误，已被 v2 取代）

用法：
    python fix_final.py --dry-run
    python fix_final.py
"""

import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parent


def print_header(t): print(f"\n{'=' * 60}\n{t}\n{'=' * 60}")
def print_ok(m):   print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")


# ------------------------------------------------------------
# 读 / 写（统一 LF，自动处理 BOM / GBK）
# ------------------------------------------------------------
def read_text(path: Path) -> str:
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
    # 统一 LF
    return text.replace('\r\n', '\n').replace('\r', '\n')


def write_text(path: Path, content: str) -> bool:
    try:
        path.write_text(content, encoding='utf-8', newline='\n')
        return True
    except Exception as e:
        print_fail(f"写回失败 {path.name}: {e}")
        return False


def backup(path: Path, suffix: str = ".bak.final") -> bool:
    bak = Path(str(path) + suffix)
    if bak.exists():
        return True
    try:
        shutil.copy2(path, bak)
        return True
    except Exception:
        return False


# ============================================================
# F1: plugin_updater.py A3（CRLF 归一化版）
# ============================================================
F1_MARKER = "# F1 修复：finally 保证 resp 关闭"

F1_OLD = '''            try:
                import requests
                resp = requests.get(
                    url, timeout=DOWNLOAD_TIMEOUT, stream=True
                )

                if resp.status_code != 200:
                    print(f"[PluginUpdater] 下载失败: HTTP {resp.status_code}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)
                        continue
                    return None

                # 获取总大小
                total_size = int(resp.headers.get('content-length', 0))

                # 流式下载
                chunks = []
                downloaded = 0

                for chunk in resp.iter_content(chunk_size=8192):
                    if self._cancelled:
                        return None

                    chunks.append(chunk)
                    downloaded += len(chunk)

                    if total_size > 0 and progress_callback:
                        pct = 5 + int((downloaded / total_size) * 50)
                        progress_callback(
                            pct,
                            f"下载中 {downloaded // 1024}/{total_size // 1024} KB"
                        )

                return b''.join(chunks)

            except ImportError:
                # urllib 回退
                try:
                    import urllib.request
                    with urllib.request.urlopen(
                        url, timeout=DOWNLOAD_TIMEOUT
                    ) as f:
                        return f.read()
                except Exception as e:
                    print(f"[PluginUpdater] urllib 下载失败: {e}")
            except Exception as e:
                print(f"[PluginUpdater] 下载异常: {e}")'''

F1_NEW = '''            resp = None
            try:
                import requests
                resp = requests.get(
                    url, timeout=DOWNLOAD_TIMEOUT, stream=True
                )

                if resp.status_code != 200:
                    print(f"[PluginUpdater] 下载失败: HTTP {resp.status_code}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY)
                        continue
                    return None

                # 获取总大小
                total_size = int(resp.headers.get('content-length', 0))

                # 流式下载
                chunks = []
                downloaded = 0

                for chunk in resp.iter_content(chunk_size=8192):
                    if self._cancelled:
                        return None

                    chunks.append(chunk)
                    downloaded += len(chunk)

                    if total_size > 0 and progress_callback:
                        pct = 5 + int((downloaded / total_size) * 50)
                        progress_callback(
                            pct,
                            f"下载中 {downloaded // 1024}/{total_size // 1024} KB"
                        )

                return b''.join(chunks)

            except ImportError:
                # urllib 回退
                try:
                    import urllib.request
                    with urllib.request.urlopen(
                        url, timeout=DOWNLOAD_TIMEOUT
                    ) as f:
                        return f.read()
                except Exception as e:
                    print(f"[PluginUpdater] urllib 下载失败: {e}")
            except Exception as e:
                print(f"[PluginUpdater] 下载异常: {e}")
            finally:
                # F1 修复：finally 保证 resp 关闭
                if resp is not None:
                    try:
                        resp.close()
                    except Exception:
                        pass'''


def fix_f1(no_backup: bool) -> str:
    path = ROOT / "infrastructure" / "plugin_updater.py"
    if not path.exists():
        print_fail("plugin_updater.py 不存在")
        return 'failed'

    content = read_text(path)

    if F1_MARKER in content:
        print_skip("F1 已修复")
        return 'skipped'

    cnt = content.count(F1_OLD)
    if cnt == 0:
        print_fail("F1 锚点未找到")
        print_info("文件可能已被手动修改，请提供 _download_update 当前内容")
        return 'failed'
    if cnt > 1:
        print_fail(f"F1 锚点重复 {cnt} 次")
        return 'failed'

    new_content = content.replace(F1_OLD, F1_NEW, 1)

    try:
        compile(new_content, str(path), 'exec')
    except SyntaxError as e:
        print_fail(f"F1 语法错误: line {e.lineno}: {e.msg}")
        return 'failed'

    if not no_backup:
        backup(path)
    if not write_text(path, new_content):
        return 'failed'
    print_ok("F1 plugin_updater.py 已修复")
    return 'applied'


# ============================================================
# F2: 覆盖 close_review_v2.py
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
    ("P0-4",  "apply_all_patches 新 marker（归档后）",
     "_archive/fixes/apply_all_patches.py", "in", "青草枯荣，野火重生"),
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
    parser.add_argument('--archive', action='store_true')
    args = parser.parse_args()

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


def fix_f2(no_backup: bool) -> str:
    path = ROOT / "close_review_v2.py"
    if not no_backup and path.exists():
        backup(path)
    if not write_text(path, CLOSE_REVIEW_V2):
        return 'failed'
    print_ok("F2 close_review_v2.py 已覆盖")
    return 'applied'


# ============================================================
# F3: 覆盖 tests/test_outline_end_lines.py
# ============================================================
TEST_OUTLINE = r'''# -*- coding: utf-8 -*-
"""outline_panel._compute_end_lines 边界测试（P1-B2）"""
import pytest


def _make_panel(qapp):
    """用 qapp fixture 真实构造 OutlinePanel"""
    try:
        from ui.outline_panel import OutlinePanel
    except ImportError:
        pytest.skip("outline_panel 不可用")
    return OutlinePanel()


def _make_node(name, type_, line, indent):
    try:
        from ui.outline_panel import SymbolNode
    except ImportError:
        pytest.skip("SymbolNode 不可用")
    return SymbolNode(name=name, type=type_, line=line, indent=indent)


class TestComputeEndLines:

    def test_simple_sequence(self, qapp):
        panel = _make_panel(qapp)
        symbols = [
            _make_node("a", "function", 0, 0),
            _make_node("b", "function", 10, 0),
            _make_node("c", "function", 20, 0),
        ]
        panel._compute_end_lines(symbols)
        assert symbols[0].end_line == 9
        assert symbols[1].end_line == 19
        assert symbols[2].end_line == 20

    def test_nested(self, qapp):
        panel = _make_panel(qapp)
        symbols = [
            _make_node("cls", "class", 0, 0),
            _make_node("m1", "method", 5, 4),
            _make_node("m2", "method", 10, 4),
            _make_node("func", "function", 20, 0),
        ]
        panel._compute_end_lines(symbols)
        assert symbols[0].end_line == 19
        assert symbols[1].end_line == 9
        assert symbols[2].end_line == 19
        assert symbols[3].end_line == 20

    def test_empty(self, qapp):
        panel = _make_panel(qapp)
        panel._compute_end_lines([])  # 不崩即可

    def test_single(self, qapp):
        panel = _make_panel(qapp)
        symbols = [_make_node("only", "function", 5, 0)]
        panel._compute_end_lines(symbols)
        assert symbols[0].end_line == 5
'''


def fix_f3(no_backup: bool) -> str:
    path = ROOT / "tests" / "test_outline_end_lines.py"
    if not no_backup and path.exists():
        backup(path)
    if not write_text(path, TEST_OUTLINE):
        return 'failed'
    print_ok("F3 test_outline_end_lines.py 已覆盖")
    return 'applied'


# ============================================================
# F4: 覆盖 tests/test_plugin_updater_close.py
# ============================================================
TEST_UPDATER = r'''# -*- coding: utf-8 -*-
"""plugin_updater 取消下载后连接关闭（P1-A3 / F1）"""
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
        """取消下载后 resp 也应被关闭"""
        updater = self._make_updater()
        updater._cancelled = True

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.headers = {'content-length': '10000'}
        fake_resp.iter_content = lambda chunk_size: iter(
            [b"x" * chunk_size] * 100
        )

        # 修复 patch 路径：plugin_updater 内部用局部 import requests，
        # 所以必须 patch 全局 requests.get
        with patch('requests.get', return_value=fake_resp):
            result = updater._download_update(
                "http://example.com/fake.zip", "test"
            )

        assert result is None
        assert fake_resp.close.called

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


def fix_f4(no_backup: bool) -> str:
    path = ROOT / "tests" / "test_plugin_updater_close.py"
    if not no_backup and path.exists():
        backup(path)
    if not write_text(path, TEST_UPDATER):
        return 'failed'
    print_ok("F4 test_plugin_updater_close.py 已覆盖")
    return 'applied'


# ============================================================
# F5: 重命名 ui/nippet_market_dialog.py
# ============================================================
def fix_f5(no_backup: bool) -> str:
    wrong = ROOT / "ui" / "nippet_market_dialog.py"
    right = ROOT / "ui" / "snippet_market_dialog.py"

    if not wrong.exists():
        if right.exists():
            print_skip("F5 文件名已正确")
            return 'skipped'
        print_fail("F5 两个文件都不存在")
        return 'failed'

    if right.exists():
        print_fail(f"F5 目标文件已存在: {right.name}")
        return 'failed'

    if no_backup:
        try:
            wrong.rename(right)
            print_ok(f"F5 {wrong.name} → {right.name}")
            return 'applied'
        except Exception as e:
            print_fail(f"F5 重命名失败: {e}")
            return 'failed'

    # 用 git mv 保留历史
    import subprocess
    try:
        r = subprocess.run(
            ['git', 'mv', str(wrong.relative_to(ROOT)),
             str(right.relative_to(ROOT))],
            cwd=ROOT, capture_output=True, text=True,
        )
        if r.returncode == 0:
            print_ok(f"F5 git mv {wrong.name} → {right.name}")
            return 'applied'
    except Exception:
        pass

    # 回退普通 rename
    try:
        wrong.rename(right)
        print_ok(f"F5 {wrong.name} → {right.name}")
        return 'applied'
    except Exception as e:
        print_fail(f"F5 重命名失败: {e}")
        return 'failed'


# ============================================================
# F6: 删除 close_review.py（有语法错误，已被 v2 取代）
# ============================================================
def fix_f6(no_backup: bool) -> str:
    path = ROOT / "close_review.py"
    if not path.exists():
        print_skip("F6 close_review.py 已不存在")
        return 'skipped'

    if no_backup:
        try:
            path.unlink()
            print_ok("F6 close_review.py 已删除")
            return 'applied'
        except Exception as e:
            print_fail(f"F6 删除失败: {e}")
            return 'failed'

    # 用 git rm
    import subprocess
    try:
        r = subprocess.run(
            ['git', 'rm', 'close_review.py'],
            cwd=ROOT, capture_output=True, text=True,
        )
        if r.returncode == 0:
            print_ok("F6 git rm close_review.py")
            return 'applied'
    except Exception:
        pass

    try:
        path.unlink()
        print_ok("F6 close_review.py 已删除")
        return 'applied'
    except Exception as e:
        print_fail(f"F6 删除失败: {e}")
        return 'failed'


# ============================================================
# 主流程
# ============================================================
FIXES = [
    ("F1", "plugin_updater.py A3（CRLF 归一化）", fix_f1),
    ("F2", "覆盖 close_review_v2.py", fix_f2),
    ("F3", "覆盖 test_outline_end_lines.py", fix_f3),
    ("F4", "覆盖 test_plugin_updater_close.py", fix_f4),
    ("F5", "重命名 ui/nippet_market_dialog.py", fix_f5),
    ("F6", "删除 close_review.py", fix_f6),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--only', type=str, default='')
    args = parser.parse_args()

    print_header("青草编辑器最终收尾")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")

    fixes = FIXES
    if args.only:
        only = {x.strip().upper() for x in args.only.split(',')}
        fixes = [f for f in fixes if f[0] in only]

    if args.dry_run:
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
        mark = {'applied': '✓', 'skipped': '-', 'failed': '✗'}[r]
        print(f"  {mark} {pid}: {name} [{r}]")
        if r == 'applied': applied += 1
        elif r == 'skipped': skipped += 1
        else: failed += 1

    print()
    if failed:
        print(f"✗ {failed} 项失败")
        return 1
    print(f"✓ 完成（应用 {applied} 项，跳过 {skipped} 项）")
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