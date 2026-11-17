# Flaky 原生崩溃治理（2026-11-17）

## 现状

- `data/ci_flaky_history.jsonl` 记录分片原生崩溃事件；
- 崩溃码 **3221225477（0xC0000005）**，发生在合并分片；逐文件复跑全部通过；
- 当前策略：分片崩溃 → 逐文件复跑 → 全部通过则门禁放行（避免阻塞发布）。

## 风险

- 掩盖真实回归：若崩溃由某次改动引入，逐文件复跑可能偶然通过；
- 发布延迟：崩溃会触发本地化重跑，增加 CI 时间。

## 治理规则

1. 每次崩溃必须写入 `ci_flaky_history.jsonl`，保留 `crash_codes`/`localized`；
2. 每周运行 `python tools/flaky_report.py` 生成 `docs/flaky_report.md`；
3. 同一崩溃码连续出现 ≥3 次：必须复现并修复，或标记 quarantine（`pytest.mark.skip` + issue）；
4. 新增测试禁止跨用例共享 QWidget/QApplication 全局状态；
5. 隔离/原生插件测试使用独立进程或显式 teardown。

## 目标

- 4 周内将分片崩溃事件率降至 **0**；
- 若无法消除，保持逐文件复跑门禁并记录风险。

## 命令

```powershell
python tools/run_tests_sharded.py --shards 3 --retries 1 --parallel
python tools/flaky_report.py
```
