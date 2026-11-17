# QingCao Editor v2.26.3 发布说明

> 2026-11-13 · 上一版本：v2.26.2

## 生态
- 新增 `tools/ratings_report.py`：本地/社区评分汇总（`docs/ratings_report.md`）；
- 评分运营手册 `docs/ratings_ops.md`；
- 插件脚手架采用验证（生成 + 清单校验）；
- 样例清理：`my_plugin` 默认禁用，`docs/plugin_samples.md`。

## 工程
- Test 主路径迁移托管 `test-fallback`（push 触发）：实测队列 3s、耗时 P95 178s；
- 自托管 Test 改为每日深度检查；发布门禁接受同 SHA fallback。

## 验证
- 全量测试 206 文件 / 3 片通过；ruff/format 全绿。
