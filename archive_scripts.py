#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""归档所有 fix/apply 脚本到 _archive/fixes/"""
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / "_archive" / "fixes"

# 这些不归档
# D2 修复：与 fix_batch_final.py 保持一致，归档 fix_remaining.py
EXCLUDE = {
    "close_review.py",
    "close_review_v2.py",
    "archive_scripts.py",
}

# 归档模式
PATTERNS = [
    "fix_*.py",
    "apply_all_patches*.py",
]


def main():
    ARCHIVE.mkdir(parents=True, exist_ok=True)

    moved = 0
    skipped = 0
    for pattern in PATTERNS:
        for src in sorted(ROOT.glob(pattern)):
            if src.name in EXCLUDE or src.name == Path(__file__).name:
                continue
            if src.is_dir():
                continue

            dst = ARCHIVE / src.name
            if dst.exists():
                print(f"  [SKIP] {src.name} 已在归档目录")
                skipped += 1
                continue

            try:
                shutil.move(str(src), str(dst))
                print(f"  [OK]   {src.name}")
                moved += 1
            except Exception as e:
                print(f"  [FAIL] {src.name}: {e}")

    # 归档 README
    readme = ARCHIVE / "README.md"
    if not readme.exists():
        lines = [
            "# 一次性修复脚本归档",
            "",
            "本目录存放 2026-09 各轮 P0/P1/P2 修复脚本。",
            "所有修复已合并到主线代码，日常不需要执行。",
            "保留仅供追溯。",
            "",
            "## 批次",
            "",
            "| 批次 | 脚本 | 覆盖范围 |",
            "|------|------|----------|",
            "| P0 工具链 | `fix_p0.py` | requirements / session.json / README / marker |",
            "| P0 代码 | `fix_p0_code.py` | task_panel / panels / file_ops / main_window / tests |",
            "| P1 核心 | `fix_p1_core.py` | sandbox socket / Pipe 竞争 / updater / mmap |",
            "| P1 UI | `fix_p1_b.py` | explorer / outline / editor / terminal / welcome / statusbar / theme_market |",
            "| P2 数据源 | `fix_p2_data.py` | tips / usage_stats / theme_market / 每日技巧 / 全局替换 / outline 大文件 |",
            "| 剩余 | `fix_remaining.py` | A3 重做 / C8 重做 / gitignore |",
            "| 历史 | `fix_sandbox_runtime_v2*.py` 等 | 早期中间版本，已被最终版取代 |",
            "",
            "## 重跑",
            "",
            "所有脚本都带 `--dry-run`：",
            "",
            "```",
            "python _archive/fixes/fix_p1_core.py --dry-run",
            "```",
            "",
        ]
        readme.write_text("\n".join(lines), encoding='utf-8')
        print("  [OK]   已生成 _archive/fixes/README.md")

    print()
    print(f"完成：{moved} 个归档，{skipped} 个跳过")


if __name__ == "__main__":
    main()