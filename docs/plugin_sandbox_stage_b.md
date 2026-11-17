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

## B0 原型（已实现，2026-11-12）

| 文件 | 作用 |
|---|---|
| `core/sandbox_rpc.py` | JSON-RPC 2.0 行协议编解码/错误码 |
| `core/plugin_host.py` | 子进程宿主：加载插件、`RemoteAPI`、`CapabilityBroker` 权限校验 |
| `core/plugin_supervisor.py` | 主进程监督者：spawn、握手（hello/ready）、API 转发、终止/崩溃检测 |
| `tests/test_v225_sandbox_b0.py` | 编解码、权限拒绝（-32001/-32601）、端到端隔离、崩溃隔离 |

协议流程：`host.hello` → 父进程 `host.ready` → 插件 `on_activate`（API 经 `api.call` 往返）→ `host.activated` → `host.shutdown`。

B0 限制：菜单回调仅传函数名（B1 上 callback id）、文件/网络 broker 白名单未接入、默认未接管现有插件加载（feature flag 待 B1）。

验证：`pytest tests/test_v225_sandbox_b0.py` → 4/4 通过（含 `os._exit` 崩溃不影响父进程）。

## B1 试点（已接入，2026-11-12）

| 能力 | 实现 |
|---|---|
| Feature flag | `QINGCAO_PLUGIN_ISOLATION=off\|demo\|all`（`app/plugin_isolation.py`） |
| 菜单回调 | 子进程注册 callback id；主进程 `invoke_callback(id)` → `host.callback` RPC → 执行插件函数 |
| 路径策略 | `core/plugin_sandbox_policy.py`：`read_file/write_file` 仅允许白名单根目录 |
| 宿主 API | `get/set_current_text`、菜单/状态项、设置 schema、日志、配置读写 |
| 试点 | `plugins/demo` 已在子进程激活；菜单「显示当前文件字符数」回调成功（输出字符数 11） |

验证命令：

```powershell
$env:QINGCAO_PLUGIN_ISOLATION = "demo"
python tools/verify_plugin_isolation.py --plugin plugins/demo
# [B1] 插件已隔离激活： demo
# [menu] 工具/Demo/显示当前文件字符数 0
# [message] Demo 当前文件字符数: 11
```

测试：`tests/test_v225_sandbox_b0.py` 7/7（含路径策略、菜单回调、开关、崩溃隔离）。

B1 限制：默认仍不接管现有加载（需显式 flag）；文件/网络白名单仅覆盖 `read_file/write_file`；UI 集成（菜单实际点击 → 宿主）待 B1.5。

## B2.1 远程面板（已实现，2026-11-12）

- 子进程 `RemoteAPI.register_remote_panel(title, fields, refresh)`；父进程 `WindowHostAPI` 创建 QDockWidget + 字段标签，1s 定时调用插件 refresh 回调（参数为当前文本快照），更新标签；
- 菜单回调显示面板：`show_remote_panel(panel_id)`；
- wordcount 新增隔离分支：`REMOTE_FIELDS` + `_remote_refresh(text)`，面板在宿主侧渲染；
- demo 灰度集合：`demo`、`wordcount`（`QINGCAO_PLUGIN_ISOLATION=demo` 时主进程排除、子进程承载）。

验证：
```
python tools/verify_plugin_isolation.py --plugin plugins/wordcount
# [panel] 字数统计 fields= 6
# [panel] show 1
# [B1] 插件已隔离激活： wordcount
```

限制：json_formatter 的 hover/code-action provider 仅登记未接线（B2.1b）；设置 schema 仅存储未渲染（R1.2）。

## R1.3 网络 broker（已实现，2026-11-12）

- `RemoteAPI.http_request(url, method, headers, data, timeout)` → 主进程 `CapabilityBroker._http_request`；
- **域名白名单**：manifest `network_allowlist: ["api.example.com"]`（无配置则全部拒绝）；
- **协议限制**：仅 http/https；响应上限 1MB（截断标记）；
- **速率限制**：默认 60 次/分钟/插件；
- **拒绝审计**：`broker.network_denials`（host/rate/error），供 UI/日志汇总；
- 权限：仍需 `network` 权限声明。

