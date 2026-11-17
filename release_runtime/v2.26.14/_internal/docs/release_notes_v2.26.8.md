# QingCao Editor v2.26.8 发布说明

> 2026-11-16 · 上一版本：v2.26.7

## 安全（B3）
- 高风险 API 信任门控：仅 `trusted` 且显式允许时放行；
- git_deep 通过宿主受控 Git API 在子进程运行（process 不下放）；
- AI 网络代理：普通 + 流式 SSE，`AIClient` 可注入宿主 transport；默认 `QINGCAO_AI_NETWORK_BROKER=1` 关闭。

## 生态
- 插件目录 `docs/plugin_catalog.md`（15 插件）；
- 性能趋势 `docs/perf_trend.md` + 每周工作流；
- 插件开发指南 `docs/plugin_development.md`、8 插件激活冒烟测试；
- 调试器宿主服务立项：`docs/debugger_host_service_plan.md`、Issue #2（8 天/M1–M4）。

## 验证
- B3/AI/生态测试通过；全量测试 3 片通过。
