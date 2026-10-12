#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""诊断 app/event_bus.py 与 core/events.py 的事件类差异"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def collect_event_classes(path: Path, module_qualname: str):
    """
    用 AST 提取一个文件里所有 dataclass 类（及字段列表）。
    """
    result = {}
    try:
        src = path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"[!] 读 {path} 失败: {e}")
        return result

    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        print(f"[!] {path} 语法错误: {e}")
        return result

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        # 只关心继承自 BaseEvent 或名字以 Event 结尾的类
        base_names = []
        for b in node.bases:
            if isinstance(b, ast.Name):
                base_names.append(b.id)
            elif isinstance(b, ast.Attribute):
                base_names.append(b.attr)

        is_event = (
            'BaseEvent' in base_names
            or node.name == 'BaseEvent'
            or (node.name.endswith('Event') and not node.name.endswith('EventBus'))
        )
        if not is_event:
            continue

        fields = []
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                fields.append(item.target.id)
            elif isinstance(item, ast.Assign):
                for t in item.targets:
                    if isinstance(t, ast.Name):
                        fields.append(t.id)
        result[node.name] = {
            'qualname': f"{module_qualname}.{node.name}",
            'bases': base_names,
            'fields': fields,
            'lineno': node.lineno,
        }
    return result


def main():
    print("=" * 70)
    print("事件类差异诊断")
    print("=" * 70)

    bus_file = ROOT / "app" / "event_bus.py"
    evt_file = ROOT / "core" / "events.py"

    bus_cls = collect_event_classes(bus_file, "app.event_bus")
    evt_cls = collect_event_classes(evt_file, "core.events")

    print(f"\n【app/event_bus.py】{len(bus_cls)} 个事件类")
    for name, info in sorted(bus_cls.items()):
        print(f"  - {name:30s} 行 {info['lineno']:4d}  "
              f"字段={info['fields']}")

    print(f"\n【core/events.py】{len(evt_cls)} 个事件类")
    for name, info in sorted(evt_cls.items()):
        print(f"  - {name:30s} 行 {info['lineno']:4d}  "
              f"字段={info['fields']}")

    # 交集与差异
    bus_names = set(bus_cls.keys())
    evt_names = set(evt_cls.keys())

    both = sorted(bus_names & evt_names)
    only_bus = sorted(bus_names - evt_names)
    only_evt = sorted(evt_names - bus_names)

    print("\n" + "=" * 70)
    print("差异分析")
    print("=" * 70)

    print(f"\n【两处都有】（{len(both)} 个）— 需要检查字段是否一致：")
    for name in both:
        bf = set(bus_cls[name]['fields'])
        ef = set(evt_cls[name]['fields'])
        same = bf == ef
        mark = "✓" if same else "✗"
        print(f"  {mark} {name}")
        if not same:
            print(f"      event_bus 独有: {sorted(bf - ef)}")
            print(f"      events   独有: {sorted(ef - bf)}")

    print(f"\n【只在 app/event_bus.py】（{len(only_bus)} 个）：")
    for name in only_bus:
        print(f"  - {name}  字段={bus_cls[name]['fields']}")

    print(f"\n【只在 core/events.py】（{len(only_evt)} 个）：")
    for name in only_evt:
        print(f"  - {name}  字段={evt_cls[name]['fields']}")

    # 结论
    print("\n" + "=" * 70)
    print("结论")
    print("=" * 70)

    if not only_bus and not only_evt:
        print("两处事件类完全覆盖，可以安全合并。")
    elif not only_bus:
        print(f"app/event_bus.py 的事件类全部在 events.py 里也有。")
        print(f"events.py 多出 {len(only_evt)} 个（新事件）。")
        print("→ 直接让 event_bus 从 events 重导出即可。")
    elif not only_evt:
        print(f"events.py 的事件类全部在 event_bus.py 里也有。")
        print(f"event_bus.py 多出 {len(only_bus)} 个。")
        print("→ 需要把多出的事件也搬到 events.py。")
    else:
        print("两处事件类有交叉但不完全覆盖。")
        print("→ 需要合并：以 events.py 为基础，把 event_bus.py 独有的事件类也搬过去。")

    # 不一致的字段
    inconsistent = [
        name for name in both
        if set(bus_cls[name]['fields']) != set(evt_cls[name]['fields'])
    ]
    if inconsistent:
        print(f"\n⚠ 字段不一致的类（{len(inconsistent)} 个）：")
        for name in inconsistent:
            print(f"  - {name}")


if __name__ == "__main__":
    main()