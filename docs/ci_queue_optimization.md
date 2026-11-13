# CI 队列优化：托管 Windows 全量测试兜底（R3+）

> 背景：Test 队列 P95 ≈1382s（23 分钟），自托管单 runner 串行，卡住会延迟发布。

## 方案

| 组件 | 变更 |
|---|---|
| `test-fallback.yml` | 托管 `windows-latest` 跑**全量**测试：`--shards 3 --retries 1 --parallel`；超时 90 分钟 |
| `ci-watchdog.yml` | 每 **10 分钟**检查一次；Test 排队 >**10 分钟**且该 SHA 无兜底运行时自动 dispatch（按 SHA 去重） |
| `ci_release_gate.py` | 新增 `--fallback-workflow`：Test 失败/排队时，若 `test-fallback` 对同 SHA 成功 → 门禁视为通过 |
| `release.yml` | gate 传入 `--fallback-workflow test-fallback.yml`，发布不再被单 runner 队列无限阻塞 |

## 预期效果

- 队列 >10 分钟即启动托管全量测试（约 10–15 分钟完成）；
- 发布门禁可基于托管结果通过，无需等待自托管队列；
- 自托管 Test 仍保留为权威结果（失败时 fallback 不能掩盖——fallback 仅作为 **额外** 通过路径）。

## 注意事项

- 托管 runner 为公开仓库免费额度；Windows 依赖安装约 2 分钟；
- 若自托管与托管结果不一致，以**更严格的一方**为准，需人工复查；
- watchdog 仍会取消 >120 分钟的卡死运行（原有逻辑）。

## 验收

- `tests/test_v225_ci_watchdog.py`：fallback 阈值 10 分钟；
- `tests/test_v225_release_gate.py`：fallback 成功可替代 Test 失败；
- 真实效果：观察下一次 main 推送/发布时的 `ci_queue_report.md` P95。

## 后续

- 若队列仍高：增加第二自托管 runner，或把 Test 主路径迁移到托管 runner；
- 统计 job 级队列：`python tools/ci_queue_stats.py --days 14 --workflows Test,Release`。

## 首轮观察（2026-11-13）

- `ci_queue_stats.py --limit 20`：Test job 队列 P50=572s、P95=1382s（≈23min），样本仍包含改动前运行；
- Release 队列 P50=3s/P95=4s；Release job 耗时 P95=1777s（构建+门禁等待）；
- 结论：优化已上线，需在后续 1–2 天新运行积累后复测 P95；若仍高，增加第二 runner。

## 复测结果（2026-11-13，v2.26.1 发布后）

- 窗口：最近 2 天，30 runs / 60 jobs；
- **Test**：队列 P50=396s、**P95=1526s（≈25min）**；耗时 P95=713s；
- **Release**：队列 P95=3s；耗时 P95=1065s（较上次 1777s 改善）；
- 结论：托管兜底让**发布**不再被队列阻塞，但 **Test 自托管队列 P95 未改善（反而 23→25min）**；
  下一步需把 Test 主路径迁移到托管 runner 或增加第二 runner，单靠 fallback 不能降低该指标。