验证：`tests/test_v225_sandbox_network.py`（白名单通过/域名拒绝审计/限流/子进程端到端）。

## B2.2 远程面板扩展（已实现，2026-11-13）

- 面板类型：`fields`（字段标签）/ `text`（QPlainTextEdit）/ `markdown`（QTextBrowser.setMarkdown）；
- `register_remote_panel(title, fields, refresh, kind=...)`；1s 定时以当前文本快照刷新；
- `todo_panel`：隔离模式按当前文本解析 TODO/FIXME，远程 text 面板展示；
- `markdown_preview`：隔离模式远程 markdown 面板（`setMarkdown` 渲染），符号 provider 暂不跨进程；
- 灰度集合扩展为：demo、wordcount、json_formatter、todo_panel、markdown_preview（+sandbox_demo）；
- logtail 仍待定：需要宿主侧文件跟随/路径白名单，避免子进程直接读任意日志。


## B3 高风险插件隔离（git_deep 试点，2026-11-16）

- 子进程不再直接执行 git/系统命令；宿主提供受控 API：`git_status/git_branch/git_diff/git_log/git_commit/git_push/git_pull/git_switch`（权限 `filesystem`，参数白名单由 GitClient 执行）；
- `git_deep` 在 `is_isolated` 时使用 `_HostGit` 适配器，所有 git 操作经 broker 往返；
- 隔离模式下 hunk 暂存明确提示暂不支持；
- 效果：demo/all 模式下 git_deep 可在子进程运行，process 权限不再由插件进程直接使用；
- 测试：`tests/test_v226_git_isolation.py` + 隔离集合断言。


## B3 信任门控（2026-11-16）

- `CapabilityBroker` 新增 `trusted`：**process/terminal/debugger** 等高风险 API 仅在 `trusted=True` 且 `allow_high_risk=True` 时放行；
- `PluginProcess` 透传 trusted（默认 False）；未签名/未授权插件调用返回 `-32001`；
- 已完成：git_deep 经宿主受控 Git API 隔离；
- **未完成**：ai_assistant/ python_debugger 的完整进程隔离需要宿主 HTTP 代理与调试会话服务，按 B3 后续排期；当前仍进程内，受权限确认保护。
- 测试：`tests/test_v226_b3_trust.py`（3/3）。


## B3 AI 网络代理（试点，2026-11-16）

- 新增 `core/ai_http.py`：仅 http/https、JSON POST、4MB 上限；
- `AIClient.set_http_transport(fn)`：注入宿主代理；启用后**非流式**请求走代理，流式调用抛错并由 `AIWorker` 回退非流式；
- `PluginAPI.ai_http_request`（network 权限）与隔离 broker `ai_http_request` 已提供；
- ai_assistant 仅在 `QINGCAO_AI_NETWORK_BROKER=1` 时启用（默认关闭），停用恢复 requests；
- 测试：`tests/test_v226_ai_broker.py`（transport/流式回退/broker 权限）。
- **未完成**：流式逐块代理、debugger 宿主服务仍待后续。


### AI 流式代理（2026-11-16）

- `AIClient.set_stream_transport(fn)`；OpenAI/Claude `chat_stream` 经宿主逐行 SSE 解析；
- ai_assistant `QINGCAO_AI_NETWORK_BROKER=1` 同时启用普通/流式 transport；
- 测试：分块内容与 callback。

### 调试器宿主服务

- 设计稿：`docs/debugger_host_service.md`（未实现，5–8 天）；
- 当前 debugger 仍进程内，被调试代码已在 driver 子进程。

### 调试器宿主服务 D1（2026-11-16）

