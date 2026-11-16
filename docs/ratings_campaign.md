# 真实用户评分运营（2026-11）

## 用户路径

1. 插件市场 → 插件详情 → 选择星级 + 简评 → **保存评分**（本机）；
2. 点击 **提交到社区** → 打开预填评分 JSON 的 GitHub Issue（`plugin-rating` 模板/标签）；
3. 仓库 Action `ratings-ingest` 自动解析 Issue → 合并 `data/registry_github/ratings.json` → 发布到市场。

## 运营动作

| 渠道 | 动作 |
|---|---|
| Release Notes | 每版附“给插件评分”链接，说明 30 秒流程 |
| README | 增加评分入口说明（本地评分 → 提交到社区） |
| GitHub Issue 模板 | `plugin-rating.yml`，标签 `plugin-rating` |
| 维护者种子 | 本地 16 条为维护者种子，报告中标注，不计入“真实用户”指标 |
| 目标 | 3 个月内：社区样本 ≥50、真实用户 ≥3 |

## 质量与防滥用

- 同一 Issue 幂等合并（`collect_issue_ratings.py` 以来源去重）；
- 评分 JSON 必须来自应用；模板注明“请勿编造”；
- 每周运行 `tools/ratings_report.py` 复核人数/均分。

## 本周执行

1. 发布 v2.26.4 时附评分入口；
2. 在 1 个社区渠道（Discussion/issue）邀请 3 位用户试用并评分；
3. 复核 `docs/ratings_report.md` 是否出现第一条真实社区评分。
