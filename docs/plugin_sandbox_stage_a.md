# 插件沙箱阶段 A（v2.25）

> 范围：**只告警不阻断**。目标是在不破坏现有 14 个插件的前提下，建立可观测的威胁面与升级路径。

## 威胁模型（同进程插件）

| 威胁 | 示例 | 当前状态 |
|---|---|---|
| 任意代码执行 | `exec/eval`、动态导入 | 仅 `PERMISSION_PROCESS` 门控；插件本身仍可调用 |
| 系统命令 | `os.system/subprocess` | 同上；阶段 A 静态 + 运行时告警 |
| 原生调用 | `ctypes` | 告警 |
| 网络外发 | `socket/requests` | `PERMISSION_NETWORK` 门控 |
| 文件读写 | 任意路径 | `PERMISSION_FILESYSTEM` 门控（同用户权限） |
| 持久化 | 启动项/注册表 | `winreg` 告警，阶段 B 隔离 |
| 崩溃连带 | 插件段错误拖垮主进程 | 阶段 B 子进程宿主 |

## 阶段 A 措施

1. **静态审计** `core/plugin_guard.py::audit_source/audit_plugin/audit_all`：
   - AST 检测高危 import（ctypes/subprocess/multiprocessing/_winapi/winreg）；
   - 危险调用（os.system/popen/exec/eval/pickle.load/marshal.loads 等）；
2. **可信允许列表** `resources/trusted_plugins.json`：第一方插件标记 trusted，告警抑制（但报告仍列出）；
3. **运行时告警** `install_audit_guard()`（启动时安装）：
   - 审计事件 `import`/`os.system`/`subprocess.Popen`/`ctypes.dlopen`；
   - 仅当调用栈来自 `plugins/` 时记录 `[sandbox-A]` 警告，每项一次；
4. **审计报告** `tools/plugin_sandbox_audit.py` → `docs/plugin_sandbox_report.md`、`data/plugin_sandbox_report.json`。

## 当前报告（v2.25）

- 14 个插件，全部在第一方可信列表；
- 非可信高危发现：**0**；
- 报告：`docs/plugin_sandbox_report.md`。

## 残余风险

- 同进程插件仍可通过 `sys.modules`/反射绕过静态检测；
- 告警不阻断，恶意插件仍可执行；
- 网络/文件系统仅靠 API 门控，进程级权限未隔离。

## 阶段 B 计划（后续）

1. 插件宿主子进程 + JSON-RPC 能力代理（崩溃隔离、权限集中）；
2. 文件/网络能力 broker（白名单路径/域名）；
3. 高风险权限默认拒绝 + 可信签名强制；
4. 阶段 C：Windows AppContainer/低完整性或 WASM 纯逻辑插件。

## 验收

- `tests/test_v225_plugin_guard.py`：静态检测/可信列表/批量审计；
- 启动时 `[sandbox-A]` 告警可观测；
- 第一方插件零回归。
