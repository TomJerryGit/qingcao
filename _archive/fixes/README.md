# 一次性修复脚本归档

本目录存放 2026-09 各轮 P0/P1/P2 修复脚本。
所有修复已合并到主线代码，日常不需要执行。
保留仅供追溯。

## 批次

| 批次 | 脚本 | 覆盖范围 |
|------|------|----------|
| P0 工具链 | `fix_p0.py` | requirements / session.json / README / marker |
| P0 代码 | `fix_p0_code.py` | task_panel / panels / file_ops / main_window / tests |
| P1 核心 | `fix_p1_core.py` | sandbox socket / Pipe 竞争 / updater / mmap |
| P1 UI | `fix_p1_b.py` | explorer / outline / editor / terminal / welcome / statusbar / theme_market |
| P2 数据源 | `fix_p2_data.py` | tips / usage_stats / theme_market / 每日技巧 / 全局替换 / outline 大文件 |
| 剩余 | `fix_remaining.py` | A3 重做 / C8 重做 / gitignore |
| 历史 | `fix_sandbox_runtime_v2*.py` 等 | 早期中间版本，已被最终版取代 |

## 重跑

所有脚本都带 `--dry-run`：

```
python _archive/fixes/fix_p1_core.py --dry-run
```
