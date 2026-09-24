#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P0 搜索与事件修复（v1）
============================
修复 3 项 P0 问题：

  P0-1  EditorProxy.highlight_all 调用不存在的 search_all()
        "高亮全部" 完全没反应（AttributeError 被 except 吞掉）

  P0-2  EditorProxy.search_next 调用签名错误
        SearchEngine.search() 无参数、返回 SearchResult，
        但代码写成 engine.search(pattern, pos, forward)，
        异常被 except 吞掉，"查找下一个"无反应

  P0-3  _route_event 中 ProjectFileEvent 分派错误
        ProjectFileRemovedEvent / ProjectFileRenamedEvent 都
        继承自 ProjectFileEvent，isinstance 全命中第一个分支，
        所有项目文件事件都被当成"新增"发出

特性:
  - 幂等
  - 每项独立处理，一项失败不影响其他
  - 修改前备份 *.bak.p0search
  - Python 文件修改后 compile() 验证

用法:
    python fix_p0_search.py --dry-run
    python fix_p0_search.py
    python fix_p0_search.py --only P0-1,P0-2
    python fix_p0_search.py --no-backup
"""

import sys
import shutil
import argparse
from pathlib import Path
from typing import Tuple

ROOT = Path(__file__).resolve().parent
BACKUP_SUFFIX = ".bak.p0search"


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
# P0-A: core/editor.py 顶部补 SearchOptions import
# ============================================================
IMPORT_MARKER = "from core.search import SearchEngine, SearchOptions"
IMPORT_OLD = "from core.search import SearchEngine\n"
IMPORT_NEW = "from core.search import SearchEngine, SearchOptions\n"


def fix_import(no_backup: bool) -> str:
    path = ROOT / "core" / "editor.py"
    return apply_replace(path, IMPORT_OLD, IMPORT_NEW,
                         marker=IMPORT_MARKER,
                         no_backup=no_backup)


# ============================================================
# P0-1: highlight_all
# ============================================================
P0_1_MARKER = "# P0-1 修复：SearchEngine 无 search_all 方法"

P0_1_OLD = (
    "            engine = SearchEngine(self.document.provider)\n"
    "            matches = engine.search_all(pattern)\n"
)

P0_1_NEW = (
    "            # P0-1 修复：SearchEngine 无 search_all 方法，\n"
    "            # 改用 search() 返回 SearchResult。\n"
    "            options = SearchOptions(pattern=pattern, is_regex=True)\n"
    "            engine = SearchEngine(self.document.provider, options)\n"
    "            result = engine.search()\n"
    "\n"
    "            if result.error or result.is_empty:\n"
    "                return 0\n"
    "\n"
    "            matches = [(m.start, m.end) for m in result.matches]\n"
)


def fix_p0_1(no_backup: bool) -> str:
    path = ROOT / "core" / "editor.py"
    return apply_replace(path, P0_1_OLD, P0_1_NEW,
                         marker=P0_1_MARKER,
                         no_backup=no_backup)


# ============================================================
# P0-2: search_next
# ============================================================
P0_2_MARKER = "# P0-2 修复：SearchEngine.search() 不接受参数"

P0_2_OLD = '''    def search_next(self, pattern: str, forward: bool = True) -> bool:
        """搜索下一个匹配"""
        try:
            engine = SearchEngine(self.document.provider)
            pos = self.get_current_pos()
            match = engine.search(pattern, pos, forward)

            if match:
                self.set_selection(match[0], match[1])
                return True
            return False

        except Exception as e:
            print(f"[EditorProxy] 搜索失败: {e}")
            return False
'''

P0_2_NEW = '''    def search_next(self, pattern: str, forward: bool = True) -> bool:
        """搜索下一个匹配"""
        try:
            # P0-2 修复：SearchEngine.search() 不接受参数，
            # 且返回 SearchResult 而非 (start, end) tuple。
            options = SearchOptions(pattern=pattern)
            engine = SearchEngine(self.document.provider, options)
            result = engine.search()

            if result.error or result.is_empty:
                return False

            pos = self.get_current_pos()
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

            self.set_selection(match.start, match.end)
            return True

        except Exception as e:
            print(f"[EditorProxy] 搜索失败: {e}")
            return False
'''


def fix_p0_2(no_backup: bool) -> str:
    path = ROOT / "core" / "editor.py"
    return apply_replace(path, P0_2_OLD, P0_2_NEW,
                         marker=P0_2_MARKER,
                         no_backup=no_backup)


# ============================================================
# P0-3: _route_event ProjectFileEvent 分派
# ============================================================
P0_3_MARKER = "# P0-3 修复：先检查子类"

P0_3_OLD = '''        # 项目
        elif isinstance(event, ProjectOpenedEvent):
            self.project_opened.emit(event)
        elif isinstance(event, ProjectClosedEvent):
            self.project_closed.emit(event)
        elif isinstance(event, ProjectFileEvent):
            self.project_file_added.emit(event)
'''

P0_3_NEW = '''        # 项目
        elif isinstance(event, ProjectOpenedEvent):
            self.project_opened.emit(event)
        elif isinstance(event, ProjectClosedEvent):
            self.project_closed.emit(event)
        # P0-3 修复：先检查子类，避免 ProjectFileEvent 基类
        # 把所有子类都当成 ProjectFileAddedEvent 发出。
        elif isinstance(event, ProjectFileAddedEvent):
            self.project_file_added.emit(event)
        elif isinstance(event, ProjectFileRemovedEvent):
            self.project_file_removed.emit(event)
        elif isinstance(event, ProjectFileRenamedEvent):
            self.project_file_renamed.emit(event)
'''


SIGNAL_MARKER = "project_file_renamed = pyqtSignal(ProjectFileEvent)"

SIGNAL_OLD = (
    "    project_file_added = pyqtSignal(ProjectFileEvent)\n"
    "    project_file_removed = pyqtSignal(ProjectFileEvent)\n"
)

SIGNAL_NEW = (
    "    project_file_added = pyqtSignal(ProjectFileEvent)\n"
    "    project_file_removed = pyqtSignal(ProjectFileEvent)\n"
    "    # P0-3 修复：新增 renamed signal\n"
    "    project_file_renamed = pyqtSignal(ProjectFileEvent)\n"
)


def fix_p0_3(no_backup: bool) -> str:
    """P0-3 涉及 2 个文件 * 2 处修改"""
    results = []
    for rel in ("app/event_bus.py", "core/events.py"):
        path = ROOT / rel
        results.append(
            apply_replace(path, SIGNAL_OLD, SIGNAL_NEW,
                          marker=SIGNAL_MARKER,
                          no_backup=no_backup)
        )
        results.append(
            apply_replace(path, P0_3_OLD, P0_3_NEW,
                          marker=P0_3_MARKER,
                          no_backup=no_backup)
        )

    if 'failed' in results:
        return 'failed'
    if 'applied' in results:
        return 'applied'
    return 'skipped'


# ============================================================
# 主流程
# ============================================================
FIXES = [
    ("P0-A", "core/editor.py 顶部 import 补 SearchOptions",
     fix_import),
    ("P0-1", "core/editor.py highlight_all",
     fix_p0_1),
    ("P0-2", "core/editor.py search_next",
     fix_p0_2),
    ("P0-3", "app/event_bus.py + core/events.py 事件分派",
     fix_p0_3),
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="P0 搜索与事件修复"
    )
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--only', type=str, default='',
                        help='只处理指定项：P0-1,P0-2,...')
    args = parser.parse_args()

    print_header("P0 搜索与事件修复")
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
          "for f in ['core/editor.py', 'app/event_bus.py', "
          "'core/events.py']]; print('OK')\"")
    print("  2. 跑测试: python tests/run_all.py")
    print("  3. 启动编辑器: python main.py")
    print("  4. 打开任意文件，Ctrl+F 输入关键词:")
    print("     - 点击'全部高亮' 应看到黄色标记")
    print("     - 点击'下一个' 应跳转到下一处匹配")
    print()
    print("清理备份:")
    print("  Windows:     del /s *.bak.p0search")
    print("  Linux/macOS: find . -name '*.bak.p0search' -delete")

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