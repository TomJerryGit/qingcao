#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P1/P2/P3 快速修复批次
========================
修复 5 项：

  P1-4  ui/editor_view.py: 引号自动闭合 + 尊重偏好
  P2-2  ui/main_window.py: 每日技巧手动点击不更新日期
  P2-4  ui/python_console.py: PythonHighlighter 正则合并
  P2-5  ui/directory_tree.py: Git 缓存 TTL 30 秒（可配置）
  P3-1  app/plugins.py: 删除死信号 plugin_loaded/plugin_unloaded

特性:
  - 幂等
  - 每项独立处理
  - 修改前备份 *.bak.batch
  - Python 文件修改后 compile() 验证

用法:
    python fix_batch_quick.py --dry-run
    python fix_batch_quick.py
    python fix_batch_quick.py --only P1-4,P2-2
    python fix_batch_quick.py --no-backup
"""

import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple, List

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.batch"


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
# P1-4: 引号自动闭合
# ============================================================
P1_4_MARKER = "P1-4: 引号自动闭合 + 尊重偏好"

P1_4_OLD = '''    def _on_char_added(self, char_code: int):
        """字符输入后的回调"""
        try:
            char = chr(char_code)

            # 自动补全右符号（无选区时）
            if char in PAIRS and not self.hasSelectedText():
                close_char = PAIRS[char]
                if char != close_char:  # 不是成对的相同字符
                    # 自动插入右符号
                    pos = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)
                    self.SendScintilla(
                        QsciScintilla.SCI_INSERTTEXT, pos,
                        close_char.encode('utf-8')
                    )
                    # 光标保持在原位置
                    self.SendScintilla(QsciScintilla.SCI_GOTOPOS, pos)
        except Exception:
            pass'''

P1_4_NEW = '''    def _on_char_added(self, char_code: int):
        """字符输入后的回调

        P1-4: 引号自动闭合 + 尊重偏好

        原实现用 `if char != close_char` 跳过所有引号（因为
        PAIRS['"'] == '"'），导致：
          - 输入 " 不会自动补 "
          - 而偏好设置里 auto_close_quotes 是打开的

        新实现：
          - 引号也自动闭合
          - 尊重 auto_close_brackets / auto_close_quotes 偏好
          - 引号闭合前检查前一个字符，避免在 don't 里误闭合
        """
        try:
            char = chr(char_code)

            if char not in PAIRS:
                return
            if self.hasSelectedText():
                return

            close_char = PAIRS[char]

            if char == close_char:
                # 引号场景
                if not self.prefs.get("auto_close_quotes", True):
                    return
                # 前面是标识符字符时不闭合（如 don't）
                pos = self.SendScintilla(
                    QsciScintilla.SCI_GETCURRENTPOS
                )
                if pos >= 2:
                    prev_byte = self.SendScintilla(
                        QsciScintilla.SCI_GETCHARAT, pos - 2
                    )
                    if 0x20 < prev_byte < 0x7F:
                        prev_char = chr(prev_byte)
                        if prev_char.isalnum() or prev_char == '_':
                            return
            else:
                # 括号场景
                if not self.prefs.get("auto_close_brackets", True):
                    return

            # 插入闭合符号
            pos = self.SendScintilla(QsciScintilla.SCI_GETCURRENTPOS)
            self.SendScintilla(
                QsciScintilla.SCI_INSERTTEXT, pos,
                close_char.encode('utf-8')
            )
            # 光标保持在原位置
            self.SendScintilla(QsciScintilla.SCI_GOTOPOS, pos)
        except Exception:
            pass'''


def fix_p1_4(no_backup: bool) -> str:
    path = ROOT / "ui" / "editor_view.py"
    return apply_replace(path, P1_4_OLD, P1_4_NEW,
                         marker=P1_4_MARKER,
                         no_backup=no_backup)


# ============================================================
# P2-2: 每日技巧日期
# ============================================================
P2_2_MARKER = "# P2-2: 仅自动触发时更新 last_tip_date"

P2_2_OLD = '''            # 标记今天已弹
            settings.setValue("last_tip_date", today)
            settings.sync()'''

P2_2_NEW = '''            # 标记今天已弹
            # P2-2: 仅自动触发时更新 last_tip_date
            # 原实现手动点击也更新，导致用户当天手动点一次后，
            # 第二天的自动弹出会被抑制到后天。
            if not manual:
                settings.setValue("last_tip_date", today)
                settings.sync()'''


def fix_p2_2(no_backup: bool) -> str:
    path = ROOT / "ui" / "main_window.py"
    return apply_replace(path, P2_2_OLD, P2_2_NEW,
                         marker=P2_2_MARKER,
                         no_backup=no_backup)


# ============================================================
# P2-4: PythonHighlighter 正则合并
# ============================================================
P2_4_MARKER = "P2-4: 关键字/内置函数合并为单条正则"

P2_4_OLD = '''        # 关键字
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(COLOR_KEYWORD)
        keyword_format.setFontWeight(QFont.Bold)
        for kw in PYTHON_KEYWORDS:
            self._rules.append((f"\\\\b{kw}\\\\b", keyword_format))

        # 内置函数
        builtin_format = QTextCharFormat()
        builtin_format.setForeground(QColor("#dcdcaa"))
        for bi in PYTHON_BUILTINS:
            self._rules.append((f"\\\\b{bi}\\\\b", builtin_format))'''

P2_4_NEW = '''        # 关键字（P2-4: 关键字/内置函数合并为单条正则）
        # 原实现每条关键字都生成一条正则，约 80 条规则，
        # 每行文本跑 80 次 finditer。合并后 2 条即可。
        # 按长度降序排列，长词优先尝试（避免 int 抢 isinstance）。
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(COLOR_KEYWORD)
        keyword_format.setFontWeight(QFont.Bold)
        _kw_alt = '|'.join(
            sorted(PYTHON_KEYWORDS, key=len, reverse=True)
        )
        self._rules.append((r'\\b(?:' + _kw_alt + r')\\b',
                            keyword_format))

        # 内置函数（同样合并）
        builtin_format = QTextCharFormat()
        builtin_format.setForeground(QColor("#dcdcaa"))
        _bi_alt = '|'.join(
            sorted(PYTHON_BUILTINS, key=len, reverse=True)
        )
        self._rules.append((r'\\b(?:' + _bi_alt + r')\\b',
                            builtin_format))'''


def fix_p2_4(no_backup: bool) -> str:
    path = ROOT / "ui" / "python_console.py"
    return apply_replace(path, P2_4_OLD, P2_4_NEW,
                         marker=P2_4_MARKER,
                         no_backup=no_backup)


# ============================================================
# P2-5: DirectoryTree Git 缓存 TTL
# ============================================================
P2_5_MARKER = "P2-5: 默认 5 → 30 秒"

P2_5_OLD = '''        # Git 状态缓存（P1-1 性能优化）
        self._git_root: Optional[str] = None
        self._git_status_cache: Dict[str, str] = {}
        self._git_cache_time: float = 0.0
        self._git_cache_ttl: float = 5.0'''

P2_5_NEW = '''        # Git 状态缓存（P1-1 性能优化）
        self._git_root: Optional[str] = None
        self._git_status_cache: Dict[str, str] = {}
        self._git_cache_time: float = 0.0
        # P2-5: 默认 5 → 30 秒
        # 用户可通过 QSettings 覆盖:
        #   QSettings("QingCao", "Editor").setValue(
        #       "git_status_cache_ttl", 60.0)
        try:
            from PyQt5.QtCore import QSettings
            _s = QSettings("QingCao", "Editor")
            self._git_cache_ttl = _s.value(
                "git_status_cache_ttl", 30.0, type=float
            )
            if self._git_cache_ttl < 1.0:
                self._git_cache_ttl = 30.0
        except Exception:
            self._git_cache_ttl = 30.0'''


def fix_p2_5(no_backup: bool) -> str:
    path = ROOT / "ui" / "directory_tree.py"
    return apply_replace(path, P2_5_OLD, P2_5_NEW,
                         marker=P2_5_MARKER,
                         no_backup=no_backup)


# ============================================================
# P3-1: PluginAPI 死信号
# ============================================================
P3_1_MARKER = "# 说明（P3-1）"

P3_1_OLD = '''    # 信号
    plugin_loaded = pyqtSignal(str)
    plugin_unloaded = pyqtSignal(str)

    def __init__(self, main_window, permissions: Optional[List[str]] = None,
                 plugin_name: str = "unknown"):'''

P3_1_NEW = '''    # 说明（P3-1）:
    #   原有两个信号 plugin_loaded / plugin_unloaded 从未在
    #   PluginAPI 内部 emit，属于死代码。PluginLoader /
    #   PluginManager 有各自的 plugin_loaded 信号负责通知，
    #   PluginAPI 层不需要重复。
    #
    #   如果第三方插件引用了 api.plugin_loaded，请在插件里
    #   改用 from app.event_bus import bus 或直接监听
    #   PluginLoader 的信号。

    def __init__(self, main_window, permissions: Optional[List[str]] = None,
                 plugin_name: str = "unknown"):'''


def _check_plugin_api_signal_safe() -> bool:
    """
    检查 plugins/ 下是否有对 api.plugin_loaded 的引用。

    返回:
        True  安全，可删除
        False 有引用，跳过
    """
    plugins_dir = ROOT / "plugins"
    if not plugins_dir.is_dir():
        return True

    for py in plugins_dir.rglob("*.py"):
        try:
            content = py.read_text(encoding='utf-8')
        except Exception:
            continue
        if ('api.plugin_loaded' in content or
                'api.plugin_unloaded' in content):
            print_warn(
                f"{py.relative_to(ROOT)} 引用了 api.plugin_loaded"
            )
            return False
    return True


def fix_p3_1(no_backup: bool) -> str:
    # 先扫引用
    if not _check_plugin_api_signal_safe():
        print_skip("有插件引用了这两个信号，跳过删除")
        return 'skipped'

    path = ROOT / "app" / "plugins.py"
    return apply_replace(path, P3_1_OLD, P3_1_NEW,
                         marker=P3_1_MARKER,
                         no_backup=no_backup)


# ============================================================
# 主流程
# ============================================================
FIXES = [
    ("P1-4", "editor_view.py 引号自动闭合", fix_p1_4),
    ("P2-2", "main_window.py 每日技巧日期", fix_p2_2),
    ("P2-4", "python_console.py 正则合并", fix_p2_4),
    ("P2-5", "directory_tree.py Git 缓存 TTL", fix_p2_5),
    ("P3-1", "plugins.py 删除死信号", fix_p3_1),
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="P1/P2/P3 快速修复批次"
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--only', type=str, default='',
                        help='只处理指定项：P1-4,P2-2,...')
    args = parser.parse_args()

    print_header("P1/P2/P3 快速修复批次")
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
    print("验证:")
    print("  python tests/run_all.py")
    print("  python main.py")
    print()
    print("清理备份:")
    print("  Windows:     del /s *.bak.batch")
    print("  Linux/macOS: find . -name '*.bak.batch' -delete")

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