# CI flaky 面包屑与发布门禁（v2.23 D5）

## 目标
原生 Qt 崩溃（0xC0000005）难以复现时，快速判断卡在哪个阶段、哪个文件，并限制 fallback 频率。

## 面包屑
`tools/run_tests_sharded.py` 在关键阶段写入 `data/test_shards/last_stage.json`（原子替换）：
- `start`：分片数/文件数/并行；
- `shard`：part、attempt、文件数、文件名；
- `localize`：正在逐文件复跑的文件；
- `flaky_pass`：崩溃码 + 逐文件复跑全部通过（门禁放行）；
- `failed`：失败片与崩溃码；
- `done`：全部通过。

崩溃后查看：
```powershell
Get-Content data\test_shards\last_stage.json
python tools/ci_flaky_report.py
```
`crashed_<test>.log` 保存逐文件定位时的崩溃输出。

## flaky 历史
门禁放行时追加 `data/ci_flaky_history.jsonl`：
```json
{"ts":..., "stage":"flaky_fallback", "crash_codes":[3221225477],
 "files":40, "shard_sizes":[49,49],"localized":[], "result":"pass_after_localize"}
```

## 发布门禁
```powershell
python tools/ci_flaky_report.py --check --max-7d 3
```
- 最近 7 天 ≤3 次：保持并行；
- >3 次：退出码 1，建议 `--shards 2 --no-parallel` 并优先修复可疑文件。

CI 在“Full test suite”后以 `if: always()` 执行该检查，失败时仍生成报告。

## 局限
- 面包屑是“最后写入者”语义，并行时只保留最近一片的状态；
- 原生崩溃可能发生在任意线程，面包屑只能缩小范围，不能替代 dump/日志。
