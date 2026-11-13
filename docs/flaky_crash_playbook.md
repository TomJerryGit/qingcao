# Flaky / 崩溃治理与 CI 队列报告（R3，2026-11-13）

## 1. 崩溃聚合现状

`python tools/crash_triage.py`：

| 项 | 数值 |
|---|---|
| faulthandler/dump 文件 | 9（其中 **5 个空文件**） |
| WER/minidump | 5 |
| CI flaky 记录 | 8 |
| 归组 | 3 组（unknown 2 / 0x8001010d 2） |

Top 签名：
- `Windows fatal exception: code 0x8001010d` @ `main_window.py:_show_daily_tip`
- `Windows fatal exception: code 0x8001010d` @ `socket.py:getaddrinfo`

`0x8001010d` = `RPC_E_CANTCALLOUT_ININPUTSYNCCALL`，与**原生 Windows 对话框/COM 调用**相关。

## 2. 已实施缓解

- **每日技巧对话框改为非原生 QMessageBox**（`DontUseNativeDialog`），避免 COM 输入同步调用；异常时回退。
- `crash_triage` 改进：
  - 空 dump 单独计数（不再归为 unknown）；
  - 无异常行的 faulthandler 归为 `uncaught | <top frame>`；
  - 扫描 WER/minidump（`data/crash_dumps`、`%LOCALAPPDATA%/CrashDumps`、runner crash_dumps）。

## 3. CI 队列 / 耗时（job 级，最近 14 天）

| 工作流 | job 数 | 队列 P50 | 队列 P95 | 耗时 P50 | 耗时 P95 |
|---|---|---|---|---|---|
| Test | 32 | 577s | **1382s（≈23min）** | 44s | 394s |
| Release | 2 | 2s | 3s | 257s | 1777s |

- 队列来源：自托管 runner 单一、Test 任务串行；watchdog/托管兜底已存在但不是全量测试；
- 目标：队列 P95 **<30 分钟**（当前 23 分钟，接近达标）。

## 4. 测试耗时

- 本地全量：`run_tests_sharded.py --shards 3 --parallel` → **3.9 分钟**（197 文件）；
- CI Test job 时长 P50 44s / P95 394s（job 统计数据口径，见 `docs/ci_queue_report.md`）；
- 本轮修复因 `plugin_store` 拆分导致的两个静态测试后，全量应恢复绿色。

## 5. 后续动作

1. CI 上传崩溃 artifact（`logs/crash_dump_*.log`、`data/test_shards/crashed_*.log`、WER dmp）；
2. `socket.getaddrinfo` 崩溃：把 AI/网络探测移到后台线程并捕获异常；
3. 队列：低峰时段合并 Test 触发、或增加第二 runner；托管 Windows 全量测试作为兜底；
4. 每周运行 `tools/ci_queue_stats.py` 与 `tools/crash_triage.py`，跟踪 P95 与 Top 签名。
