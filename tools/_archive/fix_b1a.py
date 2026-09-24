#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
青草编辑器 - B1a: 补齐 events.py 缺失字段 + 运行时诊断
=========================================================
Step 1: 补 SearchStartedEvent.scope
        （event_bus 独有，events 缺）

Step 2: 运行时逐类对比 event_bus 与 events 的字段
        比 AST 更准确（含继承字段、ClassVar 判断）

用法：
    python fix_b1a.py --dry-run
    python fix_b1a.py
"""

import os
import sys
import shutil
import argparse
import importlib
import dataclasses
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def print_header(t): print(f"\n{'=' * 60}\n{t}\n{'=' * 60}")
def print_ok(m):   print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")
def print_warn(m): print(f"  [WARN] {m}")


def read_text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except Exception:
        return ""
    if raw.startswith(b'\xef\xbb\xbf'):
        text = raw.decode('utf-8-sig', errors='replace')
    else:
        text = raw.decode('utf-8', errors='replace')
    return text.replace('\r\n', '\n').replace('\r', '\n')


def write_text(path: Path, content: str) -> bool:
    try:
        path.write_text(content, encoding='utf-8', newline='\n')
        return True
    except Exception as e:
        print_fail(f"写回失败 {path.name}: {e}")
        return False


def backup(path: Path) -> bool:
    if not path.exists():
        return True
    bak = Path(str(path) + ".bak.b1a")
    if bak.exists():
        return True
    try:
        shutil.copy2(path, bak)
        return True
    except Exception:
        return False


# ============================================================
# Step 1: 补 SearchStartedEvent.scope
# ============================================================
MARKER = "# B1a: scope 字段（event_bus 独有）"

OLD_SEARCH_STARTED = '''@dataclass
class SearchStartedEvent(SearchEvent):
    """搜索开始"""
    event_type: ClassVar[EventType] = EventType.SEARCH_STARTED
    directory: str = ""
    file_filter: str = "*.*"'''

NEW_SEARCH_STARTED = '''@dataclass
class SearchStartedEvent(SearchEvent):
    """搜索开始"""
    event_type: ClassVar[EventType] = EventType.SEARCH_STARTED
    # B1a: scope 字段（event_bus 独有）
    scope: str = "current"
    directory: str = ""
    file_filter: str = "*.*"'''


def fix_scope(no_backup: bool) -> str:
    path = ROOT / "core" / "events.py"
    if not path.exists():
        print_fail("core/events.py 不存在")
        return 'failed'

    content = read_text(path)

    if MARKER in content:
        print_skip("scope 字段已补")
        return 'skipped'

    cnt = content.count(OLD_SEARCH_STARTED)
    if cnt == 0:
        print_fail("SearchStartedEvent 锚点未找到")
        # 打印上下文提示
        idx = content.find("class SearchStartedEvent")
        if idx >= 0:
            print_info("当前定义：")
            snippet = content[idx:idx + 400]
            for line in snippet.split('\n')[:12]:
                print(f"      | {line}")
        return 'failed'
    if cnt > 1:
        print_fail(f"锚点重复 {cnt} 次")
        return 'failed'

    new_content = content.replace(OLD_SEARCH_STARTED, NEW_SEARCH_STARTED, 1)

    try:
        compile(new_content, str(path), 'exec')
    except SyntaxError as e:
        print_fail(f"语法错误: line {e.lineno}: {e.msg}")
        return 'failed'

    if not no_backup:
        backup(path)
    if not write_text(path, new_content):
        return 'failed'
    print_ok("SearchStartedEvent.scope 已补")
    return 'applied'


# ============================================================
# Step 2: 运行时字段对比
# ============================================================
def diagnose():
    """用运行时 dataclasses.fields 对比"""
    print_info("加载模块...")
    try:
        from PyQt5.QtWidgets import QApplication
        if QApplication.instance() is None:
            # 事件模块用 pyqtSignal，需要 QApplication 实例
            _app = QApplication([])
    except Exception:
        pass

    try:
        import core.events as evt_mod
        import app.event_bus as bus_mod
        importlib.reload(evt_mod)
        importlib.reload(bus_mod)
    except Exception as e:
        print_fail(f"导入失败: {e}")
        import traceback
        traceback.print_exc()
        return []

    diffs = []
    matched = 0

    for name in sorted(dir(bus_mod)):
        if name.startswith('_'):
            continue
        bus_cls = getattr(bus_mod, name)
        if not isinstance(bus_cls, type):
            continue
        try:
            if not dataclasses.is_dataclass(bus_cls):
                continue
        except Exception:
            continue

        evt_cls = getattr(evt_mod, name, None)
        if evt_cls is None:
            diffs.append((name, "events 里没有这个类"))
            continue
        if not dataclasses.is_dataclass(evt_cls):
            diffs.append((name, "events 里不是 dataclass"))
            continue

        try:
            bus_fields = {f.name for f in dataclasses.fields(bus_cls)}
            evt_fields = {f.name for f in dataclasses.fields(evt_cls)}
        except Exception as e:
            diffs.append((name, f"取字段失败: {e}"))
            continue

        missing = bus_fields - evt_fields
        if missing:
            diffs.append((name, f"events 缺字段: {sorted(missing)}"))
        else:
            matched += 1

    # events 独有的类（不算错，只是多出的）
    only_in_events = []
    for name in sorted(dir(evt_mod)):
        if name.startswith('_'):
            continue
        evt_cls = getattr(evt_mod, name)
        if not isinstance(evt_cls, type):
            continue
        try:
            if not dataclasses.is_dataclass(evt_cls):
                continue
        except Exception:
            continue
        if not hasattr(bus_mod, name):
            only_in_events.append(name)

    print()
    print("-" * 60)
    print("字段对比结果")
    print("-" * 60)
    print(f"  bus / events 都有的 dataclass: {matched} 个字段完全一致")
    if diffs:
        print(f"  ⚠ 字段不一致: {len(diffs)} 个")
        for name, reason in diffs:
            print(f"      - {name}: {reason}")
    else:
        print(f"  ✓ 无字段不一致")

    if only_in_events:
        print()
        print(f"  events 独有的类（{len(only_in_events)} 个，属于扩展）:")
        for name in only_in_events:
            print(f"      - {name}")

    return diffs


# ============================================================
# Step 3: 加测试
# ============================================================
TEST_CONTENT = '''# -*- coding: utf-8 -*-
"""事件类字段存在性测试（B1a）"""
import dataclasses


def _has_field(cls, name):
    try:
        return name in {f.name for f in dataclasses.fields(cls)}
    except Exception:
        return False


class TestEventFields:

    def test_search_started_has_scope(self):
        from core.events import SearchStartedEvent
        assert _has_field(SearchStartedEvent, 'scope'), \\
            "SearchStartedEvent 缺少 scope 字段（B1a 修复）"

    def test_editor_changed_has_filepath(self):
        from core.events import EditorChangedEvent
        # filepath 从 EditorEvent 继承
        assert _has_field(EditorChangedEvent, 'filepath')

    def test_editor_created_has_filepath(self):
        from core.events import EditorCreatedEvent
        assert _has_field(EditorCreatedEvent, 'filepath')

    def test_file_opened_fields(self):
        from core.events import FileOpenedEvent
        for name in ('path', 'encoding', 'size', 'line_count', 'is_readonly'):
            assert _has_field(FileOpenedEvent, name), \\
                f"FileOpenedEvent 缺少 {name}"

    def test_file_saved_fields(self):
        from core.events import FileSavedEvent
        for name in ('path', 'encoding', 'size', 'backup_path'):
            assert _has_field(FileSavedEvent, name), \\
                f"FileSavedEvent 缺少 {name}"

    def test_cursor_fields(self):
        from core.events import CursorEvent
        for name in ('line', 'col', 'position'):
            assert _has_field(CursorEvent, name), \\
                f"CursorEvent 缺少 {name}"

    def test_tab_changed_fields(self):
        from core.events import TabChangedEvent
        for name in ('index', 'title', 'filepath', 'old_index'):
            assert _has_field(TabChangedEvent, name), \\
                f"TabChangedEvent 缺少 {name}"

    def test_macro_started_has_macro_name(self):
        from core.events import MacroStartedEvent
        assert _has_field(MacroStartedEvent, 'macro_name')

    def test_macro_stopped_has_duration(self):
        from core.events import MacroStoppedEvent
        assert _has_field(MacroStoppedEvent, 'duration_seconds')

    def test_status_message_fields(self):
        from core.events import StatusMessageEvent
        for name in ('message', 'timeout', 'level'):
            assert _has_field(StatusMessageEvent, name), \\
                f"StatusMessageEvent 缺少 {name}"
'''


def add_test(no_backup: bool) -> str:
    path = ROOT / "tests" / "test_events_fields.py"
    if path.exists():
        print_skip("test_events_fields.py 已存在")
        return 'skipped'
    if not write_text(path, TEST_CONTENT):
        return 'failed'
    print_ok("tests/test_events_fields.py 已创建")
    return 'applied'


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("B1a: 补字段 + 运行时诊断")
    print(f"  项目目录: {ROOT}")

    if args.dry_run:
        print_info("[DRY-RUN] 步骤：")
        print_info("  1. 补 SearchStartedEvent.scope")
        print_info("  2. 运行时对比 event_bus / events 的字段")
        print_info("  3. 新增 tests/test_events_fields.py")
        return 0

    print_header("Step 1: 补 SearchStartedEvent.scope")
    r1 = fix_scope(args.no_backup)

    print_header("Step 2: 运行时字段对比")
    diffs = diagnose()

    print_header("Step 3: 新增字段测试")
    r3 = add_test(args.no_backup)

    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    print(f"  {r1} 补 scope")
    print(f"  {r3} 新增测试")

    if diffs:
        print()
        print_warn(f"仍有 {len(diffs)} 处字段差异，请看上方 Step 2 输出")
        print_info("把差异贴给我，下一轮统一补")
    else:
        print()
        print_ok("无字段差异，B1a 完成")

    print()
    print("下一步：")
    print("  python tests/run_all.py")
    print("  git add -A")
    print("  git commit -m 'refactor(B1a): 补 events.py 缺失字段 + 字段测试'")
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