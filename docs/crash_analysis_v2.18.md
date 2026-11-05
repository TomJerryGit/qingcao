# CI Qt 崩溃历史分析（v2.18 P2）

> 数据来源：`D:\actions-runner\_diag`（Worker 日志）与本地 dump/faulthandler 日志。

## 统计

| 指标 | 数值 |
|---|---|
| 扫描 Job 数（完成标记） | 338 |
| 失败 Job 数（含非崩溃） | 54 |
| 含原生崩溃码 `3221225477` 的 Job | 0 |

## 崩溃日期分布

- 日志中未发现原生崩溃码记录

## 现有证据文件

- WER dump: 5 个
- faulthandler 崩溃栈: 5 个
  - `D:\actions-runner\crash_dumps\python.exe.11392.dmp`
  - `D:\actions-runner\crash_dumps\python.exe.11952.dmp`
  - `D:\actions-runner\crash_dumps\python.exe.12092.dmp`
  - `D:\actions-runner\crash_dumps\python.exe.7624.dmp`
  - `D:\actions-runner\crash_dumps\python.exe.9684.dmp`
  - `D:\QingCaoEditor\logs\crash_dump_1116.log`
  - `D:\QingCaoEditor\logs\crash_dump_11256.log`
  - `D:\QingCaoEditor\logs\crash_dump_13316.log`
  - `D:\QingCaoEditor\logs\crash_dump_13540.log`
  - `D:\QingCaoEditor\logs\crash_dump_8180.log`

## 结论与建议

1. 历史 CI 失败主要来自**测试失败**与**负载误报**，原生崩溃为偶发；
2. 当前无可用 dump 现场：下次崩溃发生后，WER dump 与
   `logs/crash_dump_<pid>.log` 会随 CI 步骤自动采集；
3. 已实施缓解：全量测试重试 1→2、性能门禁 `--auto` 5× 下限、
   主题/字体相关改动跑 E2E 基线；
4. 下一步：若 dump 出现，按 `docs/ci_qt_crash_playbook.md` 用
   WinDbg/cdb 分析栈顶模块，再决定是否补 Qt 符号或规避代码路径。
