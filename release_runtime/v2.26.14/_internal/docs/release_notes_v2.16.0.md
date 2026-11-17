# 青草编辑器 v2.16.0 发布说明

> 发布日期：2026-10-30 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.16.0`）
> 主题：**安全与市场生态**

---

## 一句话概括

v2.16.0 完成插件市场**Ed25519 非对称签名**与安全状态展示、沙箱 RPC 审计基线、
调试器求值模式可配置；并落地分片自适应、诊断来源过滤、广播 ACK 重试与
多主题 E2E 截图基线。

---

## 安全与市场

- **Ed25519 非对称签名**：公钥可配置（`QINGCAO_PLUGIN_PUBKEYS`，支持轮换）、
  吊销名单（`QINGCAO_PLUGIN_REVOKED`），HMAC 回退；未配置密钥时拒绝带签名安装；
- 插件市场详情展示**安全状态**（未签名 / SHA256 / HMAC / Ed25519 / 已吊销）；
- **沙箱 RPC 审计基线**：`tools/baselines/sandbox_rpc.json`，CI 比对白名单变更；
- 调试器求值模式可配置：`QINGCAO_DEBUGGER_EVAL_MODE=restricted|developer`。

## 多实例与稳定性

- 广播 **ACK 重试**：file_saved 带 `msg_id`，500ms 未确认自动重发一次；
- 修复 ACK 中继回环（`_read_from` 单次处理上限 1000 条防御）；
- 测试**分片数自适应**（按 CPU 数 2~4 片），CI 使用 `--auto-shards`。

## UI 与验证

- 问题面板新增「来源」列，并支持按沙箱插件来源动态过滤；
- 多主题 **E2E 截图基线**：`tools/theme_e2e_screenshots.py`
  （dark/light/eye/high_contrast × 主窗口+插件面板，产物 `docs/theme_baseline/`）；
- 多屏高 DPI 手动验证清单：`docs/manual_validation_v2.16_multimonitor.md`。

## 验证

- 分片并行全量：114 个测试文件 → 2 片全绿；ruff 0；
- CI：test / test-py312 全绿；
- 安全文档：`docs/plugin_market_security.md`、`docs/security_review_python_debugger_v2.15.md`。

## 升级注意事项

1. v2.15.1 → v2.16.0 无数据迁移；
2. 若注册表插件带签名，需配置对应公钥/密钥，否则安装会被拒绝（fail closed）；
3. developer 求值模式仅建议在可信调试场景开启。
