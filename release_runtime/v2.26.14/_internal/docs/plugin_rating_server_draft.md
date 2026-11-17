# 插件评分服务端草案（v2.21 P2，未实现）

## 接口
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/v1/plugins/{name}/rating | average/count/distribution |
| POST | /api/v1/plugins/{name}/rating | stars 1-5 + 可选 comment + client_id |
| GET | /api/v1/plugins/{name}/reviews | 最近评论 |

## 策略
- 匿名 client_id + 每日限流 + 异常检测；
- 评论默认公开，可删除；不采集身份；
- 客户端：远端平均分（橙色）与本地评分（绿色）并存，服务不可用回退本地。

## 上线路径
1. 静态 JSON 聚合（GitHub Releases，零服务端）；
2. 只写服务（免费子域/Worker）；
3. 完整评论审核与反垃圾。
