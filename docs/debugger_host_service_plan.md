# 调试器宿主服务项目计划（B3，2026-11-16 立项）

## 1. 项目目标

把 `python_debugger` 的调试会话生命周期从插件进程移到**主进程 DebugService**，插件仅通过 RPC 控制；调试面板走远程面板。完成标准：

- 插件子进程不再直接持有 `process` 能力（debugger 高风险面收敛）；
- 断点/单步/变量/调用栈/监视功能对等；
- 默认 feature flag 关闭，灰度开启，失败可回退进程内实现。

## 2. 范围

| 包含 | 不包含 |
|---|---|
| DebugService（包装现有 DebugSession） | 新调试协议/替换 bdb |
| RPC：start/stop/continue/step/locals/stack/eval | 远程 attach/多进程调试 |
| 远程面板：栈/变量/监视 | 调试器 UI 大改版 |
| 权限门控（trusted + debugger） | 其他插件迁移 |

## 3. 架构与协议

```
主进程 DebugService(QObject)
 ├─ DebugSession（现有 driver 子进程）
 ├─ RPC 方法（权限 debugger，仅 trusted）
 └─ 事件：break/stack/locals/watches → 远程面板
插件子进程 → api.debug_*（无 subprocess）
```

协议见 `docs/debugger_host_service.md`（草案）。

## 4. 工作分解（8 天）

| 天 | 任务 | 交付/验收 |
|---|---|---|
| D1 ✅ | DebugService 骨架 + RPC schema（`core/debug_service.py`） | 单测 4/4：schema/权限/生命周期 |
| D2 ✅ | start/stop 迁移（真实 DebugSession） | 真实脚本启停、无孤儿、失败清理、shutdown 幂等 |
| D3 ✅ | continue/step/断点事件迁移（`debug.set_breakpoints`） | 断点/单步命令与事件广播测试 |
| D4 ✅ | locals/stack/eval RPC + 结果事件 | 信号替身验证；真实断点集成测试暂缓（曾挂起） |
| D5 ✅ | 宿主面板（栈/变量，`ui/debug_host_panel.py`） | 事件驱动更新测试；插件隔离接入留 D6 |
| D6 🟡 | `PluginAPI.debug_*` + feature flag + 宿主面板 | flag 测试 11/11；隔离插件分支未接（需 broker debug_*） |
| D7 | 故障注入/崩溃/超时 | 子进程崩溃不影响主进程 |
| D8 | 回归 + 文档 + 发布门禁 | 全量测试、性能对比、发布说明 |

## 5. 里程碑

- **M1（D2）**：会话可启动/停止，RPC 通路打通；
- **M2（D4）**：调试控制与变量/栈对等；
- **M3（D6）**：隔离模式端到端可用；
- **M4（D8）**：回归通过，默认关闭、灰度开启。

## 6. 验收标准

- 断点/单步/继续/局部变量/调用栈/监视全部通过真实脚本测试；
- 调试插件在隔离模式不调用 `subprocess`；
- 崩溃/超时注入不影响主进程；
- 全量测试 3 片通过；性能回退 <10%；
- flag 关闭时行为与当前完全一致。

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Qt 信号跨进程/线程 | 事件队列 + 超时；先非 UI 通道 |
| 会话状态不一致 | 单会话锁；状态机 + 超时 |
| 面板同步复杂 | 先栈/变量只读，监视后置 |
| 回退成本 | feature flag 默认关闭，保留进程内路径 |

## 8. 资源与排期

- 需要 1 名插件/调试方向开发，5–8 个工作日；
- 依赖：`core/debug_service.py`、`PluginAPI.debug_*`、远程面板协议（已有 text/markdown 可扩展）；
- 排期建议：下一迭代（v2.27）独立里程碑，不阻塞 v2.26.x。

## 9. 跟踪

- GitHub Issue：调试器宿主服务（B3）项目看板；
- 设计稿：`docs/debugger_host_service.md`；
- 每周更新进度/风险。
