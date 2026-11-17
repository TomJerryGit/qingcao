# 青草编辑器 v2.18.0 发布说明

> 发布日期：2026-11-02 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.18.0`）
> 主题：**插件市场服务化 / 可维护性 / 可观测性**

---

## 一句话概括

v2.18.0 打通插件市场"发布 → 签名 → 注册表服务 → 验签安装"闭环，
完成 `main_window.py` 拆分（-43% 行数），并落地性能趋势报告与崩溃历史分析。

---

## 插件市场在线服务化 MVP

- `tools/build_plugin_registry.py`：扫描插件 → 打包 zip → SHA256 →
  Ed25519 签名 → 生成 `registry.json`；
- `tools/plugin_registry_server.py`：本地/内网 HTTP 注册表服务
  （`/registry.json` + `/plugins/*.zip`，`--check` 自检）；
- 客户端配置注册表 URL 即可在线安装（下载 → 哈希/验签 → 安装 → 重载）；
- 失败路径已验证：篡改拒绝、未配置公钥拒绝（fail closed）、离线回退；
- 文档：`docs/plugin_registry_mvp.md`。

## 可维护性重构（第一批）

- `ui/main_window.py` **5350 → 3048 行（-43%）**；
- 拆分 4 个 Mixin：
  - `menu_builder_mixin.py`（17 方法 / 981 行）
  - `panel_registry_mixin.py`（19 方法 / 355 行）
  - `sandbox_ui_mixin.py`（18 方法 / 529 行）
  - `plugins_ui_mixin.py`（4 方法 / 231 行）
- 行为不变（全量测试 + CI 全绿）。

## 可观测性与无障碍

- **性能趋势报告** `tools/perf_trend_report.py`：
  `--record` 记录历史、`--report` 输出阈值/趋势表，CI 自动记录；
- **崩溃历史分析** `tools/analyze_crash_dumps.py`：
  扫描 Runner 日志统计失败/原生崩溃，报告 `docs/crash_analysis_v2.18.md`；
- **NVDA 修复批次**：输入控件补充 `accessibleDescription`。

## 验证

- 分片并行全量：121 个测试文件 → 2 片全绿；
- 新增测试：注册表端到端（含验签/篡改拒绝/客户端兼容）、崩溃分析、趋势报告、
  无障碍描述；
- CI：test / test-py312 全绿。

## 升级注意事项

1. v2.17.1 → v2.18.0 无数据迁移；
2. 在线市场为本地/内网 MVP（HTTP 无鉴权），公网使用前需 HTTPS 与密钥托管；
3. 真机验证项（NVDA、跨屏 DPI）以清单形式提供，需在真实设备执行。
