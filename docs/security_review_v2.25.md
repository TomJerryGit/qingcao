# 安全复核与整改（v2.25）

## P0：self-hosted runner × pull_request

- **问题**：`test.yml` 同时对 `pull_request` 触发并运行在自托管 Windows runner；公开仓库的 PR 可在维护者机器上执行不可信代码（凭据/文件风险）。
- **整改**：移除 `test.yml` 的 `pull_request` 触发；PR 验证改由 **GitHub 托管** 的 `test-fallback.yml`（windows-latest）承接。
- **后续（需人工）**：在仓库设置中为 main 添加分支保护（要求 Lint/Security/Test 通过），并限制 self-hosted runner 仅接受受信任分支。

## P2：shell=True / exec / pickle

| 位置 | 用途 | 门控 | 结论 |
|---|---|---|---|
| `app/plugin_api_data.py:279` `subprocess.run(shell=True)` | 插件 API `run_command` | `PERMISSION_PROCESS`（高风险，安装时确认） | 保留；属显式高风险能力 |
| `app/plugin_api_data.py:302` `exec(code)` | 插件 API `run_python` | `PERMISSION_PROCESS` | 保留；文档标注"危险" |
| 其余 `app.exec()` / `menu.exec()` | Qt 事件循环，非进程执行 | — | 非风险 |

建议：插件沙箱（v3.0 阶段 B）落地后，将 `run_command/run_python` 迁移到隔离子进程。

## P2：构建产物与锁文件

- 已删除本地 `build/`（25.8MB）与 `dist/`（208.7MB）；
- 新增 `requirements-lock.txt`（当前环境冻结的直接依赖），CI/发布可使用锁定安装；
- `requirements.txt` 的宽松约束保留以兼容版本范围；建议发布流水线使用 lock 文件。

## P2：其他

- **tag 与 release 不一致**：v2.25.0 发布门禁未通过期间 tag 已存在；整改后重新发布。
- **分支保护**：无 API 权限，需仓库管理员在 GitHub 设置中手工开启。
- **TODO/FIXME**：见 `docs/todo_cleanup_v2.25.md`。
