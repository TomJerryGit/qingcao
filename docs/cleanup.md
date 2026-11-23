# 磁盘清理（本地开发/CI）

## 低风险清理（已执行）

历史来源目录、旧构建、测试 dump 已清理，约 1.82GB。

## Runner 旧版本清理（需管理员）

脚本：`tools/cleanup_runner_artifacts.ps1`

```powershell
# 预览
powershell -ExecutionPolicy Bypass -File tools\cleanup_runner_artifacts.ps1 -DryRun

# 执行（管理员）
powershell -ExecutionPolicy Bypass -File tools\cleanup_runner_artifacts.ps1

# 同时清理 _work 构建产物（约 260MB，下次 CI 会重建）
powershell -ExecutionPolicy Bypass -File tools\cleanup_runner_artifacts.ps1 -IncludeWorkCache
```

## 安全措施

- 检测到 `Runner.Worker` 活动任务时直接退出；
- 只删除 `D:\actions-runner` 下白名单目标；
- 停止的服务在 finally 中自动恢复；
- 默认只保留最近 5 个 Worker 诊断日志；
- 不触碰当前 `bin`、`externals`、`_work` 源码。

## 日志

`tools/cleanup_runner_artifacts.log`


## 总入口（推荐）

```powershell
# 预览（无需管理员）
powershell -ExecutionPolicy Bypass -File tools\cleanup_all.ps1 -DryRun

# 执行（管理员；含 Runner 清理）
powershell -ExecutionPolicy Bypass -File tools\cleanup_all.ps1

# 只清理项目、不动 Runner
powershell -ExecutionPolicy Bypass -File tools\cleanup_all.ps1 -SkipRunner

# 包含 _work 构建缓存
powershell -ExecutionPolicy Bypass -File tools\cleanup_all.ps1 -IncludeWorkCache
```