- 新增 `core/debug_service.py`：RPC schema（start/stop/continue/step/locals/stack/eval + 事件）、`DebugService` 骨架；
- 默认关闭（`QINGCAO_DEBUGGER_HOST=1`），仅 trusted 可调用；
- 测试：`tests/test_v226_debug_service.py` 4/4；
- 下一步 D2：真实脚本 start/stop + 无孤儿进程。

### 调试器宿主服务 D3（2026-11-16）

- `debug.set_breakpoints`、continue/step over/into/out 接入；
- 会话信号桥接：`debug.break/output/exit/error` 事件；
- 测试：断点事件、单步命令、退出清理；
- 下一步 D4：locals/stack/eval + 远程面板。

### 调试器宿主服务 D5（2026-11-16）

- 新增 `ui/debug_host_panel.py`：监听 `DebugService.event`，展示调用栈/变量/状态；
- 测试：事件驱动更新（break/stack/locals/exit）；
- 下一步 D6：插件隔离分支 + 远程对接（D5 面板目前为宿主组件）。

### 调试器宿主服务 D6（2026-11-16）

- broker/WindowHostAPI 增加 `debug_*`（权限 `debugger`）；
- `python_debugger` 加入隔离集合，`_isolated_mode()` 分支调用 `api.debug_*`；
- 修复隔离子进程相对导入（按文件路径加载 mixin）；新增子进程 stderr 日志采集；
- 隔离激活实测 PASS；
- **待 D7**：隔离模式下真实脚本端到端调试（启动/断点/变量）。

### 调试器宿主服务 D8（2026-11-16）

- 全量测试通过；v2.26.9 发布；
- 发布 workflow 上传大资产超时，`ci_publish_release.py` 上传超时增至 900s 并支持重试；
- 手动补传 ZIP/SHA/sig 成功。


## 隔离插件 UI 级 e2e（2026-11-16）

- 真实 `IsolatedPluginHost` + QMainWindow + 隔离 `git_deep`：
  菜单「查看状态」→ 子进程 RPC → 宿主 Git API → 对话框；
- 补齐隔离 API：`get_current_filepath`、`show_text_dialog`；git_deep 声明 `editor_read`；
- 测试：`tests/test_v226_isolated_e2e.py`（1/1）。


## 隔离调试器 UI e2e + 信任白名单（2026-11-17）

- `QINGCAO_TRUSTED_PLUGINS`（逗号分隔）显式授予 `trusted` + `allow_high_risk`；默认空；
- `python_debugger` 隔离 e2e：菜单「调试当前文件」→ broker `debug_start` → 宿主 DebugService 真实会话 → 「终止调试」→ 会话清理；
- 测试：`tests/test_v226_isolated_e2e.py` 2/2（git_deep + python_debugger）。


## B3 AI 宿主服务（2026-11-17）

- 新增 `core/ai_service.py`：宿主侧持有 AI 客户端/Key，`ai_run(prompt,system,max_tokens)` 返回文本；
- broker/WindowHostAPI/RemoteAPI 增加 `ai_run`（权限 `network`）；
- 用途：后续隔离 ai_assistant 仅传 prompt，**API Key 不进入子进程**；
- 未完成：ai_assistant 插件子进程分支（UI/相对导入改造量大），当前仍进程内。


## AI 隔离 headless 分支（2026-11-17）

- 隔离加载器注册 `sys.modules[qc_isolated_plugin]`，支持插件包相对导入；
- ai_assistant 隔离模式仅注册 headless 动作（解释/重构/生成测试/审查），经宿主 `ai_run` 调用，Key 不进子进程；
- 限制：无流式/历史/diff/插入/面板；
- 测试：隔离 AI e2e + loader 相对导入。


### AI 隔离流式/历史（2026-11-17）

- `AIService.run(stream=True,use_history=True)`：宿主侧流式回调/历史，Key 不进子进程；
- 新增 `ui/ai_host_panel.py`：隔离插件 `ai_show_panel` → 宿主面板逐块显示；
- 面板在 GUI 线程创建（bridge），避免跨线程 QWidget；
- 测试：隔离 AI e2e 流式文本 `abc` 可见；
- 限制：仍无结果对话框/插入/diff/多会话管理。


