# 青草编辑器 v2.20.1 发布说明

> 版本：2.20.1 · 类型：v2.20.x P2 增量

## 新增
- **mmap 跨行等长扩展**：差异区间内换行位置一致即允许跨行补丁，提高大文件保存命中率；
- **插件评分导入/导出**：本地评分 JSON 导出/合并导入/覆盖导入（CLI `tools/plugin_rating_tool.py`）；
- **CI flaky 频率观察**：fallback 放行时记录 `data/ci_flaky_history.jsonl`，
  报告工具 `tools/ci_flaky_report.py`（频率/最近 7 天/决策建议）；
- **终端功能立项建议**：`docs/terminal_feature_proposal.md`（MVP/非目标/风险/里程碑）。

## 验证
- 分片并行全量：全绿；
- CI：i18n 覆盖率+QA 双门禁、全量测试、性能/主题/无障碍门禁全绿（3 片一次通过，未触发 fallback）。

## 升级
v2.20.0 → v2.20.1 无数据迁移。
