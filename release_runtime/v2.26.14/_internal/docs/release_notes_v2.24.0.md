# QingCao Editor v2.24.0 发布说明

> 发布日期：2026-11-10 · 上一版本：v2.23.0

本版本聚焦**性能门禁、安全闭环、架构可维护性**三条主线。

## 性能

- **性能门禁收紧**：有效容差 5×~20× → **2×~4×**，新增分级硬上限（mainwindow 1.5s、open_50mb 8s、session_save 1s 等）；
- **50MB 视口优先加载原型**（`QINGCAO_VIEWPORT_LOAD=1`）：首次可视 **1.44s → 0.09s（16×）**，完整加载 1.44s → 0.70s；默认关闭待验证；
- 修正 CI `theme_reapply` 噪声误报（基线 0.05→0.12s）。

## 安全

- **插件安装/更新风险分级确认**：`process/terminal/debugger` 默认高风险、默认拒绝；
- **ratings.json 签名闭环**：发布端自动签名、客户端 fail-closed 验签；已随注册表重发上线（`ratings.json` + `.sig`，公钥 `1f32f745…`）；
- **安装包 Ed25519 签名**：`tools/sign_update_asset.py` + CI 自动签名上传 `.sig`；
- CI `pip-audit` 安全扫描工作流；权限矩阵测试（run_command/run_python 门禁）。

## 架构

- 全仓业务代码（含 main.py）**均 ≤1,500 行**（不含 `tools/_archive`）：
  - main.py 1,856 → **115**（薄入口），helpers(1,064)/run(687)；
  - file_merge_dialog 1,917→8、search 1,805→99、panels 1,674→20、lsp_client 1,845→1,500、plugin_updater 1,822→1,365、plugin_loader 1,730→1,119、sound_manager 1,689→675、column_editor_dialog 1,606→275、python_console 1,568→955、directory_tree 1,859→1,478；
- 插件加载器支持包式插件相对导入；
- 架构门禁测试覆盖文件行数上限/MRO/re-export。

## 其他

- 插件注册表重发（17 个资产，13 个插件签名完整）；
- 文档：`docs/perf_gate_tightening.md`、`docs/perf_viewport_prototype.md`、`docs/security_hardening_v2.24.md`、`docs/architecture_split_v2.24.md`、`docs/optimization_roadmap_v2.24.md`。

## 验证

- 本地/CI 全量测试通过（含 flaky 原生崩溃回退放行机制）；
- version/ruff/i18n/安全/无障碍/性能门禁全绿。
