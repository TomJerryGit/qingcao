# 插件沙箱阶段 B 设计稿（v3.x）

> 目标：把插件从主进程隔离到 **插件宿主子进程**，通过 JSON-RPC 能力代理调用宿主 API；阶段 A 的告警升级为可审计、可拒绝的能力边界。

## 1. 目标与非目标

| 目标 | 非目标（本阶段不做） |
|---|---|
| 插件崩溃不带走主进程 | OS 级 AppContainer/沙箱（阶段 C） |
| 高风险能力（process/terminal/debugger）默认拒绝 | WASM 插件 |
| 文件/网络能力经 broker 白名单 | 完全兼容现有全部插件（分阶段迁移） |
| 每个插件独立进程、独立日志/资源限额 | 多插件共享进程 |

## 2. 架构

```
┌──────────── 主进程 (Qt UI) ────────────┐
│ PluginHostSupervisor                  │
│  ├─ 每插件: QProcess(PluginHost)      │
│  ├─ 能力代理 CapabilityBroker         │
│  └─ 事件总线桥 (file_opened 等)       │
└───────────────┬───────────────────────┘
                │ JSON-RPC 2.0 over stdio (长度前缀/行分隔)
┌───────────────▼───────────────────────┐
│ PluginHost (子进程, Python)            │
│  ├─ 加载插件 __init__.py               │
│  ├─ 提供受限 api_remote 对象           │
│  └─ 请求/响应/事件循环                 │
└───────────────────────────────────────┘
```

- 传输：**stdin/stdout JSON 行**（每行一个 JSON-RPC 消息；stdout 禁止插件直接 print，重定向到日志）；
- 现有插件可继续使用 `PluginBase`，宿主提供代理版 `self.api`，方法签名保持一致；
- UI 回调（菜单/状态项）由宿主注册为 RPC callback id，子进程触发时由主进程执行。

## 3. 协议（JSON-RPC 2.0）

```json
{"jsonrpc":"2.0","id":1,"method":"api.call","params":{"name":"get_current_text","args":[]}}
{"jsonrpc":"2.0","id":1,"result":{"ok":true,"value":"..."}}
{"jsonrpc":"2.0","method":"host.event","params":{"event":"file_opened","data":{...}}}
{"jsonrpc":"2.0","method":"plugin.log","params":{"level":"info","message":"..."}}
```

错误码：

| code | 含义 |
|---|---|
| -32601 | 方法不存在 / 权限不允许 |
| -32001 | 能力被拒绝（权限未声明/风险策略） |
| -32002 | 超时 |
| -32003 | 资源超限（内存/RPC 速率） |

**权限校验在主进程 broker 执行**（子进程不可信）；高风险方法需 manifest 声明 + 用户确认 + 签名信任。

## 4. 能力代理范围（阶段 B1）

| API 类别 | 处理 |
|---|---|
| `get_current_text` / `set_current_text` | 代理（editor_read/write） |
| `add_menu` / `add_status_item` / `show_message` | 代理（dialog；回调回主进程） |
| `run_command` / `run_python` | **默认禁用**；显式 `process` + 每次确认，超时/输出上限 |
| `register_completion/hover/code_action` | 代理，结果回传 |
| 文件读写 | 仅 broker 白名单路径（项目目录/插件数据目录），拒绝绝对路径逃逸 |
| 网络 | broker 域名白名单 + 速率限制（阶段 B2） |

## 5. 生命周期与失败处理

1. 主进程启动插件 → spawn 子进程 → 握手（`host.hello` 含 manifest/权限）；
2. 插件 `on_activate` 超时（默认 5s）→ 标记失败、不阻塞 UI；
3. 子进程崩溃 → 主进程记录 crash（`crash_triage` 归组）→ 可选一次自动重启（禁止循环）；
4. `on_deactivate` 超时 → 强制 terminate；
5. 插件禁用/卸载 → 子进程退出 + 回调清理。

## 6. 兼容与迁移

- 阶段 B0：新增 `PluginHost` 协议库 + 单插件（`demo`）试点，默认仍走进程内；
- 阶段 B1：`ai_assistant`/`wordcount` 等低风险插件迁入子进程；
- 阶段 B2：高风险插件（`python_debugger`）要求签名 + 显式授权；
- 环境开关：`QINGCAO_PLUGIN_ISOLATION=0|1|strict`，默认 `0`（保持现状），CI 开启 `strict` 跑回归。

## 7. 性能预算

| 指标 | 目标 |
|---|---|
| 插件激活额外延迟 | < 150ms/插件 |
| RPC 往返（本机） | < 5ms |
| 内存/插件 | < 80MB |
| 崩溃恢复 | < 2s |

## 8. 验收（实现阶段）

- 单测：协议编解码/权限拒绝/超时/崩溃重启；
- 集成：3 个试点插件功能对等；
- 故障注入：子进程 `os._exit` 不影响主进程；
- 安全：`run_command` 默认被拒绝；路径逃逸被拒。

## 9. 风险

| 风险 | 缓解 |
|---|---|
| 回调/RPC 死锁 | 全部调用带超时；禁止同步嵌套回调 |
| 插件输出污染 stdout | 启动时重定向 stdout→stderr/日志 |
| 性能回退 | 默认关闭；逐插件灰度 + 基准 |
| 兼容性 | 保留进程内实现，feature flag 切换 |
