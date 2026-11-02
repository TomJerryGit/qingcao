# 青草编辑器 v2.18.1 发布说明

> 发布日期：2026-11-02 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.18.1`）
> 类型：v2.18.x P3 收尾 + 单机模拟验证

---

## 新增

### 插件市场安全增强
- 注册表服务 **Token 鉴权**（Bearer，401 拒绝）与 **HTTPS**（`--cert/--key`）；
- 客户端支持 `QINGCAO_REGISTRY_TOKEN` 与 TLS 校验开关
  （`QINGCAO_REGISTRY_VERIFY_TLS`），requests/urllib 回退路径均带鉴权头。

### mmap 增量编辑预研
- `tools/bench_mmap_edit.py`：24MB 文件单行修改 **7.7× 加速**
  （0.26s → 0.034s），支持 CRLF 等长补丁；
- 设计文档 `docs/mmap_incremental_edit_design.md`。

### i18n 脚手架
- `core/i18n_json.py`：JSON 翻译映射 + 未命中回退原文；
- `tools/extract_i18n_strings.py`：已提取 **5218 条中文串**模板
  （`locale/zh_CN/strings.json`）；
- 迁移计划 `docs/i18n_migration_plan.md`。

### 真机验证（单机可模拟部分已执行）
- `tools/simulate_dpi_matrix.py`：100%/125%/150%/200% 缩放矩阵全部通过；
- `tools/check_a11y_tree.ps1`：Windows UI Automation 树检查
  **65 个元素 / 65 个命名（100%）**，作为 NVDA 替代验证；
- 结果文档 `docs/manual_validation_results_v2.18.md`。

## 未覆盖（环境边界）

- NVDA 实际语音播报：本机未安装，需安装后按清单执行；
- 跨屏拖动/混合 DPI 跳变：需第二块物理显示器。

## 验证

- 分片并行全量：122 个测试文件 → 2 片全绿；
- 新增 P3 测试（Token/HTTPS/mmap/i18n）与验证工具；
- CI：test / test-py312 全绿。

## 升级注意事项

1. v2.18.0 → v2.18.1 无数据迁移；
2. 启用 Token 鉴权时客户端必须配置相同 Token，否则 401；
3. mmap 增量编辑尚未接入保存路径（仅预研/基准）。
