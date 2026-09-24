#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
B1b: 合并事件系统（v2 修复版）
================================
让 app/event_bus.py 从 core/events.py 重导出所有事件类，
删除 event_bus.py 里重复的 44 个事件类 + EventType 枚举。

修复历史（v2）:
    原版的 END_PATTERN 用 `r'^class EventHistory\\('` 匹配，
    但实际定义是 `class EventHistory:`（不继承基类），
    导致 Step 1 总是失败。

    本版改动：
      1. END_PATTERN 改用 `r'^class EventHistory\\b'` 匹配单词边界
      2. Step 1 失败时直接 return，不再执行 Step 2
      3. 增加失败时的诊断输出（打印文件尾部）
      4. 精简依赖，去掉重复的辅助函数

用法:
    python fix_b1b.py --dry-run
    python fix_b1b.py
"""

import re
import sys
import shutil
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def print_header(t):
    print(f"\n{'=' * 60}\n{t}\n{'=' * 60}")


def print_ok(m):   print(f"  [OK]   {m}")
def print_skip(m): print(f"  [SKIP] {m}")
def print_fail(m): print(f"  [FAIL] {m}")
def print_info(m): print(f"  [INFO] {m}")


# ============================================================
# 文件读写
# ============================================================
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
    bak = Path(str(path) + ".bak.b1b")
    if bak.exists():
        return True
    try:
        shutil.copy2(path, bak)
        return True
    except Exception:
        return False


# ============================================================
# 重导出块
# ============================================================
REEXPORT_BLOCK = '''# ============================================================
# 事件类型与事件类（B1b: 统一从 core.events 重导出）
# ============================================================
# 所有事件定义已迁移到 core/events.py。
# 本模块保留 EventBus 与相关工具（EventHistory / subscribe /
# TemporarySubscription），不再重复定义事件类。
#
# 这样做的原因：
#   1. app/event_bus.py 与 core/events.py 曾各自定义过 44 个
#      同名事件类，字段一致但对象不同，isinstance 可能失败。
#   2. B1a 验证了两处字段完全一致、events 是超集。
#   3. 统一到 core.events 后，任何调用方无论从哪个模块导入，
#      拿到的都是同一对象。
from core.events import (
    # 枚举与工厂
    EventType,
    EventFactory,
    # 基类
    BaseEvent,
    # 文件事件
    FileEvent,
    FileOpenedEvent,
    FileSavedEvent,
    FileClosedEvent,
    FileModifiedEvent,
    FileReloadedEvent,
    FileEncodingChangedEvent,
    # 编辑器事件
    EditorEvent,
    EditorChangedEvent,
    EditorFocusedEvent,
    EditorCreatedEvent,
    EditorDestroyedEvent,
    # 光标与选区
    CursorEvent,
    SelectionEvent,
    # 文本编辑
    TextEditEvent,
    TextInsertedEvent,
    TextDeletedEvent,
    TextReplacedEvent,
    # 撤销重做
    UndoEvent,
    RedoEvent,
    # 搜索
    SearchEvent,
    SearchStartedEvent,
    SearchFinishedEvent,
    SearchResultEvent,
    # 标签
    TabEvent,
    TabChangedEvent,
    TabAddedEvent,
    TabRemovedEvent,
    # 项目
    ProjectEvent,
    ProjectOpenedEvent,
    ProjectClosedEvent,
    ProjectFileEvent,
    ProjectFileAddedEvent,
    ProjectFileRemovedEvent,
    ProjectFileRenamedEvent,
    # 宏
    MacroEvent,
    MacroStartedEvent,
    MacroStoppedEvent,
    MacroReplayedEvent,
    # 插件
    PluginEvent,
    PluginLoadedEvent,
    PluginUnloadedEvent,
    PluginErrorEvent,
    # 主题
    ThemeEvent,
    # 应用
    AppEvent,
    AppReadyEvent,
    AppClosingEvent,
    # 状态与通知
    StatusMessageEvent,
    NotificationEvent,
)


'''


# ============================================================
# 定位
# ============================================================
# 起点：事件类型枚举注释块
START_PATTERN = re.compile(
    r'# =+\n# 事件类型枚举\n# =+\n'
)

# 终点：EventHistory 类定义
# 关键修复：用 \b 匹配单词边界，兼容 "class EventHistory:" 和
# "class EventHistory(...)" 两种写法
END_PATTERN = re.compile(r'^class EventHistory\b', re.MULTILINE)


def find_block_bounds(content: str):
    """找到待替换块 [start_idx, end_idx)"""
    start_m = START_PATTERN.search(content)
    if not start_m:
        return None, None, "未找到起点（'# 事件类型枚举' 注释块）"

    start_idx = start_m.start()

    end_m = END_PATTERN.search(content, start_idx)
    if not end_m:
        return None, None, "未找到终点（'class EventHistory'）"

    end_idx = end_m.start()

    return start_idx, end_idx, None


# ============================================================
# 主逻辑
# ============================================================
def fix(no_backup: bool, dry_run: bool) -> str:
    path = ROOT / "app" / "event_bus.py"
    if not path.exists():
        print_fail("app/event_bus.py 不存在")
        return 'failed'

    content = read_text(path)

    # 幂等：已应用过
    if "B1b: 统一从 core.events 重导出" in content:
        print_skip("B1b 已应用")
        return 'skipped'

    start, end, err = find_block_bounds(content)
    if err:
        print_fail(err)

        # 诊断信息
        print_info("文件前 30 行：")
        for i, line in enumerate(content.split('\n')[:30], 1):
            print(f"      {i:4d} | {line}")

        print_info("搜索 'class EventHistory'：")
        m = re.search(r'class EventHistory', content)
        if m:
            line_no = content[:m.start()].count('\n') + 1
            print(f"      在第 {line_no} 行找到")
        else:
            print("      未找到")

        return 'failed'

    deleted_block = content[start:end]
    deleted_lines = deleted_block.count('\n') + 1

    print_info(f"将替换第 {content[:start].count(chr(10)) + 1} "
               f"~ {content[:end].count(chr(10)) + 1} 行 "
               f"（共 {deleted_lines} 行）")
    print_info("被删除内容前 6 行：")
    for line in deleted_block.split('\n')[:6]:
        print(f"      | {line}")
    print_info("...")

    new_content = content[:start] + REEXPORT_BLOCK + content[end:]

    # 语法验证
    try:
        compile(new_content, str(path), 'exec')
    except SyntaxError as e:
        print_fail(f"生成后语法错误: line {e.lineno}: {e.msg}")
        lines = new_content.split('\n')
        start_line = max(0, e.lineno - 3)
        end_line = min(len(lines), e.lineno + 2)
        for i in range(start_line, end_line):
            mark = ">>>" if i == e.lineno - 1 else "   "
            print(f"      {mark} {i+1:4d} | {lines[i]}")
        return 'failed'

    if dry_run:
        print_info("[DRY-RUN] 内容已生成，不写回")
        return 'applied'

    if not no_backup and not backup(path):
        print_fail("备份失败")
        return 'failed'

    if not write_text(path, new_content):
        return 'failed'

    print_ok(
        f"app/event_bus.py 已替换"
        f"（删 {deleted_lines} 行，插 {REEXPORT_BLOCK.count(chr(10))} 行）"
    )
    return 'applied'


# ============================================================
# 测试文件
# ============================================================
TEST_IDENTITY = '''# -*- coding: utf-8 -*-
"""事件类身份测试（B1b）

