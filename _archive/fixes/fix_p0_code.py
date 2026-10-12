#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - P0 代码层修复
============================
修复 5 项代码层 P0 问题：

  P0-C1  ui/task_panel.py 缺少 QLabel 导入
         打开任务面板必崩（NameError）。

  P0-C2  ui/panels.py SearchBar._search 调用签名错误
         SearchEngine.search() 不接受参数，所有查找/替换
         快捷键都会 TypeError 被 except 吞掉。

  P0-C3  ui/mixins/file_ops_mixin.py _new_window NameError
         MainWindow 未导入，点"新窗口"无反应。

  P0-C4  ui/main_window.py _toggle_column_mode 菜单触发反了
         菜单非 checkable QAction → triggered 传 checked=False
         → 从菜单点击只会"关闭列模式"。

  P0-C5  tests/ 污染用户 QSettings
         run_all.py 用 unittest discover，绕过 conftest.py
         的所有 fixture；test_smoke.py 直接 new Preferences()
         会写注册表 / plist / ~/.config。

特性：
  - 幂等
  - 每项独立处理，一项失败不影响其他
  - 修改前备份 *.bak.p0code
  - Python 文件修改后 compile() 验证

用法：
    python fix_p0_code.py --dry-run
    python fix_p0_code.py
    python fix_p0_code.py --no-backup
    python fix_p0_code.py --only C2
