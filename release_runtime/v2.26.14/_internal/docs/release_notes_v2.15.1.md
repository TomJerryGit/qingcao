# 青草编辑器 v2.15.1 发布说明

> 发布日期：2026-10-30 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.15.1`）
> 主题：**多实例健壮性 + 安全工程**

---

## 新增与改进

### 多实例广播协议版本协商
- 新增 `hello` / `hello_ack` 交换协议版本；
- 版本不一致时状态栏提示「按兼容模式处理」（仅一次）；
- 未来版本事件安全忽略，不影响旧实例。

### 性能门禁智能降级
- `bench_optimization.py --auto`：按 CPU/内存负载自动放大容差（1.0~4.0）；
- CI 使用 `--auto --factor 3.0`，减少负载导致的误报。

### 沙箱 RPC 方法白名单自动化审计
- 新增 `tools/audit_sandbox_rpc.py`：校验白名单 / worker / manager 一致性；
- `--strict` 不一致即失败，已纳入 CI。

### 插件市场签名校验（fail closed）
- SHA256 完整性 + HMAC-SHA256 来源签名；
- 密钥来自 `QINGCAO_PLUGIN_SIGNING_KEY`；未配置密钥时拒绝带签名安装；
- 文档：`docs/plugin_market_security.md`。

### 调试器求值 RPC 层校验
- 宿主侧新增 `validate_eval_expression`：空/超长表达式直接拒绝；
- 目标子进程内 `_safe_eval` 二级校验，形成两级防线。

## 验证

- 分片并行全量：111 个测试文件 → 2 片通过；
- 沙箱 RPC 审计 `--strict` 通过（本地 + CI）；
- CI：test / test-py312 全绿。

## 升级注意事项

1. v2.15.0 → v2.15.1 无数据迁移；
2. 插件市场带签名安装需配置 `QINGCAO_PLUGIN_SIGNING_KEY`，否则会被拒绝（符合预期）。
