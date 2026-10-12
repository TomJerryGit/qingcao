#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成内置音效文件到 resources/sounds/（P2）

背景
----
`infrastructure/sound_manager.py` 的 `_load_event_sound` 优先从
`resources/sounds/<file>.wav` 加载，加载不到才回退到
`BuiltinSounds` 程序化合成：

    if os.path.exists(filepath):
        effect = SoundEffect(filepath, self)   # 优先文件
        ...
    data = BuiltinSounds.get(event)            # 回退合成

因此功能本身**可用**（走合成回退），但 `resources/sounds/` 目录长期
不存在 —— 既让文档/README 的"音效目录"显得缺失，也让用户无处放置
自定义音效。

本脚本把 `BuiltinSounds` 生成的数据**物化成真实 .wav 文件**，从而：

  * 目录与文档一致；
  * 音效可被用户直接替换/试听，无需改代码；
  * 播放路径从"每次合成"变为"直接读文件"（略省 CPU）。

生成的音效内容与原来的合成回退**完全一致**（同一函数产出），
所以听感不会变化。

用法::

    python tools/make_sounds.py            # 生成缺失的文件
    python tools/make_sounds.py --force    # 覆盖已有文件
    python tools/make_sounds.py --list     # 只列出将生成的文件
"""
import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    argv = argv if argv is not None else sys.argv[1:]
    force = '--force' in argv
    list_only = '--list' in argv

    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError:
        print('[make_sounds] 需要 PyQt5')
        return 1

    app = QApplication.instance() or QApplication([])

    from infrastructure.sound_manager import (
        BuiltinSounds, DEFAULT_SOUND_DIR, EVENT_FILE_MAP, SoundEvent,
    )

    sound_dir = os.path.join(ROOT, DEFAULT_SOUND_DIR)
    os.makedirs(sound_dir, exist_ok=True)

    created = skipped = failed = 0
    total_bytes = 0

    for event in SoundEvent:
        filename = EVENT_FILE_MAP.get(event, '%s.wav' % event.value)
        path = os.path.join(sound_dir, filename)

        if os.path.exists(path) and not force:
            skipped += 1
            continue

        try:
            data = BuiltinSounds.get(event)
        except Exception as e:
            print('  [FAIL] %-16s 合成失败: %s' % (event.value, e))
            failed += 1
            continue

        if not data:
            failed += 1
            continue

        if list_only:
            print('  将生成 %-18s %6d 字节' % (filename, len(data)))
            created += 1
            continue

        try:
            with open(path, 'wb') as f:
                f.write(data)
            created += 1
            total_bytes += len(data)
        except OSError as e:
            print('  [FAIL] %s: %s' % (filename, e))
            failed += 1

    if list_only:
        print('[make_sounds] 待生成 %d 个（--list 模式，未写盘）' % created)
        return 0

    print('[make_sounds] 目录: %s' % sound_dir)
    print('[make_sounds] 新生成 %d 个, 已存在跳过 %d 个, 失败 %d 个, 共 %.1f KB'
          % (created, skipped, failed, total_bytes / 1024.0))

    # 校验：SoundManager 现在应能从文件加载
    try:
        from infrastructure.sound_manager import SoundManager
        mgr = SoundManager(sound_dir=sound_dir)
        loaded = len(getattr(mgr, '_event_sounds', {}) or {})
        print('[make_sounds] SoundManager 载入事件音效: %d 个' % loaded)
    except Exception as e:
        print('[make_sounds] SoundManager 校验跳过: %s' % e)

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