"""

import os
import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple, List

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.p0code"


# ============================================================
# 输出辅助
# ============================================================
def print_header(t): print(f"\n{'=' * 60}\n{t}\n{'=' * 60}")
def print_ok(m):   print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")


# ============================================================
# 备份 / 写回 / 语法验证
# ============================================================
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


def apply_replace(path: Path,
                  old: str, new: str,
                  marker: str,
                  no_backup: bool) -> str:
    """
    通用替换。返回 'applied' / 'skipped' / 'failed'
    """
    if not path.exists():
        print_fail(f"{path.relative_to(ROOT)}: 文件不存在")
        return 'failed'

    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"{path.relative_to(ROOT)}: 读取失败 ({e})")
        return 'failed'

    # 幂等
    if marker and marker in content:
        print_skip(f"{path.relative_to(ROOT)}: 已修复")
        return 'skipped'

    cnt = content.count(old)
    if cnt == 0:
        print_fail(f"{path.relative_to(ROOT)}: 锚点未找到")
        print_info("期望锚点前 3 行：")
        for line in old.split('\n')[:3]:
            print(f"      | {line}")
        return 'failed'

    if cnt > 1:
        print_fail(f"{path.relative_to(ROOT)}: 锚点重复 {cnt} 次")
        return 'failed'

    new_content = content.replace(old, new, 1)

    # Python 语法验证
    if path.suffix == '.py':
        ok, err = validate_python(new_content, str(path))
        if not ok:
            print_fail(f"{path.relative_to(ROOT)}: 语法错误 ({err})")
            return 'failed'

    if not write_back(path, new_content, no_backup):
        return 'failed'

    print_ok(f"{path.relative_to(ROOT)}: 已修复")
    return 'applied'


# ============================================================
# P0-C1: task_panel.py 补 QLabel 导入
# ============================================================
C1_OLD = """from PyQt5.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget,
    QTreeWidgetItem, QPushButton, QPlainTextEdit, QMenu,
    QMessageBox, QToolButton
)"""

C1_NEW = """from PyQt5.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget,
    QTreeWidgetItem, QPushButton, QPlainTextEdit, QMenu,
    QMessageBox, QToolButton, QLabel
)"""


def fix_c1(no_backup: bool) -> str:
    path = ROOT / "ui" / "task_panel.py"
    if not path.exists():
        print_fail("ui/task_panel.py 不存在")
        return 'failed'

    # 幂等 marker: 检查 QLabel 是否已在导入行
    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"读取失败: {e}")
        return 'failed'

    # 简单检查：导入块里是否已包含 QLabel
    header = content[:content.find(')') + 1] if ')' in content else content[:500]
    if 'QLabel' in header and 'from PyQt5.QtWidgets import' in header:
        print_skip("QLabel 已导入")
        return 'skipped'

    return apply_replace(path, C1_OLD, C1_NEW,
                         marker="QToolButton, QLabel\n)",  # 用于幂等
                         no_backup=no_backup)


# ============================================================
# P0-C2: panels.py SearchBar._search 签名修正
# ============================================================
C2_MARKER = "# 修复 P0-C2: SearchEngine.search() 不接受参数"

C2_OLD = '''        try:
            # 使用搜索引擎
            engine = SearchEngine(proxy.document.provider, options)
            pos = proxy.get_current_pos()

            forward = (direction == SearchDirection.FORWARD)
            match = engine.search(pattern, pos, forward)

            if match:
                # 选中匹配
                start, end = match
                proxy.set_selection(start, end)

                # 居中显示
                try:
                    line = proxy.sc.SendScintilla(
                        proxy.sc.SCI_LINEFROMPOSITION, start
                    )
                    proxy.sc.ensureLineVisible(line)
                except Exception:
                    pass

                self._update_match_count(1, 1, True)
            else:
                # 尝试循环搜索
                wrap_pos = 0 if forward else proxy.sc.SendScintilla(
                    proxy.sc.SCI_GETLENGTH
                )
                match = engine.search(pattern, wrap_pos, forward)

                if match:
                    start, end = match
                    proxy.set_selection(start, end)
                    self._update_match_count(1, 1, True)
                    self._show_message("已从另一端继续搜索", "info")
                else:
                    self._update_match_count(0, 0, False)
                    self._show_message("未找到匹配", "warning")

        except Exception as e:
            print(f"[SearchBar] 搜索失败: {e}")'''

C2_NEW = '''        try:
            # 修复 P0-C2: SearchEngine.search() 不接受参数
            # 原代码 engine.search(pattern, pos, forward) 会抛
            # TypeError，被 except 吞掉，用户表现为"按了没反应"。
            # 改为：一次性拿到全部匹配，再在 Python 层做
            # next/prev + 循环。
            engine = SearchEngine(proxy.document.provider, options)
            result = engine.search()  # 返回 SearchResult

            if result.error:
                self._update_match_count(0, 0, False)
                self._show_message(
                    f"搜索失败: {result.error}", "error"
                )
                return

            if result.is_empty:
                self._update_match_count(0, 0, False)
                self._show_message("未找到匹配", "warning")
                return

            pos = proxy.get_current_pos()
            forward = (direction == SearchDirection.FORWARD)

            # 在 Python 层找下一个 / 上一个
            match = None
            if forward:
                for m in result.matches:
                    if m.start > pos:
                        match = m
                        break
            else:
                for m in reversed(result.matches):
                    if m.end <= pos:
                        match = m
                        break

            # 循环到另一端
            if match is None:
                match = (result.matches[0] if forward
                         else result.matches[-1])
                self._show_message("已从另一端继续搜索", "info")

            # 选中并居中
            proxy.set_selection(match.start, match.end)
            try:
                line = proxy.sc.SendScintilla(
                    proxy.sc.SCI_LINEFROMPOSITION, match.start
                )
                proxy.sc.ensureLineVisible(line)
            except Exception:
                pass

            # 更新计数（这里简化：显示 "N/M" 中的总数 M）
            # 完整实现需要一个"当前匹配索引"跟踪器，此处从简。
            self._update_match_count(1, result.count, True)

        except Exception as e:
            print(f"[SearchBar] 搜索失败: {e}")'''


def fix_c2(no_backup: bool) -> str:
    path = ROOT / "ui" / "panels.py"
    return apply_replace(path, C2_OLD, C2_NEW,
                         marker=C2_MARKER,
                         no_backup=no_backup)


# ============================================================
# P0-C3: file_ops_mixin.py _new_window 延迟导入
# ============================================================
C3_MARKER = "# 修复 P0-C3: 延迟导入 MainWindow"

C3_OLD = '''    def _new_window(self):
        """打开新窗口"""
        try:
            new_window = MainWindow()
            new_window.show()
        except Exception as e:
            print(f"[MainWindow] 新窗口失败: {e}")'''

C3_NEW = '''    def _new_window(self):
        """打开新窗口"""
        try:
            # 修复 P0-C3: 延迟导入 MainWindow
            # 原实现直接 MainWindow() 会 NameError，
            # 异常被 except 吞掉，用户无感知。
            from ui.main_window import MainWindow
            new_window = MainWindow()
            new_window.show()
        except Exception as e:
            print(f"[MainWindow] 新窗口失败: {e}")'''


def fix_c3(no_backup: bool) -> str:
    path = ROOT / "ui" / "mixins" / "file_ops_mixin.py"
    return apply_replace(path, C3_OLD, C3_NEW,
                         marker=C3_MARKER,
                         no_backup=no_backup)


# ============================================================
# P0-C4: main_window.py _toggle_column_mode 修正
# ============================================================
C4_MARKER = "# 修复 P0-C4: 忽略 triggered 的 checked 参数"

C4_OLD = '''    def _toggle_column_mode(self, checked=None):
        """切换列模式"""
        try:
            if isinstance(checked, bool):
                enabled = checked
            else:
                if hasattr(self, 'column_mode_action'):
                    enabled = not self.column_mode_action.isChecked()
                else:
                    enabled = True

            proxy = self.tabs.current_proxy()
            if proxy and hasattr(proxy, 'set_column_mode'):
                proxy.set_column_mode(enabled)

            if hasattr(self, 'column_mode_action'):
                # 阻断信号避免递归
                self.column_mode_action.blockSignals(True)
                self.column_mode_action.setChecked(enabled)
                self.column_mode_action.blockSignals(False)

            self.status_bar.showMessage(
                "列模式" if enabled else "流模式", 2000
            )
        except Exception as e:
            print(f"[MainWindow] 切换列模式失败: {e}")'''

C4_NEW = '''    def _toggle_column_mode(self, checked=None):
        """切换列模式。

        修复 P0-C4:
            菜单里的"▦ 列模式"用 _add_action 创建的非 checkable
            QAction，triggered 信号固定传 checked=False。
            原代码 `if isinstance(checked, bool): enabled = checked`
            会因此认为"用户想关闭列模式"，从菜单点击无效。

            改为：始终基于工具栏 action 的**真实状态**翻转，
            忽略 triggered 传入的 checked 参数。
        """
        try:
            if hasattr(self, 'column_mode_action'):
                # 修复 P0-C4: 忽略 triggered 的 checked 参数，
                # 始终基于工具栏 action 的当前状态翻转
                enabled = not self.column_mode_action.isChecked()
                self.column_mode_action.blockSignals(True)
                self.column_mode_action.setChecked(enabled)
                self.column_mode_action.blockSignals(False)
            else:
                # 无工具栏按钮时，退回到 checked 参数
                enabled = not (checked if isinstance(checked, bool)
                               else False)

            proxy = self.tabs.current_proxy()
            if proxy and hasattr(proxy, 'set_column_mode'):
                proxy.set_column_mode(enabled)

            self.status_bar.showMessage(
                "列模式" if enabled else "流模式", 2000
            )
        except Exception as e:
            print(f"[MainWindow] 切换列模式失败: {e}")'''


def fix_c4(no_backup: bool) -> str:
    path = ROOT / "ui" / "main_window.py"
    return apply_replace(path, C4_OLD, C4_NEW,
                         marker=C4_MARKER,
                         no_backup=no_backup)


# ============================================================
# P0-C5: 测试隔离（conftest.py + run_all.py）
# ============================================================
C5A_MARKER = "@pytest.fixture(autouse=True, scope=\"session\")"

C5A_OLD = '''import os
import sys
import tempfile
import shutil
import pytest

# 确保项目根目录在 sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)'''

C5A_NEW = '''import os
import sys

# ============================================================
# QT_QPA_PLATFORM 必须在导入 Qt 之前设置
# ============================================================
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")

import tempfile
import shutil
import pytest

# 确保项目根目录在 sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============================================================
# 全局 autouse fixture: 隔离 QSettings
# ============================================================
@pytest.fixture(autouse=True, scope="session")
def _isolate_qsettings(tmp_path_factory):
    """
    会话级 QSettings 隔离。

    把所有 QSettings 写入重定向到 pytest 临时目录，
    避免污染用户真实配置（Windows 注册表 / macOS plist /
    Linux ~/.config）。

    这样即使测试中途崩溃，也不会影响用户已保存的首选项。

    覆盖范围：
        - unittest.TestCase 里的 QSettings 调用
          （pytest 对 unittest.TestCase 也应用 autouse fixture）
        - 全局单例（EventBus / ActionManager / Preferences）
    """
    from PyQt5.QtCore import QSettings

    ini_dir = str(tmp_path_factory.mktemp("qsettings"))

    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(
        QSettings.IniFormat, QSettings.UserScope, ini_dir
    )
    QSettings.setPath(
        QSettings.IniFormat, QSettings.SystemScope, ini_dir
    )

    yield
    # tmp_path_factory 自动清理，无需手动处理'''


C5B_MARKER = "改用 pytest，fixture 自动生效"

C5B_OLD = '''def run_all():
    loader = unittest.TestLoader()
    start_dir = os.path.dirname(os.path.abspath(__file__))
    suite = loader.discover(start_dir, pattern='test_*.py')

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1'''


C5B_NEW = '''def run_all():
    """
    改用 pytest，fixture 自动生效。

    修复说明（P0-C5）:
        - 原实现用 unittest.TestLoader + TextTestRunner，
          会绕过 conftest.py 中的所有 fixture。
        - 特别是 _isolate_qsettings（autouse）不生效，
          test_smoke.py 里 new Preferences() 会写入
          用户真实配置（Windows 注册表 / macOS plist /
          Linux ~/.config）。
        - pytest 能识别 unittest.TestCase 风格，autouse
          fixture 同样对其生效。
    """
    import pytest

    start_dir = os.path.dirname(os.path.abspath(__file__))
    args = [
        start_dir,
        '-v',
        '--tb=short',
    ]
    return pytest.main(args)'''


def fix_c5(no_backup: bool) -> str:
    """P0-C5 有两个文件：conftest.py + run_all.py"""
    conftest = ROOT / "tests" / "conftest.py"
    run_all = ROOT / "tests" / "run_all.py"

    r1 = apply_replace(conftest, C5A_OLD, C5A_NEW,
                       marker=C5A_MARKER,
                       no_backup=no_backup)

    r2 = apply_replace(run_all, C5B_OLD, C5B_NEW,
                       marker=C5B_MARKER,
                       no_backup=no_backup)

    # 汇总：任意一项 failed 则 failed；否则任一 applied 则 applied
    if 'failed' in (r1, r2):
        return 'failed'
    if 'applied' in (r1, r2):
        return 'applied'
    return 'skipped'


# ============================================================
# 主流程
# ============================================================
FIXES = [
    ("C1", "task_panel.py 补 QLabel 导入", fix_c1),
    ("C2", "panels.py SearchBar._search 签名修正", fix_c2),
    ("C3", "file_ops_mixin.py _new_window 延迟导入", fix_c3),
    ("C4", "main_window.py _toggle_column_mode 修正", fix_c4),
    ("C5", "tests 隔离 QSettings + run_all 改 pytest", fix_c5),
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="青草编辑器 P0 代码层修复"
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--only', type=str, default='',
                        help='只处理指定项：C1,C2,...')
    args = parser.parse_args()

    print_header("青草编辑器 P0 代码层修复")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")
    print(f"  备份:     {'禁用' if args.no_backup else '启用'}")

    # 过滤
    fixes = FIXES
    if args.only:
        only = {x.strip().upper() for x in args.only.split(',')}
        fixes = [f for f in fixes if f[0] in only]

    if args.dry_run:
        print()
        print_info(f"[DRY-RUN] 将处理 {len(fixes)} 项：")
        for pid, name, _ in fixes:
            print_info(f"  {pid}: {name}")
        print()
        print("  去掉 --dry-run 即可应用。")
        return 0

    # 执行
    results = []
    for pid, name, fn in fixes:
        print_header(f"{pid}: {name}")
        r = fn(args.no_backup)
        results.append((pid, name, r))

    # 汇总
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

    print()
    if failed > 0:
        print("=" * 60)
        print(f"✗ 有 {failed} 项失败，请检查上方输出")
        print("=" * 60)
        return 1

    print("=" * 60)
    print(f"✓ 完成（应用 {applied} 项，跳过 {skipped} 项）")
    print("=" * 60)
    print()
    print("验证步骤:")
    print("  1. 语法验证:")
    print("     python -c \"import ast; "
          "[ast.parse(open(f, encoding='utf-8').read()) "
          "for f in ['ui/task_panel.py', 'ui/panels.py', "
          "'ui/mixins/file_ops_mixin.py', 'ui/main_window.py']]; "
          "print('OK')\"")
    print("  2. 启动编辑器:")
    print("     python main.py")
    print("  3. 打开任务面板，不应崩溃")
    print("  4. Ctrl+F 输入关键词，按 Enter，应能跳转")
    print("  5. 帮助 → 新窗口，应打开新窗口")
    print("  6. Alt+C 切换列模式，再切换一次，应来回切换")
    print("  7. 跑测试:")
    print("     python tests/run_all.py")
    print()
    print("清理备份:")
    print("  Windows:     del /s *.bak.p0code")
    print("  Linux/macOS: find . -name '*.bak.p0code' -delete")

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