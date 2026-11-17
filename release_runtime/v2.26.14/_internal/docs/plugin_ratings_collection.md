# 真实插件评分收集与发布

## 数据流
1. 应用内评分：插件市场 → 详情 → 星级 → 保存评分（写入本机 `data/plugin_ratings.json`）；
2. 汇总为**可跟踪**社区文件：
   ```powershell
   python tools/collect_ratings.py data/plugin_ratings.json --out community_ratings.json
   ```
3. 聚合（合并 community + 本地）：
   ```powershell
   python tools/build_ratings_aggregate.py
   ```
4. 触发 `Publish Plugin Registry`（工作流文件变更自触发或 PAT dispatch）→ 签名上传 `ratings.json`。

## 当前数据
- `community_ratings.json`：16 个插件，均为真实用户评分（count=1，average=5.0）；
- 客户端按 `count`/`average` 展示「社区平均分」，不足 3 位用户时仅供参考。

## 质量约束
- 禁止编造评分；每次提交需为真实用户导出文件；
- `collect_ratings.py` 按用户计 1 票并做加权平均。

## 评分运营闭环（v2.25 阶段 3.1）

1. 应用内「评分邀请」引导用户评分（写入本机 `data/plugin_ratings.json`）；
2. 用户用 Issue 模板「插件评分提交」粘贴导出 JSON；
3. `Ratings Ingest` 工作流（每日 04:00 UTC）：
   - `tools/collect_issue_ratings.py --apply` 拉取 `plugin-rating` Issue；
   - 按 issue 编号幂等（`data/ratings_ingested.json`），1 用户 1 票加权合并；
   - 有变更时自动提交 `community_ratings.json` 并 `gh workflow run publish_registry.yml`；
4. 发布工作流重新聚合 + Ed25519 签名上传 `ratings.json`。
