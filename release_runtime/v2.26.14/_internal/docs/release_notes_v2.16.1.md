# 青草编辑器 v2.16.1 发布说明

> 发布日期：2026-10-30 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.16.1`）
> 类型：P3 收尾 + CI 稳定性修复（小版本）

---

## 新增

- **插件签名工具** `tools/sign_plugin.py`（keygen / sign / verify，Ed25519）；
- **密钥轮换/吊销操作手册** `docs/plugin_market_key_rotation_playbook.md`；
- **只读沙箱插件** `whitespace_sandbox`：行尾空白 / Tab 缩进 / 超长行诊断；
- **主题 E2E 基线 CI 对比**：`theme_e2e_screenshots.py --check`
  （panel 阈值 24、window 80），CI 新增 Theme baseline check 步骤。

## 修复

- 性能门禁 `--auto` **最低有效容差 5×**，避免空闲 Runner 噪声误报；
- 沙箱插件目录支持 `QINGCAO_SANDBOX_PLUGIN_DIR` 覆盖（测试会话级隔离）。

## 验证

- 分片并行全量：115 个测试文件 → 2 片全绿；
- 沙箱定向测试（诊断聚合/菜单/配置/e2e）全过；
- CI：test / test-py312 全绿。

## 升级注意事项

1. v2.16.0 → v2.16.1 无数据迁移；
2. 新增沙箱插件默认启用，可在插件面板禁用；
3. CI 主题基线对比依赖 `docs/theme_baseline/`，更新 UI 后需重新生成基线。
