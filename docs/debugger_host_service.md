# 调试器宿主服务设计（B3，未实现）

> 目标：把 `DebugSession` 生命周期从插件进程移到宿主，插件通过 JSON-RPC 控制；调试面板走远程面板。

## 现状

- `plugis/python_debugger` 的插件 UI/会话控制在主进程；被调试程序已在 **driver 子进程**（`DebugSession` → `driver.py`）；
- `process` 权限由插件使用（启动 driver），仍是高风险面。

## 目标架构

```
主进程 DebugService(QObject)
 ├─ 持有 DebugSession（现有类）
 ├─ RPC: debug.start/stop/continue/step/locals/stack/eval
 └─ 远程面板事件：break/stack/locals/watches
插件子进程（隔离模式）
 └─ 仅通过 api.debug_* 调用，不直接 subprocess
```

## 协议（草案）

| 方法 | 参数 | 返回 |
|---|---|---|
| `debug.start` | script, args | `{ok, error}` |
| `debug.stop` | — | `{ok}` |
| `debug.continue` | — | `{ok}` |
| `debug.step` | over/into/out | `{ok}` |
| `debug.locals` | — | `{values}` |
| `debug.eval` | expr | `{value/error}` |

事件：`debug.break {file,line,locals,stack,watches}` → 远程面板刷新。

## 迁移步骤

1. 新增 `core/debug_service.py`（包装 DebugSession，信号转 RPC 事件）；
2. PluginAPI 增加 `debug_*`（权限 `debugger`，仅 trusted）；
3. 插件隔离模式改用 `debug_*`，进程内模式保留回退；
4. 远程面板展示栈/变量/监视；
5. 测试：真实脚本断点、单步、终止（无孤儿）。

## 估算与风险

- 5–8 天；涉及 Qt 信号跨进程、会话生命周期、面板同步；
- 默认 feature flag 关闭，逐插件灰度；
- 在完成前，debugger 继续进程内运行并受权限确认保护。
