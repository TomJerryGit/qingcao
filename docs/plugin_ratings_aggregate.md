# 插件评分静态聚合（v2.23 P1-2，零服务端）

## 目标
把本地评分导出为 `ratings.json`，随注册表发布到 GitHub Releases，客户端可只读获取平均分，无需自建服务。

## Schema
```json
{"version":1,"generated_at":"...","source":"local-export",
 "plugins":{"wordcount_sandbox":{"average":4.0,"count":1,"sources":["local"]}}}
```

## 生成与发布
```powershell
python tools/build_ratings_aggregate.py
python tools/publish_registry_release.py --dry-run   # 会同时生成 ratings.json
```
`publish_registry_release.py` 在构建注册表后自动聚合本地评分并写入 `data/registry_github/ratings.json`，随 `registry.json` 一起上传。

## 客户端（已实现）

- `PluginStoreClient.fetch_ratings()`：从注册表基址拉取 `ratings.json`（超时 5s，失败静默）；
- `set_community_ratings/get_community_rating`：模块级缓存；
- 市场打开时自动加载，卡片显示「★ 4.5 社区 (N)」，详情显示「社区 ★ 4.5 (N)」；
- 拉取失败/离线时回退本地评分，不阻塞市场；
- 测试环境 `QINGCAO_NO_COMMUNITY_RATINGS=1` 关闭网络。
- 从注册表基址拉取 `ratings.json`，在卡片/详情展示「社区平均分」；
- 远端不可用时回退本地评分；
- 本地评分仍不上传（当前聚合为本地导出，非真实社区数据）。

## 定位
这是阶段 1（只读静态聚合）；阶段 2 才是只写服务端（见 `docs/plugin_rating_server_draft.md`）。
