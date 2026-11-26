# 依赖与安全审计（v2.26.42 / 2026-11-26）

## 范围

- 依赖清单与版本约束；
- 插件权限/沙箱 RPC；
- 危险 API 与硬编码密钥；
- 发布签名与 CI 安全检查。

## 结果

| 检查 | 结果 |
|---|---|
| 硬编码 API Key / 私钥 | 未发现 |
| 沙箱 RPC 白名单 | 11 个方法，**通过** |
| 网络线程审计 | **0 违规** |
| 插件审计 | 12 pass / 1 review / 2 warn |
| 表达式求值 eval | **已替换为 AST 受限求值** |
| Release 签名 | Ed25519 `.sig` 已生成 |
| 依赖漏洞扫描 | 未安装 pip-audit，未执行 |

## 插件审计说明

- `python_debugger` review：导入 `subprocess`，manifest 已声明 `process` 权限；
- `markdown_preview` / `spell_check` warn：写文件，manifest 已声明 `filesystem` 权限；
- 均为“权限已声明”的启发式告警，不是缺失权限。

## 发现与处理

| 发现 | 严重度 | 处理 |
|---|---|---|
| `eval_expression` 使用 `eval` | 中 | 已替换为 `core/safe_expr.py` AST 受限求值；仅允许数字/运算符 |
| 插件 `run_command` 使用 `shell=True` | 高（若插件不可信） | 已由 `process` 权限门控；仅信任插件；文档标注 |
| 插件 `run_python` 在宿主 `exec` | 高（若插件不可信） | 同上；建议后续只允许隔离进程执行 |
| 依赖范围宽、无 hash/lock | 中 | 建议 CI 增加 `pip-audit` 与固定依赖 |
| Release 未跑安全审计 | 中 | 单 workflow 目前只跑 Lint/Test；建议加入安全 smoke |

## 建议

1. CI 安装 `pip-audit`，对 `requirements.txt` 扫描；
2. 生成锁文件（`pip-compile`/`pip freeze`）并定期更新；
3. 不安装不可信插件；`process` 权限视为完全信任；
4. 后续将 `run_python` 迁移到隔离子进程；
5. Release 增加 `audit_sandbox_rpc.py` + `audit_network_threads.py` 快速门禁。

## 结论

未发现硬编码密钥；沙箱 RPC/网络线程审计通过；表达式求值风险已修复。主要剩余风险是**插件信任模型**与**依赖漏洞扫描缺失**，属于架构/流程决策，不是当前版本的直接漏洞。