B1b 合并后，从 app.event_bus 与 core.events 导入的同名事件类
应是同一个对象（is 断言），而非两份定义。
"""
import pytest


EVENT_NAMES = [
    'BaseEvent',
    'FileEvent', 'FileOpenedEvent', 'FileSavedEvent',
    'FileClosedEvent', 'FileModifiedEvent', 'FileReloadedEvent',
    'FileEncodingChangedEvent',
    'EditorEvent', 'EditorChangedEvent', 'EditorFocusedEvent',
    'EditorCreatedEvent', 'EditorDestroyedEvent',
    'CursorEvent', 'SelectionEvent',
    'TextEditEvent',
    'UndoEvent', 'RedoEvent',
    'SearchEvent', 'SearchStartedEvent', 'SearchFinishedEvent',
    'SearchResultEvent',
    'TabEvent', 'TabChangedEvent', 'TabAddedEvent', 'TabRemovedEvent',
    'ProjectEvent', 'ProjectOpenedEvent', 'ProjectClosedEvent',
    'ProjectFileEvent',
    'MacroEvent', 'MacroStartedEvent', 'MacroStoppedEvent',
    'MacroReplayedEvent',
    'PluginEvent', 'PluginLoadedEvent', 'PluginUnloadedEvent',
    'PluginErrorEvent',
    'ThemeEvent',
    'AppEvent', 'AppReadyEvent', 'AppClosingEvent',
    'StatusMessageEvent', 'NotificationEvent',
]


class TestEventIdentity:

    def test_event_classes_are_same_object(self):
        import app.event_bus as bus_mod
        import core.events as evt_mod

        mismatched = []
        for name in EVENT_NAMES:
            a = getattr(bus_mod, name, None)
            b = getattr(evt_mod, name, None)
            if a is None:
                mismatched.append(f"{name}: 不在 app.event_bus")
                continue
            if b is None:
                mismatched.append(f"{name}: 不在 core.events")
                continue
            if a is not b:
                mismatched.append(f"{name}: 不是同一对象")

        assert not mismatched, (
            "B1b 合并失败:\\n  " + "\\n  ".join(mismatched)
        )

    def test_event_type_enum_is_same(self):
        from app.event_bus import EventType as A
        from core.events import EventType as B
        assert A is B

    def test_base_event_is_same(self):
        from app.event_bus import BaseEvent as A
        from core.events import BaseEvent as B
        assert A is B

    def test_isinstance_across_modules(self):
        from app.event_bus import FileOpenedEvent as BusEvt
        from core.events import FileOpenedEvent as CoreEvt

        obj = BusEvt(path="/tmp/x.txt")
        assert isinstance(obj, CoreEvt)
        assert isinstance(obj, BusEvt)
'''


def add_identity_test() -> str:
    path = ROOT / "tests" / "test_event_identity.py"
    if path.exists():
        print_skip("tests/test_event_identity.py 已存在")
        return 'skipped'
    if not write_text(path, TEST_IDENTITY):
        return 'failed'
    print_ok("tests/test_event_identity.py 已创建")
    return 'applied'


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true')
    args = parser.parse_args()

    print_header("B1b: 合并事件系统（v2）")
    print(f"  项目目录: {ROOT}")
    print(f"  模式:     {'DRY-RUN' if args.dry_run else '实际应用'}")

    print_header("Step 1: 重导出事件类")
    r1 = fix(args.no_backup, args.dry_run)

    if args.dry_run:
        print()
        print_info("[DRY-RUN] 完成，未修改任何文件")
        return 0

    # 关键修复：Step 1 失败则中止，不创建注定失败的测试
    if r1 == 'failed':
        print()
        print_fail("Step 1 失败，跳过 Step 2")
        return 1

    print_header("Step 2: 加身份等价测试")
    r2 = add_identity_test()

    print()
    print("=" * 60)
    print("汇总")
    print("=" * 60)
    print(f"  [{r1}] 重导出事件类")
    print(f"  [{r2}] 加测试")

    if 'failed' in (r1, r2):
        print()
        print_fail("有失败项")
        return 1

    print()
    print_ok("B1b 完成")
    print()
    print("下一步：")
    print("  python tests/run_all.py")
    print("  python main.py")
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