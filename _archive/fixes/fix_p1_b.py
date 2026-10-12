#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - P1-B UI 层修复
==============================
修复 8 项 UI 层 P1 问题。

  B1  explorer /select, 参数被拆成两个 → 不定位文件
      （directory_tree.py / tabs.py / global_search_panel.py 三处）

  B2  outline_panel._compute_end_lines 逻辑错
      有子节点的符号 end_line 被设为子节点起始行，
      最后一个符号 end_line = 自己起始行

  B3  outline_panel 只监听 file_opened，同一文件编辑不刷新

  B4  editor_view._smart_home 把 col（字节）与 indent（字符）比较

  B5  terminal_panel 子线程直接操作 QPlainTextEdit（跨线程 UI）

  B6  welcome_widget.StatsPanel 读从未写入的 onboarding.json

  B7  status_bar_widgets.GitBranchLabel 触发双重信号

  B8  theme_market._on_preview 快速连点互相覆盖

特性：
  - 幂等
  - 每项独立处理
  - 修改前备份 *.bak.p1b
  - Python 文件修改后 compile() 验证

用法：
    python fix_p1_b.py --dry-run
    python fix_p1_b.py
    python fix_p1_b.py --only B1,B5
"""

import os
import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple, List, Callable, Dict

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.p1b"


# ============================================================
# 输出
# ============================================================
def print_header(t): print(f"\n{'=' * 60}\n{t}\n{'=' * 60}")
def print_ok(m):   print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")


# ============================================================
# 工具
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


def apply_replace(path: Path, old: str, new: str,
                  marker: str, no_backup: bool) -> str:
    if not path.exists():
        print_fail(f"{path.relative_to(ROOT)}: 文件不存在")
        return 'failed'
    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"{path.relative_to(ROOT)}: 读取失败 ({e})")
        return 'failed'

    if marker and marker in content:
        print_skip(f"{path.relative_to(ROOT)}: 已修复")
        return 'skipped'

    cnt = content.count(old)
    if cnt == 0:
        print_fail(f"{path.relative_to(ROOT)}: 锚点未找到")
        for line in old.split('\n')[:3]:
            print(f"      | {line}")
        return 'failed'
    if cnt > 1:
        print_fail(f"{path.relative_to(ROOT)}: 锚点重复 {cnt} 次")
        return 'failed'

    new_content = content.replace(old, new, 1)

    if path.suffix == '.py':
        ok, err = validate_python(new_content, str(path))
        if not ok:
            print_fail(f"{path.relative_to(ROOT)}: 语法错误 ({err})")
            return 'failed'

    if not write_back(path, new_content, no_backup):
        return 'failed'

    print_ok(f"{path.relative_to(ROOT)}: 已修复")
    return 'applied'


def apply_multi(path: Path,
                replacements: List[Tuple[str, str]],
                marker: str,
                no_backup: bool) -> str:
    """多段替换，全或无"""
    if not path.exists():
        print_fail(f"{path.relative_to(ROOT)}: 文件不存在")
        return 'failed'
    try:
        content = path.read_text(encoding='utf-8')
    except Exception as e:
        print_fail(f"{path.relative_to(ROOT)}: 读取失败 ({e})")
        return 'failed'

    if marker and marker in content:
        print_skip(f"{path.relative_to(ROOT)}: 已修复")
        return 'skipped'

    for i, (old, _) in enumerate(replacements):
        cnt = content.count(old)
        if cnt == 0:
            print_fail(
                f"{path.relative_to(ROOT)}: 第 {i+1} 段锚点未找到"
            )
            for line in old.split('\n')[:3]:
                print(f"      | {line}")
            return 'failed'
        if cnt > 1:
            print_fail(
                f"{path.relative_to(ROOT)}: 第 {i+1} 段锚点重复 {cnt} 次"
            )
            return 'failed'

    new_content = content
    for old, new in replacements:
        new_content = new_content.replace(old, new, 1)

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
# B1: explorer /select,
# ============================================================
B1_MARKER = "# P1-B1: /select, 必须作为单个参数"

def fix_b1(no_backup: bool) -> str:
    """三处文件都要修。任一失败则 failed，任一 applied 则 applied。"""
    results = []

    # ---- 1. ui/directory_tree.py ----
    p1 = ROOT / "ui" / "directory_tree.py"
    results.append(apply_replace(
        p1,
        old="""            if sys.platform == 'win32':
                subprocess.Popen(['explorer', '/select,',
                                   path.replace('/', '\\\\')])""",
        new="""            if sys.platform == 'win32':
                # P1-B1: /select, 必须作为单个参数
                # 原写法 ['explorer', '/select,', path] 会打开目录
                # 但不定位文件，因为 explorer 要求 /select,<path>
                # 是同一个参数。
                subprocess.Popen(
                    ['explorer',
                     f'/select,{path.replace("/", chr(92))}']
                )""",
        marker=B1_MARKER,
        no_backup=no_backup,
    ))

    # ---- 2. app/tabs.py ----
    p2 = ROOT / "app" / "tabs.py"
    results.append(apply_replace(
        p2,
        old="""            if sys.platform == 'win32':
                subprocess.Popen(
                    ['explorer', '/select,',
                     filepath.replace('/', '\\\\')]
                )""",
        new="""            if sys.platform == 'win32':
                # P1-B1: /select, 必须作为单个参数
                subprocess.Popen(
                    ['explorer',
                     f'/select,{filepath.replace("/", chr(92))}']
                )""",
        marker=B1_MARKER,
        no_backup=no_backup,
    ))

    # ---- 3. ui/global_search_panel.py ----
    p3 = ROOT / "ui" / "global_search_panel.py"
    results.append(apply_replace(
        p3,
        old="""            if sys.platform == 'win32':
                subprocess.Popen(['explorer', '/select,',
                                   filepath.replace('/', '\\\\')])""",
        new="""            if sys.platform == 'win32':
                # P1-B1: /select, 必须作为单个参数
                subprocess.Popen(
                    ['explorer',
                     f'/select,{filepath.replace("/", chr(92))}']
                )""",
        marker=B1_MARKER,
        no_backup=no_backup,
    ))

    if 'failed' in results:
        return 'failed'
    if 'applied' in results:
        return 'applied'
    return 'skipped'


# ============================================================
# B2: outline_panel _compute_end_lines
# ============================================================
B2_MARKER = "# P1-B2: 计算 end_line 的正确方式"

B2_OLD = """    def _compute_end_lines(self, symbols: List[SymbolNode]):
        \"\"\"计算每个符号的结束行\"\"\"
        for i, symbol in enumerate(symbols):
            if i + 1 < len(symbols):
                next_symbol = symbols[i + 1]
                # 如果下一个符号的缩进大于当前，则作为子节点，不算结束
                if next_symbol.indent > symbol.indent:
                    symbol.end_line = next_symbol.line
                else:
                    symbol.end_line = next_symbol.line - 1
            else:
                symbol.end_line = symbol.line"""

B2_NEW = """    def _compute_end_lines(self, symbols: List[SymbolNode]):
        \"\"\"计算每个符号的结束行。

        修复说明（P1-B2）:
            原实现只看"下一个符号的缩进"：
              - 有子节点的符号，end_line 被设为子节点起始行（错）
              - 最后一个符号 end_line = 自己起始行（错）
            结果：跟随光标高亮时命中错误的符号。

            修复：向后扫描第一个缩进 <= 自己的符号，
                 其前一行为自己的 end_line。最后一个符号延伸
                 到文件最末符号的位置。
        \"\"\"
        if not symbols:
            return

        # P1-B2: 计算 end_line 的正确方式
        max_line = max(s.line for s in symbols)
        n = len(symbols)

        for i, symbol in enumerate(symbols):
            end_line = max_line
            for j in range(i + 1, n):
                if symbols[j].indent <= symbol.indent:
                    end_line = symbols[j].line - 1
                    break
            symbol.end_line = max(symbol.line, end_line)"""


def fix_b2(no_backup: bool) -> str:
    path = ROOT / "ui" / "outline_panel.py"
    return apply_replace(path, B2_OLD, B2_NEW,
                         marker=B2_MARKER, no_backup=no_backup)


# ============================================================
# B3: outline_panel 监听文件修改
# ============================================================
B3_MARKER = "# P1-B3: 监听文本变化，强制刷新大纲"

B3_OLD = """    def _connect_signals(self):
        \"\"\"连接事件总线信号\"\"\"
        try:
            bus.cursor_moved.connect(self._on_cursor_moved)
            bus.file_opened.connect(self._on_file_opened)
        except Exception:
            pass"""

B3_NEW = """    def _connect_signals(self):
        \"\"\"连接事件总线信号\"\"\"
        try:
            bus.cursor_moved.connect(self._on_cursor_moved)
            bus.file_opened.connect(self._on_file_opened)
            # P1-B3: 监听文本变化，强制刷新大纲
            # 原实现只监听 file_opened，同一文件编辑后不刷新。
            try:
                bus.file_modified.connect(self._on_file_modified)
                bus.file_saved.connect(self._on_file_modified)
            except Exception:
                pass
        except Exception:
            pass

    def _on_file_modified(self, event):
        \"\"\"文件内容变化 → 强制重新解析。

        P1-B3 修复：
            直接把 _current_filepath 置空，让 _do_update 中的
            "filepath != _current_filepath" 分支触发重新解析。
        \"\"\"
        try:
            self._current_filepath = None
            self.schedule_update()
        except Exception:
            pass"""


def fix_b3(no_backup: bool) -> str:
    path = ROOT / "ui" / "outline_panel.py"
    return apply_replace(path, B3_OLD, B3_NEW,
                         marker=B3_MARKER, no_backup=no_backup)


# ============================================================
# B4: editor_view _smart_home
# ============================================================
B4_MARKER = "# P1-B4: col 是字节偏移"

B4_OLD = """        if col > indent:
            # 跳到行首非空白
            target = line_start + indent_bytes
        elif col == indent and indent > 0:
            # 跳到绝对行首
            target = line_start
        elif col == 0:
            # 循环回到行首非空白
            target = line_start + indent_bytes
        else:
            # 默认跳到行首
            target = line_start"""

B4_NEW = """        # P1-B4: col 是字节偏移，必须与 indent_bytes 比较（而非字符数 indent）
        # 否则全角空格（U+3000，UTF-8 下 3 字节）行为异常
        if col > indent_bytes:
            # 跳到行首非空白
            target = line_start + indent_bytes
        elif col == indent_bytes and indent_bytes > 0:
            # 跳到绝对行首
            target = line_start
        elif col == 0:
            # 循环回到行首非空白
            target = line_start + indent_bytes
        else:
            # 默认跳到行首
            target = line_start"""


def fix_b4(no_backup: bool) -> str:
    path = ROOT / "ui" / "editor_view.py"
    return apply_replace(path, B4_OLD, B4_NEW,
                         marker=B4_MARKER, no_backup=no_backup)


# ============================================================
# B5: terminal_panel 子线程 UI 操作
# ============================================================
B5_MARKER_1 = "# P1-B5: 子线程通过信号转发输出"

B5_OLD_1 = """class TerminalPanel(QDockWidget):
    \"\"\"集成终端面板\"\"\"

    def __init__(self, main_window=None, parent=None):
        super().__init__("终端", parent or main_window)
        self.main_window = main_window
        self.setObjectName("TerminalPanel")
        self.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)

        self.process = None
        self._cwd = os.getcwd()

        self._build_ui()
        self._apply_style()"""

B5_NEW_1 = """class TerminalPanel(QDockWidget):
    \"\"\"集成终端面板\"\"\"

    # P1-B5: 子线程通过信号转发输出
    # Qt 不允许从非主线程访问 QWidget，原实现 _read_output 在
    # 子线程里直接调 _append_output（QPlainTextEdit.textCursor 等），
    # 轻则渲染错乱，重则进程崩溃。
    _output_signal = pyqtSignal(str)

    def __init__(self, main_window=None, parent=None):
        super().__init__("终端", parent or main_window)
        self.main_window = main_window
        self.setObjectName("TerminalPanel")
        self.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)

        self.process = None
        self._cwd = os.getcwd()

        self._build_ui()
        self._apply_style()

        # P1-B5: 连接信号（跨线程安全）
        self._output_signal.connect(self._append_output)"""


B5_OLD_2 = """    def _read_output(self):
        \"\"\"读取输出\"\"\"
        try:
            while self.process and self.process.poll() is None:
                line = self.process.stdout.readline()
                if not line:
                    break
                self._append_output(line)
        except Exception:
            pass"""

B5_NEW_2 = """    def _read_output(self):
        \"\"\"读取输出（子线程）

        P1-B5: 通过信号转发，不直接操作 QWidget。
        \"\"\"
        try:
            while self.process and self.process.poll() is None:
                line = self.process.stdout.readline()
                if not line:
                    break
                # 通过信号转发到主线程
                self._output_signal.emit(line)
        except Exception:
            pass"""


def fix_b5(no_backup: bool) -> str:
    path = ROOT / "ui" / "terminal_panel.py"
    return apply_multi(
        path,
        [(B5_OLD_1, B5_NEW_1), (B5_OLD_2, B5_NEW_2)],
        marker=B5_MARKER_1,
        no_backup=no_backup,
    )


# ============================================================
# B6: welcome_widget StatsPanel 数据源
# ============================================================
B6_MARKER = "# P1-B6: 改用 core.usage_stats"

B6_OLD = """    def _load_stats(self):
        \"\"\"加载统计数据\"\"\"
        try:
            path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data", "onboarding.json"
            )

            if os.path.exists(path):
                import json
                with open(path, 'r', encoding='utf-8') as f:
                    stats = json.load(f)

                self.update_stat("saves", stats.get('saves', 0))
                self.update_stat("files_opened",
                                  stats.get('files_opened', 0))
                self.update_stat("lines_edited",
                                  stats.get('lines_edited', 0))
                self.update_stat("macros_used",
                                  stats.get('macros_used', 0))
        except Exception as e:
            print(f"[StatsPanel] 加载统计失败: {e}")"""

B6_NEW = """    def _load_stats(self):
        \"\"\"加载统计数据。

        P1-B6: 改用 core.usage_stats

        原实现读取 data/onboarding.json，但该文件从未被任何
        模块写入，导致统计面板永远显示 0。改用统一的
        core.usage_stats（数据源：telemetry / session /
        local_completer）。
        \"\"\"
        try:
            from core.usage_stats import get_usage_stats
            snap = get_usage_stats().get_snapshot()

            self.update_stat("saves", int(snap.files_saved))
            self.update_stat("files_opened", int(snap.files_opened))
            # lines_edited：用累计编辑时长（秒）近似
            self.update_stat(
                "lines_edited", int(snap.total_edit_time)
            )
            # macros_used：用加载插件数近似
            self.update_stat(
                "macros_used", int(snap.plugins_loaded)
            )
        except ImportError as e:
            print(f"[StatsPanel] core.usage_stats 不可用: {e}")
        except Exception as e:
            print(f"[StatsPanel] 加载统计失败: {e}")"""


def fix_b6(no_backup: bool) -> str:
    path = ROOT / "ui" / "welcome_widget.py"
    return apply_replace(path, B6_OLD, B6_NEW,
                         marker=B6_MARKER, no_backup=no_backup)


# ============================================================
# B7: status_bar_widgets GitBranchLabel 双重信号
# ============================================================
B7_MARKER = "# P1-B7: 阻止 super() 触发 clicked"

B7_OLD = """class GitBranchLabel(ClickableLabel):
    \"\"\"Git 分支标签（点击打开 Git 面板）\"\"\"

    git_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("", parent, "点击打开 Git 面板")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.text():
            self.git_clicked.emit()
        super().mousePressEvent(event)"""

B7_NEW = """class GitBranchLabel(ClickableLabel):
    \"\"\"Git 分支标签（点击打开 Git 面板）\"\"\"

    git_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("", parent, "点击打开 Git 面板")

    def mousePressEvent(self, event):
        # P1-B7: 阻止 super() 触发 clicked
        # 基类 ClickableLabel.mousePressEvent 会 emit self.clicked，
        # 如果这里也调 super()，一次点击会触发 clicked + git_clicked
        # 两个信号。
        if event.button() == Qt.LeftButton and self.text():
            self.git_clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)"""


def fix_b7(no_backup: bool) -> str:
    path = ROOT / "ui" / "status_bar_widgets.py"
    return apply_replace(path, B7_OLD, B7_NEW,
                         marker=B7_MARKER, no_backup=no_backup)


# ============================================================
# B8: theme_market _on_preview 竞态
# ============================================================
B8_MARKER = "# P1-B8: generation counter 防止预览覆盖"

B8_OLD = """        # 临时应用
        try:
            for i in range(self.main_window.tabs.count()):
                loader.apply(self.main_window.tabs.widget(i), loaded)
            if loaded.qss:
                self.main_window.setStyleSheet(loaded.qss)

            # 3 秒后恢复
            def restore():
                if current:
                    for i in range(self.main_window.tabs.count()):
                        loader.apply(self.main_window.tabs.widget(i), current)
                    if current.qss:
                        self.main_window.setStyleSheet(current.qss)

            QTimer.singleShot(3000, restore)
        except Exception as e:
            QMessageBox.warning(self, "预览失败", str(e))"""

B8_NEW = """        # P1-B8: generation counter 防止预览覆盖
        # 用户 3 秒内连点不同主题的"预览"，多个 restore 定时器
        # 会依次触发，把界面恢复成错误的状态。
        # 每次预览递增 generation，只有最新的 restore 才执行。
        self._preview_gen = getattr(self, '_preview_gen', 0) + 1
        gen = self._preview_gen

        # 临时应用
        try:
            for i in range(self.main_window.tabs.count()):
                loader.apply(self.main_window.tabs.widget(i), loaded)
            if loaded.qss:
                self.main_window.setStyleSheet(loaded.qss)

            # 3 秒后恢复
            def restore():
                # 有更新的预览请求 → 跳过本次恢复
                if getattr(self, '_preview_gen', 0) != gen:
                    return
                if current:
                    for i in range(self.main_window.tabs.count()):
                        loader.apply(
                            self.main_window.tabs.widget(i), current
                        )
                    if current.qss:
                        self.main_window.setStyleSheet(current.qss)

            QTimer.singleShot(3000, restore)
        except Exception as e:
            QMessageBox.warning(self, "预览失败", str(e))"""


def fix_b8(no_backup: bool) -> str:
    path = ROOT / "ui" / "theme_market.py"
    return apply_replace(path, B8_OLD, B8_NEW,
                         marker=B8_MARKER, no_backup=no_backup)


# ============================================================
# 主流程
# ============================================================
FIXES: List[Tuple[str, str, Callable[[bool], str]]] = [
    ("B1", "explorer /select, 参数合并（3 处）", fix_b1),
    ("B2", "outline_panel._compute_end_lines 逻辑修正", fix_b2),
    ("B3", "outline_panel 监听文件修改", fix_b3),
    ("B4", "editor_view._smart_home 字节偏移比较", fix_b4),
    ("B5", "terminal_panel 子线程 UI 操作", fix_b5),
    ("B6", "welcome_widget.StatsPanel 数据源", fix_b6),
    ("B7", "status_bar_widgets 双重信号", fix_b7),
    ("B8", "theme_market 预览竞态", fix_b8),
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="青草编辑器 P1-B UI 层修复"
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--only', type=str, default='',
                        help='只处理指定项：B1,B2,...')
    args = parser.parse_args()

    print_header("青草编辑器 P1-B UI 层修复")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")
    print(f"  备份:     {'禁用' if args.no_backup else '启用'}")

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
          "for f in ['ui/directory_tree.py', 'app/tabs.py', "
          "'ui/global_search_panel.py', 'ui/outline_panel.py', "
          "'ui/editor_view.py', 'ui/terminal_panel.py', "
          "'ui/welcome_widget.py', 'ui/status_bar_widgets.py', "
          "'ui/theme_market.py']]; print('OK')\"")
    print("  2. 启动编辑器: python main.py")
    print("  3. 验证 B1: 目录树右键 → 在文件管理器中显示")
    print("  4. 验证 B2/B3: 打开 py 文件，编辑，看大纲是否跟随")
    print("  5. 验证 B5: 打开终端，运行 dir/ls，应稳定输出")
    print("  6. 验证 B6: 回到欢迎页，看统计是否非 0")
    print("  7. 验证 B8: 主题市场快速连点两个主题的预览")
    print()
    print("清理备份:")
    print("  Windows:     del /s *.bak.p1b")
    print("  Linux/macOS: find . -name '*.bak.p1b' -delete")

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