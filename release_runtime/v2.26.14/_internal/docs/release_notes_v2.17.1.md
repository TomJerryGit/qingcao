# 青草编辑器 v2.17.1 发布说明

> 发布日期：2026-11-02 · 平台：Windows x64 · 便携版（免安装）
> 版本权威来源：`version.py`（`2.17.1`）
> 类型：v2.17.x P2 收尾（稳定性与可观测性）

---

## 新增

- **CI Qt 崩溃治理**：
  - `main.py` 启用 `faulthandler`，原生崩溃栈写入 `logs/crash_dump_<pid>.log`；
  - 新增 `tools/enable_crash_dumps.py`：配置 Windows 错误报告本地转储
    （HKLM LocalDumps，DumpType=1），支持 `--check/--remove`；
  - CI 新增 best-effort 崩溃转储步骤；
  - 排查手册 `docs/ci_qt_crash_playbook.md`（采集/复现/WinDbg/历史诱因）。
- **全局搜索大文件保护**：搜索跳过 >10MB 文件并在结果中提示
  「跳过 N 个 >10MB 大文件」（搜索本身已是后台线程）。
- **NVDA 屏幕阅读器验证清单**：`docs/manual_validation_v2.17_nvda.md`
  （7 项人工检查 + 记录表 + 自动化辅助命令）。

## 确认既有能力

- 插件市场**批量更新**：检查更新 → 确认 → `_update_all` 一键全部更新
  （不兼容项自动跳过），已补回归断言。

## 验证

- 分片并行全量：119 个测试文件 → 2 片全绿；
- 新增 `tests/test_v217x_p2.py`（崩溃工具/搜索跳过/接线文档）；
- CI：test / test-py312 全绿。

## 升级注意事项

1. v2.17.0 → v2.17.1 无数据迁移；
2. 崩溃转储配置需管理员权限（应用内功能不受影响）；
3. >10MB 文件默认不在全局搜索结果中，可在文件内搜索。