### AI 隔离多会话/结果菜单（2026-11-17）

- `AIService` 按 session 维护消息历史；`ai_reset_history(session)` 新会话；
- 隔离插件菜单：打开输出面板 / 显示完整结果（宿主 show_text_dialog）/ 新会话；
- 测试：多会话历史隔离、隔离 AI e2e。


### AI 结果自动弹窗/多会话 UI（2026-11-17）

- AIHostPanel 增加会话下拉 + 新会话按钮；当前会话经 `ai_current_session` 传给子进程；
- 隔离插件设置 `auto_result_dialog`（默认开）：结果经宿主 `show_text_dialog` 自动弹出；
- 菜单：打开输出面板 / 显示完整结果 / 新会话；
- 测试：隔离 AI e2e 验证面板流式 + 自动弹窗 + 会话下拉。


### AI 结果受限插入/替换（2026-11-17）

- broker `ai_apply_result`（权限 `editor_write`）；
- 宿主在 GUI 线程执行插入/替换（proxy API 或 Scintilla 回退）；
- 隔离菜单：插入结果到光标 / 替换选中代码（仅用户显式触发，永不自动写入）；
- e2e：AI 结果 `abc` 成功插入编辑器；权限拒绝测试通过。


### AI 差异预览（隔离，2026-11-17）

- broker `ai_preview_diff`（权限 `editor_read`）；宿主用 difflib 生成 unified diff 并弹窗；
- 隔离菜单「预览差异」；不写编辑器；
- 测试：e2e 验证 `+abc` 出现；连续 5 轮综合测试全绿（14/14）。


### AI 会话重命名/删除 UI（2026-11-17）

- AIHostPanel 增加重命名/删除按钮；AIService `rename_session/delete_session`；
- 删除当前会话回退 default；目标重名拒绝；
- 测试：服务与面板 UI。


### AI 会话持久化/导出（2026-11-17）

- `AIService(history_path=...)` 自动加载/保存 `data/ai_host_sessions.json`（原子写）；
- `export_sessions/import_sessions`；面板「导出/导入」按钮（QFileDialog）；
- 测试：持久化跨实例、导出导入、面板按钮；AI 套件连续 3 轮 13/13。


### AI e2e 稳定化（2026-11-17）

- e2e 关闭自动弹窗（避免模态与 diff 断言竞态），流式/面板/插入/差异分别断言；
- 连续 5 轮综合 AI 测试全绿（13/13）。


### AI 会话加密/冲突策略（2026-11-17）

- 默认宿主服务 `encrypt=True`：Fernet + 安全存储密钥，文件为加密 envelope；兼容旧明文；
- 导入冲突策略：rename（默认）/overwrite/skip；面板 QInputDialog 选择；
- 测试：加密跨实例、三种冲突策略；AI 套件连续 3 轮 15/15。


### AI 会话导入预览（2026-11-17）

- `AIService.preview_import(path, conflict)` 返回新增/冲突计划，不修改状态；
- 面板导入前显示新增数、冲突映射，确认后再执行；
- 测试：预览计划/不修改状态；AI 套件连续 3 轮 16/16。


### AI 会话搜索/导出范围（2026-11-17）

- `search_sessions`（按会话/角色/内容，限制 100 条）；面板搜索框+查找；
- `export_sessions(names=...)` 支持全部/当前会话；面板范围选择；
- 测试：搜索、范围导出、面板按钮。


### AI 搜索结果跳转/高亮（2026-11-17）

- 搜索命中列表选择后跳转到会话并显示历史；
- `QTextEdit.ExtraSelection` 高亮全部命中；
- 测试：跳转会话/高亮计数；AI 套件连续 3 轮 19/19。


### AI 搜索过滤（2026-11-17）

- `search_sessions(current_only, role)`：仅当前会话、按角色筛选；
- 面板：仅当前会话勾选 + 角色下拉；
- 测试：过滤逻辑/面板控件；AI 套件连续 3 轮 21/21。
