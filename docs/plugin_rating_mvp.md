# 插件市场本地评分 MVP（v2.20 P1-3）

## 范围

- 评分/简评**仅保存在本机**，不上传、不共享；
- 每个插件一条本地评分（1~5 星 + 可选简评）；
- 明确标注「本地评分（仅本机可见）」，避免与远端评分混淆。

## 存储

- 位置：`data/plugin_ratings.json`（可用 `QINGCAO_PLUGIN_RATINGS_FILE` 覆盖）；
- Schema：
```json
{"version": 1,
 "plugins": {"wordcount_sandbox": {"stars": 4, "comment": "好用", "updated": 1700000000.0}}}
```
- 原子写入（临时文件 + `os.replace`），失败不影响主流程。

## UI

- 插件详情：5 星选择 + 简评 + 保存按钮 + 状态提示；
- 插件卡片：有本地评分时显示「★ N 本地」；
- 排序：新增「按本地评分」（无评分视为 0）。

## 未来（预留）

- 注册表 schema 已有 `rating` / `rating_count` 字段（远端评分）；
- 服务端评分上线后：本地评分可上送/同步，或与远端加权；
- 需处理防刷、隐私与撤销。

## 测试

`tests/test_v220_plugin_rating.py`（存储 CRUD/持久化、详情 UI、排序接线、文档）。