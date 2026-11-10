# 真实插件评分收集与发布（v2.24）

## 数据流
1. 用户在应用「插件市场 → 详情 → 星级评分 → 保存评分」；
2. 评分写入 `data/plugin_ratings.json`（本机，不上传）；
3. 用户导出该文件并提交（GitHub Issue / 私聊 / PR）；
4. 维护者运行收集器合并多份真实提交：
   ```powershell
   python tools/collect_ratings.py submissions/*.json
   ```
   输出 `data/ratings_community.json`（加权平均 + 提交数）；
5. 发布（自动聚合 + 签名）：
   ```powershell
   python tools/build_ratings_aggregate.py
   ```
   `publish_registry_release.py` 会读取 community 数据并签名上传。

## 约束
- **禁止编造评分**：只合并真实用户导出的文件；
- 每份提交按用户计 1 票；本地单人评分 count=1；
- 未达到 3 位用户前不建议对外标注"社区评分"，可按实际 count 展示。
